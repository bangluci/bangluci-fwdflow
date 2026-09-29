import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.trucking.models import TruckingOrderEvent


@pytest.fixture
def container(make_shipment, make_container):
    return make_container(make_shipment())


def test_trucking_events_append_only(db, container, make_trucking_order):
    order = make_trucking_order(container, events=("ASSIGNED",))
    event = db.query(TruckingOrderEvent).filter_by(order_id=order.id).one()
    with pytest.raises(DBAPIError, match="append-only|forbid|không được"):
        with db.begin_nested():
            db.execute(text("UPDATE trucking_order_events SET reason = 'x' WHERE id = :id"), {"id": event.id})
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text("DELETE FROM trucking_order_events WHERE id = :id"), {"id": event.id})


def test_one_active_order_per_container_kind(db, container, make_trucking_order):
    make_trucking_order(container, "PICKUP_FULL")
    make_trucking_order(container, "RETURN_EMPTY")  # khác loại thì được
    with pytest.raises(IntegrityError, match="uq_trucking_orders_active"):
        with db.begin_nested():
            make_trucking_order(container, "PICKUP_FULL")


def test_new_order_allowed_after_cancel(container, make_trucking_order):
    make_trucking_order(container, "PICKUP_FULL", events=("CANCELLED",))
    assert make_trucking_order(container, "PICKUP_FULL").status == "PLANNED"


@pytest.mark.parametrize("status", ["ASSIGNED", "STARTED", "COMPLETED"])
def test_assigned_requires_truck_and_driver(db, container, make_trucking_order, status):
    order = make_trucking_order(container)
    with pytest.raises(IntegrityError, match="ck_trucking_orders_assigned"):
        with db.begin_nested():
            db.execute(text("UPDATE trucking_orders SET status = :s WHERE id = :id"), {"s": status, "id": order.id})
