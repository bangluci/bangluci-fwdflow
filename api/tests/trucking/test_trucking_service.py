from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.catalog.models import Driver, Truck
from app.envelope import AppError
from app.trucking import service
from app.trucking.models import TruckingOrder, TruckingOrderEvent
from app.trucking.schemas import OrderCreate

PLANNED_AT = datetime(2026, 11, 26, 8, 0, tzinfo=UTC)


@pytest.fixture
def world(db, make_user, make_shipment, make_container, make_trucker):
    shipment = make_shipment(status="CLEARED")
    return type("World", (), {
        "actor": make_user("DISPATCH"), "shipment": shipment, "container": make_container(shipment),
        "team": make_trucker(), "make_container": staticmethod(make_container)})


def body(world, kind="PICKUP_FULL", container=None, trucker=None):
    return OrderCreate(container_id=(container or world.container).id, kind=kind,
                       trucker_id=(trucker or world.team.trucker).id, pickup_location=" Cảng Cát Lái ",
                       drop_location="Kho Bình Dương", planned_at=PLANNED_AT)


def code(fn, *args, **kwargs):
    with pytest.raises(AppError) as info:
        fn(*args, **kwargs)
    return info.value.code, info.value.status


def test_create_pickup_full_planned(db, world):
    order = service.create_order(db, world.actor, body(world))
    assert (order.status, order.kind, order.truck_id, order.driver_id) == ("PLANNED", "PICKUP_FULL", None, None)
    assert order.pickup_location == "Cảng Cát Lái" and order.created_by_id == world.actor.id


def test_second_active_pickup_rejected(db, world):
    service.create_order(db, world.actor, body(world))
    assert code(service.create_order, db, world.actor, body(world)) == ("DUPLICATE_ORDER", 409)


def test_pickup_after_cancel_allowed(db, world):
    first = service.create_order(db, world.actor, body(world))
    service.cancel_order(db, world.actor, first.id, "Đổi kế hoạch")
    assert service.create_order(db, world.actor, body(world)).status == "PLANNED"


def test_return_empty_requires_completed_pickup(db, world, make_trucking_order):
    assert code(service.create_order, db, world.actor, body(world, "RETURN_EMPTY")) == ("PICKUP_NOT_COMPLETED", 409)
    make_trucking_order(world.container, "PICKUP_FULL", events=("ASSIGNED", "STARTED"), team=world.team)
    assert code(service.create_order, db, world.actor, body(world, "RETURN_EMPTY")) == ("PICKUP_NOT_COMPLETED", 409)


def test_return_empty_after_completed_pickup_allowed(db, world, make_trucking_order):
    make_trucking_order(world.container, "PICKUP_FULL", events=("ASSIGNED", "STARTED", "COMPLETED"), team=world.team)
    assert service.create_order(db, world.actor, body(world, "RETURN_EMPTY")).kind == "RETURN_EMPTY"


def test_create_on_lcl_rejected(db, world, make_shipment, make_container):
    lcl = make_shipment(status="CLEARED", load_type="LCL")
    assert code(service.create_order, db, world.actor, body(world, container=make_container(lcl))) == ("NOT_FCL", 422)


def test_create_on_cancelled_shipment_rejected(db, world, make_shipment, make_container):
    closed = make_container(make_shipment(status="CANCELLED"))
    assert code(service.create_order, db, world.actor, body(world, container=closed)) == ("SHIPMENT_CLOSED", 409)
    world.team.trucker.active = False
    db.flush()
    assert code(service.create_order, db, world.actor, body(world)) == ("INACTIVE_REFERENCE", 422)


def test_truck_of_other_trucker_rejected(db, world, make_trucker):
    order = service.create_order(db, world.actor, body(world))
    other = make_trucker()
    assert code(service.assign_order, db, world.actor, order.id, other.truck.id, world.team.driver.id) == (
        "TRUCKER_MISMATCH", 422)
    assert code(service.assign_order, db, world.actor, order.id, world.team.truck.id, other.driver.id) == (
        "TRUCKER_MISMATCH", 422)


def test_assign_moves_to_assigned(db, world):
    order = service.create_order(db, world.actor, body(world))
    service.assign_order(db, world.actor, order.id, world.team.truck.id, world.team.driver.id)
    assert (order.status, order.truck_id, order.driver_id) == ("ASSIGNED", world.team.truck.id, world.team.driver.id)
    (event,) = db.scalars(select(TruckingOrderEvent).where(TruckingOrderEvent.order_id == order.id))
    assert (event.kind, event.truck_id, event.driver_id, event.actor_id) == (
        "ASSIGNED", world.team.truck.id, world.team.driver.id, world.actor.id)
    assert code(service.assign_order, db, world.actor, order.id, world.team.truck.id, world.team.driver.id) == (
        "INVALID_TRANSITION", 409)


def test_reassign_keeps_status_and_requires_reason(db, world, make_trucking_order):
    order = make_trucking_order(world.container, events=("ASSIGNED", "STARTED"), team=world.team)
    spare = world.team.trucker
    truck = Truck(trucker_id=spare.id, plate_no="51C-99999")
    driver = Driver(trucker_id=spare.id, full_name="Tai xe moi")
    db.add_all([truck, driver])
    db.flush()
    assert code(service.reassign_order, db, world.actor, order.id, truck.id, driver.id, "  ") == ("REASON_REQUIRED", 422)
    service.reassign_order(db, world.actor, order.id, truck.id, driver.id, "Xe hỏng lốp")
    assert (order.status, order.truck_id, order.driver_id) == ("STARTED", truck.id, driver.id)
    last = db.scalars(select(TruckingOrderEvent).where(TruckingOrderEvent.order_id == order.id)
                      .order_by(TruckingOrderEvent.id.desc())).first()
    assert (last.kind, last.reason) == ("REASSIGNED", "Xe hỏng lốp")


def test_reassign_in_planned_rejected(db, world):
    order = service.create_order(db, world.actor, body(world))
    assert code(service.reassign_order, db, world.actor, order.id, world.team.truck.id, world.team.driver.id,
                "lý do") == ("INVALID_TRANSITION", 409)


def test_cancel_from_started_rejected(db, world, make_trucking_order):
    order = make_trucking_order(world.container, events=("ASSIGNED", "STARTED"), team=world.team)
    assert code(service.cancel_order, db, world.actor, order.id, "muộn rồi") == ("INVALID_TRANSITION", 409)


def test_write_ops_record_audit(db, world):
    order = service.create_order(db, world.actor, body(world))
    service.assign_order(db, world.actor, order.id, world.team.truck.id, world.team.driver.id)
    service.cancel_order(db, world.actor, order.id, "Khách hoãn")
    logs = db.scalars(select(AuditLog).where(AuditLog.entity == "trucking_order", AuditLog.entity_id == str(order.id))
                      .order_by(AuditLog.id)).all()
    assert [log.action for log in logs] == ["CREATE", "ASSIGN", "CANCEL"]
    assert logs[1].before["status"] == "PLANNED" and logs[1].after["status"] == "ASSIGNED"
    assert db.get(TruckingOrder, order.id).status == "CANCELLED"
