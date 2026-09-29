from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.envelope import AppError
from app.shipments.models import ShipmentEvent
from app.shipments.service import cancel_shipment, try_auto_advance
from app.trucking.models import TruckingOrder

DONE = ("ASSIGNED", "STARTED", "COMPLETED")


def _at_warehouse_events(db, shipment):
    return db.scalar(select(func.count()).select_from(ShipmentEvent).where(
        ShipmentEvent.shipment_id == shipment.id, ShipmentEvent.to_status == "AT_WAREHOUSE"))


@pytest.fixture
def two_containers(make_shipment, make_container):
    shipment = make_shipment(status="CLEARED")
    return shipment, make_container(shipment), make_container(shipment)


def test_auto_at_warehouse_when_all_pickups_completed(db, two_containers, make_trucking_order):
    shipment, c1, c2 = two_containers
    make_trucking_order(c1, events=DONE)
    make_trucking_order(c2, events=DONE)
    assert try_auto_advance(db, shipment) is True and shipment.status == "AT_WAREHOUSE"
    event = db.scalars(select(ShipmentEvent).where(ShipmentEvent.shipment_id == shipment.id)
                       .order_by(ShipmentEvent.id.desc())).first()
    assert (event.actor_id, event.from_status, event.reason) == (None, "CLEARED", "Tự chuyển: mọi container đã tới kho đích")


def test_no_advance_when_one_pickup_not_completed(db, two_containers, make_trucking_order):
    shipment, c1, c2 = two_containers
    make_trucking_order(c1, events=DONE)
    make_trucking_order(c2, events=("ASSIGNED", "STARTED"))
    assert try_auto_advance(db, shipment) is False and shipment.status == "CLEARED"


def test_cancelled_pickup_not_counted(db, two_containers, make_trucking_order):
    shipment, c1, c2 = two_containers
    make_trucking_order(c1, events=DONE)
    make_trucking_order(c2, events=("CANCELLED",))
    assert try_auto_advance(db, shipment) is False


def test_no_advance_when_shipment_not_cleared(db, make_shipment, make_container, make_trucking_order):
    shipment = make_shipment(status="CUSTOMS_CLEARING")
    make_trucking_order(make_container(shipment), events=DONE)
    assert try_auto_advance(db, shipment) is False and shipment.status == "CUSTOMS_CLEARING"


def test_container_to_door_also_advances(db, make_shipment, make_container, make_trucking_order):
    shipment = make_shipment(status="CLEARED", delivery_mode="CONTAINER_TO_DOOR")
    make_trucking_order(make_container(shipment), events=DONE)
    assert try_auto_advance(db, shipment) is True and shipment.status == "AT_WAREHOUSE"


def test_try_auto_advance_twice_single_event(db, two_containers, make_trucking_order):
    shipment, c1, c2 = two_containers
    make_trucking_order(c1, events=DONE)
    make_trucking_order(c2, events=DONE)
    assert [try_auto_advance(db, shipment), try_auto_advance(db, shipment)] == [True, False]
    assert _at_warehouse_events(db, shipment) == 1


def test_cancel_shipment_cancels_planned_and_assigned_orders(db, make_user, two_containers, make_trucking_order):
    shipment, c1, c2 = two_containers
    planned, assigned = make_trucking_order(c1), make_trucking_order(c2, events=("ASSIGNED",))
    cancel_shipment(db, shipment.id, "Khách bỏ hàng", make_user("ADMIN"))
    assert shipment.status == "CANCELLED"
    db.refresh(planned)
    db.refresh(assigned)
    assert (planned.status, assigned.status) == ("CANCELLED", "CANCELLED")


def test_cancel_shipment_with_gate_out_rejected_keeps_orders(db, make_user, make_shipment, make_container,
                                                             make_trucking_order):
    shipment = make_shipment(status="CLEARED")
    container = make_container(shipment, milestones={"GATE_OUT_FULL": datetime(2026, 11, 26, 3, 0, tzinfo=UTC)})
    order = make_trucking_order(container)
    with pytest.raises(AppError) as info:
        cancel_shipment(db, shipment.id, "muộn", make_user("ADMIN"))
    assert info.value.code == "CANCEL_AFTER_GATE_OUT"
    assert db.get(TruckingOrder, order.id).status == "PLANNED" and shipment.status == "CLEARED"
