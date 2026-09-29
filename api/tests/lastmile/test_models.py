import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.audit.models import AuditLog
from app.audit.service import record_audit, snapshot
from app.lastmile.models import ORDER_FIELDS, LastMileEvent


@pytest.fixture
def shipment(make_shipment):
    return make_shipment(status="AT_WAREHOUSE")


def test_last_mile_events_append_only(db, shipment, make_last_mile_order):
    order = make_last_mile_order(shipment)
    event = db.scalars(select(LastMileEvent).where(LastMileEvent.order_id == order.id)).one()
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text("UPDATE last_mile_events SET reason = 'x' WHERE id = :id"), {"id": event.id})
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text("DELETE FROM last_mile_events WHERE id = :id"), {"id": event.id})


def test_tracking_code_unique_constraint(db, shipment, make_last_mile_order):
    make_last_mile_order(shipment, tracking_code="ABCDE12345")
    with pytest.raises(IntegrityError, match="tracking_code"):
        with db.begin_nested():
            make_last_mile_order(shipment, tracking_code="ABCDE12345")


def test_coordinates_both_or_none_check(db, shipment, make_last_mile_order):
    order = make_last_mile_order(shipment)
    with pytest.raises(IntegrityError, match="ck_last_mile_events_coordinates"):
        with db.begin_nested():
            db.add(LastMileEvent(order_id=order.id, kind="DELIVERED", occurred_at=order.created_at, lat=10.5))
            db.flush()


def test_packages_must_be_positive(db, shipment, make_last_mile_order):
    with pytest.raises(IntegrityError, match="packages"):
        with db.begin_nested():
            make_last_mile_order(shipment, packages=0)


def test_audit_masks_recipient_phone_and_address(db, shipment, make_last_mile_order):
    order = make_last_mile_order(shipment, recipient_phone="0901234567", address="12 Lê Lợi, Quận 1, TP.HCM")
    record_audit(db, None, "CREATE", "last_mile_order", order.id, after=snapshot(order, ORDER_FIELDS))
    db.flush()
    row = db.scalars(select(AuditLog).where(AuditLog.entity == "last_mile_order")).one()
    dumped = str(row.after)
    assert "0901234567" not in dumped and "Lê Lợi" not in dumped and "Nguyễn Văn An" not in dumped
    assert row.after["tracking_code"] == order.tracking_code
