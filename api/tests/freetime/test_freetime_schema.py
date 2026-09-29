import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.freetime.models import FreeTimeRule, FreeTimeTier, ShipmentFreeTimeOverride


def _rule(ft, **overrides):
    values = {"carrier_id": ft.carrier().id, "port_id": ft.port().id, "container_type": "40HC", "fee_type": "DEM",
              "free_days": 5, "effective_from": "2026-01-01"}
    return FreeTimeRule(**{**values, **overrides})


def _flush_fails(db, obj, match=None):
    db.add(obj)
    with pytest.raises(IntegrityError, match=match):
        db.flush()
    db.rollback()


def test_rule_unique_on_five_keys_and_effective_date(db, ft):
    db.add(_rule(ft))
    db.flush()
    _flush_fails(db, _rule(ft), "uq_free_time_rules_key")


def test_rule_new_effective_date_is_allowed(db, ft):
    db.add_all([_rule(ft), _rule(ft, effective_from="2026-06-01", free_days=3)])
    db.flush()
    assert len(db.scalars(select(FreeTimeRule)).all()) == 2


@pytest.mark.parametrize("free_days", [-1, 366])
def test_rule_free_days_must_be_0_to_365(db, ft, free_days):
    _flush_fails(db, _rule(ft, free_days=free_days))


@pytest.mark.parametrize("free_days", [0, 365])
def test_rule_free_days_bounds_accepted(db, ft, free_days):
    db.add(_rule(ft, free_days=free_days))
    db.flush()


@pytest.mark.parametrize("field", [{"fee_type": "XYZ"}, {"container_type": "40FR"}])
def test_rule_fee_type_and_container_type_checked(db, ft, field):
    _flush_fails(db, _rule(ft, **field))


@pytest.mark.parametrize(("from_day", "to_day"), [(0, None), (6, 5)])
def test_tier_bounds_checked(db, ft, from_day, to_day):
    rule = _rule(ft)
    db.add(rule)
    db.flush()
    _flush_fails(db, FreeTimeTier(rule_id=rule.id, from_day=from_day, to_day=to_day, rate_amount=1, currency="USD"))


def test_tier_currency_only_vnd_usd(db, ft):
    rule = _rule(ft)
    db.add(rule)
    db.flush()
    _flush_fails(db, FreeTimeTier(rule_id=rule.id, from_day=6, to_day=None, rate_amount=1, currency="EUR"))


def test_deleting_rule_cascades_tiers(db, ft):
    (rule,) = ft.rules("REGU", "VNSGN", "40HC", dem=(5, [(6, None, 2000, "USD")]))
    db.delete(rule)
    db.flush()
    assert db.scalars(select(FreeTimeTier)).all() == []


def test_override_unique_per_shipment_and_fee_type(db, ft):
    shipment_id = ft.container().shipment_id
    ft.override(shipment_id, "DEM", 10)
    ft.override(shipment_id, "DET", 10)
    db.add(ShipmentFreeTimeOverride(shipment_id=shipment_id, fee_type="DEM", free_days=3, source="DO"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_override_source_checked(db, ft):
    shipment_id = ft.container().shipment_id
    _flush_fails(db, ShipmentFreeTimeOverride(shipment_id=shipment_id, fee_type="DEM", free_days=3, source="PHONE"))
