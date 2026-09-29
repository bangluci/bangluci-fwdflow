from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.catalog.models import Customer
from app.finance.service import create_charge
from app.reports.demdet import is_demdet_flagged
from app.shipments.models import Shipment

URL = "/api/reports/demdet"
NOV = {"from_month": "2026-11", "to_month": "2026-11"}
CLOSED_CYCLE = {"DISCHARGED": "2026-11-01", "GATE_OUT_FULL": "2026-11-13", "EMPTY_RETURNED": "2026-11-18"}


@pytest.fixture(autouse=True)
def fixed_today(db):
    db.execute(text("SELECT set_config('app.as_of', '2026-11-30', true)"))


@pytest.fixture
def accountant(login_as):
    return login_as("ACCOUNTANT")


def _cost(db, shipment, actor, category="DEM", amount=5_000_000, direction="COST"):
    return create_charge(db, shipment.id, {"direction": direction, "category": category, "amount": amount,
                                           "currency": "VND"}, actor)


def _rows(client, **params):
    return client.get(URL, params={**NOV, **params}).json()["data"]


@pytest.mark.parametrize(("estimate", "actual", "flagged"), [
    (10_000_000, 12_000_000, False), (10_000_000, 12_000_001, True), (10_000_000, 7_999_999, True),
    (10_000_000, 8_000_000, False), (0, 1, True), (0, 0, False)])
def test_demdet_flag_boundary(estimate, actual, flagged):
    assert is_demdet_flagged(estimate, actual) is flagged


def test_demdet_estimate_converts_usd_with_fx(client, db, ft, accountant):
    ft.standard_rules()
    container = ft.container(status="COMPLETED", milestones=CLOSED_CYCLE)
    _cost(db, db.get(Shipment, container.shipment_id), accountant)
    data = _rows(client)
    (row,) = data["rows"]
    assert (row["estimate_vnd"], row["actual_vnd"], row["deviation_pct"], row["flagged_shipments"]) == (
        5_588_000, 5_000_000, -10.5, 0)
    assert data["fx_usd_vnd"] == 25_400 and data["totals"]["estimate_vnd"] == 5_588_000


def test_demdet_actual_counts_only_cost_dem_det_combined(client, db, ft, accountant):
    ft.standard_rules()
    shipment = db.get(Shipment, ft.container(status="COMPLETED", milestones=CLOSED_CYCLE).shipment_id)
    _cost(db, shipment, accountant)
    _cost(db, shipment, accountant, category="DEM", direction="REVENUE", amount=9_000_000)
    _cost(db, shipment, accountant, category="TRUCKING", amount=3_000_000)
    _cost(db, shipment, accountant, category="DND_COMBINED", amount=1_000_000)
    assert _rows(client)["rows"][0]["actual_vnd"] == 6_000_000


def test_demdet_month_uses_first_discharged_vn_date(client, ft, accountant):
    ft.standard_rules()
    ft.container(status="ARRIVED", milestones={"DISCHARGED": datetime(2026, 10, 31, 17, 30, tzinfo=UTC)})
    assert len(_rows(client)["rows"]) == 1
    assert _rows(client, from_month="2026-10", to_month="2026-10")["rows"] == []


def test_demdet_group_by_month_customer_carrier(client, db, ft, accountant):
    ft.standard_rules()
    for name, day in (("Khach A", "2026-11-05"), ("Khach B", "2026-11-06")):
        customer = Customer(name=name)
        db.add(customer)
        db.flush()
        ft.container(status="ARRIVED", milestones={"DISCHARGED": day}, customer=customer)
    by = {group: _rows(client, group_by=group) for group in ("month", "customer", "carrier", "shipment")}
    assert [len(by[g]["rows"]) for g in ("month", "customer", "carrier", "shipment")] == [1, 2, 1, 2]
    assert by["month"]["rows"][0]["shipments"] == 2 and by["carrier"]["rows"][0]["label"] == "REGU"
    assert by["customer"]["totals"] == by["month"]["totals"] and by["month"]["rows"][0]["key"] == "2026-11"
    assert {r["label"] for r in by["customer"]["rows"]} == {"Khach A", "Khach B"}


def test_demdet_excludes_cancelled_and_lcl(client, ft, accountant):
    ft.standard_rules()
    ft.container(status="CANCELLED", milestones={"DISCHARGED": "2026-11-05"})
    ft.container(status="ARRIVED", load_type="LCL", milestones={"DISCHARGED": "2026-11-05"})
    ft.container(status="IN_TRANSIT", eta="2026-12-20")  # chưa dỡ hàng
    assert _rows(client)["rows"] == []


@pytest.mark.parametrize("role", ["DOCS", "DISPATCH"])
def test_demdet_forbidden_for_docs_dispatch(client, login_as, role):
    login_as(role)
    res = client.get(URL)
    assert res.status_code == 403 and res.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("params", [{"from_month": "2026-13", "to_month": "2026-13"},
                                    {"from_month": "2026-12", "to_month": "2026-11"},
                                    {"from_month": "2025-11", "to_month": "2026-11"}])
def test_demdet_invalid_range_rejected(client, accountant, params):
    res = client.get(URL, params=params)
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_RANGE"


def test_demdet_defaults_to_current_month(client, ft, accountant):
    ft.standard_rules()
    ft.container(status="ARRIVED", milestones={"DISCHARGED": "2026-11-20"})
    data = client.get(URL).json()["data"]
    assert (data["from_month"], data["to_month"], data["group_by"]) == ("2026-11", "2026-11", "shipment")
    assert len(data["rows"]) == 1
