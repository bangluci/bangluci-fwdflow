from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.envelope import AppError
from app.finance.models import Charge
from app.finance.service import compute_amount_vnd, create_charge, shipment_profit


def _code(fn, *args, **kwargs):
    with pytest.raises(AppError) as info:
        fn(*args, **kwargs)
    return info.value.code, info.value.status


def _charge(direction="REVENUE", category="OCEAN_FREIGHT", amount=1000, currency="VND", fx_rate=None):
    return {"direction": direction, "category": category, "amount": amount, "currency": currency,
            "fx_rate": fx_rate}


def _count(db):
    return db.scalar(select(func.count()).select_from(Charge))


def test_amount_vnd_usd_rounds_half_up():
    assert compute_amount_vnd(12345, "USD", Decimal(25410)) == (3136865, Decimal(25410))  # 3136864,5 → lên


def test_amount_vnd_vnd_equals_amount():
    assert compute_amount_vnd(15_000_000, "VND", Decimal(25000)) == (15_000_000, Decimal(1))


def test_usd_charge_without_fx_rate_rejected(db, make_shipment, make_user):
    shipment, actor = make_shipment(), make_user("ACCOUNTANT")
    for fx in (None, Decimal(0), Decimal(-1)):
        assert _code(create_charge, db, shipment.id, _charge(currency="USD", fx_rate=fx), actor) == (
            "FX_RATE_REQUIRED", 400)
    assert _count(db) == 0


@pytest.mark.parametrize("amount", [0, -1])
def test_non_positive_amount_rejected(amount):
    assert _code(compute_amount_vnd, amount, "VND", None) == ("INVALID_AMOUNT", 400)


def test_unsupported_currency_rejected():
    assert _code(compute_amount_vnd, 100, "EUR", Decimal(1)) == ("UNSUPPORTED_CURRENCY", 400)


def test_charges_check_rejects_usd_zero_fx_at_db(db, make_shipment):
    shipment = make_shipment()
    with pytest.raises(IntegrityError, match="ck_charges_fx"):
        with db.begin_nested():
            db.execute(text("INSERT INTO charges (shipment_id, direction, category, amount, currency, fx_rate, "
                            "amount_vnd) VALUES (:s, 'COST', 'OTHER', 100, 'USD', 0, 0)"), {"s": shipment.id})


def test_shipment_profit_matches_manual_fixture(db, make_shipment, make_user):
    shipment, actor = make_shipment(), make_user("ACCOUNTANT")
    for data in (_charge("REVENUE", "OCEAN_FREIGHT", 15_000_000), _charge("REVENUE", "OTHER", 50_000, "USD", Decimal(25400)),
                 _charge("COST", "OCEAN_FREIGHT", 35_000, "USD", Decimal(25400)),
                 _charge("COST", "TRUCKING", 3_500_000), _charge("COST", "DEM", 2_200_000)):
        create_charge(db, shipment.id, data, actor)
    profit = shipment_profit(db, shipment.id)
    assert (profit.revenue_vnd, profit.cost_vnd, profit.profit_vnd) == (27_700_000, 14_590_000, 13_110_000)
    assert shipment_profit(db, make_shipment().id).profit_vnd == 0
