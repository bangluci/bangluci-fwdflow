from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.catalog.models import Customer
from app.events import effective_events
from app.shipments.models import ContainerEvent, Shipment, ShipmentEvent

T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)


def _event(event_id, kind, occurred_at, adjusts=None, recorded_offset=0):
    return SimpleNamespace(id=event_id, kind=kind, occurred_at=occurred_at, adjusts_event_id=adjusts,
                           recorded_at=T0 + timedelta(minutes=recorded_offset), actor_id=None)


def test_effective_events_applies_latest_retime():
    events = [_event(1, "DISCHARGED", T0), _event(2, "RETIME", T0 + timedelta(hours=1), adjusts=1, recorded_offset=1),
              _event(3, "RETIME", T0 + timedelta(hours=2), adjusts=1, recorded_offset=2)]
    (only,) = effective_events(events)
    assert only.occurred_at == T0 + timedelta(hours=2) and only.original_occurred_at == T0


def test_effective_events_drops_voided_event():
    events = [_event(1, "DISCHARGED", T0), _event(2, "GATE_OUT_FULL", T0, recorded_offset=1),
              _event(3, "VOID", T0, adjusts=2, recorded_offset=2)]
    assert [e.id for e in effective_events(events)] == [1]


def test_effective_events_voided_retime_restores_time():
    events = [_event(1, "DISCHARGED", T0), _event(2, "RETIME", T0 + timedelta(hours=5), adjusts=1, recorded_offset=1),
              _event(3, "VOID", T0, adjusts=2, recorded_offset=2)]
    (only,) = effective_events(events)
    assert only.occurred_at == T0


def test_shipment_events_update_blocked(db, make_shipment):
    shipment = make_shipment()
    with pytest.raises(DBAPIError, match="append-only|không được"):
        db.execute(text("UPDATE shipment_events SET reason = 'x' WHERE shipment_id = :id"), {"id": shipment.id})
    db.rollback()


def test_container_events_delete_blocked(db, make_shipment, make_container):
    container = make_container(make_shipment(status="ARRIVED"), milestones={"DISCHARGED": T0})
    with pytest.raises(DBAPIError, match="append-only|không được"):
        db.execute(text("DELETE FROM container_events WHERE container_id = :id"), {"id": container.id})
    db.rollback()


def test_lcl_container_to_door_violates_check(db, make_user):
    customer = Customer(name="KH")
    db.add(customer)
    db.flush()
    db.add(Shipment(load_type="LCL", delivery_mode="CONTAINER_TO_DOOR", customer_id=customer.id,
                    staff_id=make_user("DOCS").id))
    with pytest.raises(IntegrityError, match="ck_shipments_lcl_via_warehouse"):
        db.flush()
    db.rollback()


def test_shipment_code_format(make_shipment):
    assert make_shipment().code.startswith("FF") and len(make_shipment().code) == 9
    assert make_shipment().code[2:].isdigit()


def test_event_models_expose_common_columns(make_shipment):
    shipment = make_shipment(status="IN_TRANSIT")
    assert ShipmentEvent.__table__.c.adjusts_event_id.foreign_keys and ContainerEvent.__table__.c.reason is not None
    assert shipment.status == "IN_TRANSIT"
