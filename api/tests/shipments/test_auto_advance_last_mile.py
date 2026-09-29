from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.lastmile.schemas import OrderIn
from app.lastmile.service import create_orders, return_order
from app.shipments.auto_advance import try_auto_advance
from app.shipments.models import ContainerEvent, ShipmentEvent
from tests.driver_factories import jpeg

PICKED = ("CREATED", "ASSIGNED", "PICKED_UP")


def _completed_events(db, shipment):
    return db.scalar(select(func.count()).select_from(ShipmentEvent).where(
        ShipmentEvent.shipment_id == shipment.id, ShipmentEvent.to_status == "COMPLETED"))


def test_first_pick_up_moves_delivering(client, driver, make_shipment, make_last_mile_order, send):
    shipment = make_shipment(status="AT_WAREHOUSE", total_packages=10)
    order = make_last_mile_order(shipment, 5, events=("CREATED", "ASSIGNED"), driver=driver)
    assert send("LM_PICK_UP", order.id).status_code == 200
    assert shipment.status == "DELIVERING"


def test_partial_packages_delivered_not_completed(client, driver, make_shipment, make_last_mile_order, send):
    shipment = make_shipment(status="DELIVERING", total_packages=10, load_type="LCL")
    order = make_last_mile_order(shipment, 6, events=PICKED, driver=driver)
    assert send("LM_DELIVER", order.id, jpeg()).status_code == 200
    assert shipment.status == "DELIVERING"


def test_shipment_without_orders_never_auto_completes(db, make_shipment):
    shipment = make_shipment(status="AT_WAREHOUSE", load_type="LCL", total_packages=10)
    assert try_auto_advance(db, shipment) is False and shipment.status == "AT_WAREHOUSE"


def test_all_delivered_waits_for_empty_return_fcl(client, db, driver, make_shipment, make_container,
                                                  make_last_mile_order, send):
    shipment = make_shipment(status="DELIVERING", total_packages=10)
    now = datetime.now(UTC)
    container = make_container(shipment, milestones={"DISCHARGED": now - timedelta(days=4),
                                                    "GATE_OUT_FULL": now - timedelta(days=3)})
    order = make_last_mile_order(shipment, 10, events=PICKED, driver=driver)
    assert send("LM_DELIVER", order.id, jpeg()).status_code == 200
    assert shipment.status == "DELIVERING"
    db.add(ContainerEvent(container_id=container.id, kind="EMPTY_RETURNED", occurred_at=now - timedelta(days=1)))
    db.flush()
    assert try_auto_advance(db, shipment) is True and shipment.status == "COMPLETED"


def test_lcl_all_delivered_completes(client, db, driver, make_shipment, make_last_mile_order, send):
    shipment = make_shipment(status="DELIVERING", load_type="LCL", total_packages=10)
    first = make_last_mile_order(shipment, 6, events=PICKED, driver=driver)
    second = make_last_mile_order(shipment, 4, events=PICKED, driver=driver)
    assert send("LM_DELIVER", first.id, jpeg()).status_code == 200 and shipment.status == "DELIVERING"
    assert send("LM_DELIVER", second.id, jpeg()).status_code == 200
    assert shipment.status == "COMPLETED" and _completed_events(db, shipment) == 1


def test_returned_order_blocks_completion_until_resplit(client, db, driver, make_user, make_shipment,
                                                        make_last_mile_order, send, today):
    shipment = make_shipment(status="DELIVERING", load_type="LCL", total_packages=10)
    done = make_last_mile_order(shipment, 6, events=PICKED, driver=driver)
    back = make_last_mile_order(shipment, 4, events=(*PICKED, "FAILED"), driver=driver)
    assert send("LM_DELIVER", done.id, jpeg()).status_code == 200
    assert shipment.status == "DELIVERING"  # còn đơn FAILED dở
    return_order(db, make_user("DISPATCH"), back.id, "Người nhận từ chối")
    try_auto_advance(db, shipment)
    assert shipment.status == "DELIVERING"  # 6 / 10 kiện đã giao, quỹ kiện trả lại 4
    (again,) = create_orders(db, make_user("DISPATCH"), shipment.id, [OrderIn(
        recipient_name="Trần B", recipient_phone="0912345678", address="99 Nguyễn Trãi, Q5", packages=4,
        planned_date=today, driver_id=driver.team.driver.id)])
    assert send("LM_PICK_UP", again.id).status_code == 200
    assert send("LM_DELIVER", again.id, jpeg()).status_code == 200
    assert shipment.status == "COMPLETED"


def test_delivered_events_do_not_double_count_completion(db, make_shipment, make_last_mile_order):
    shipment = make_shipment(status="DELIVERING", load_type="LCL", total_packages=4)
    make_last_mile_order(shipment, 4, events=(*PICKED, "DELIVERED"))
    assert [try_auto_advance(db, shipment), try_auto_advance(db, shipment)] == [True, False]
    assert _completed_events(db, shipment) == 1
