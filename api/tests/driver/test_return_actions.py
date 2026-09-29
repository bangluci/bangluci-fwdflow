from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.shipments.models import ContainerEvent, Shipment, ShipmentEvent
from app.shipments.service import try_auto_advance
from tests.driver.conftest import discharged_at as _discharged_at
from tests.driver.conftest import jpeg

VN = ZoneInfo("Asia/Ho_Chi_Minh")
RETURN_EVENTS = ("ASSIGNED", "STARTED")


def _left_port(make_container, shipment):
    now = _discharged_at()
    return make_container(shipment, milestones={"DISCHARGED": now, "GATE_OUT_FULL": now + timedelta(hours=6)})


def _kinds(db, container):
    return [e.kind for e in db.scalars(select(ContainerEvent).where(ContainerEvent.container_id == container.id)
                                       .order_by(ContainerEvent.id))]


def test_return_start_needs_no_evidence(client, db, driver, make_shipment, make_container, ready_order, send):
    shipment = make_shipment(status="AT_WAREHOUSE")
    container = _left_port(make_container, shipment)
    made = ready_order("RETURN_EMPTY", shipment=shipment, container=container)
    res = send("RETURN_START", made.order.id)
    assert res.status_code == 200 and res.json()["data"]["status"] == "STARTED"
    db.refresh(made.order)
    assert made.order.status == "STARTED" and _kinds(db, container) == ["DISCHARGED", "GATE_OUT_FULL"]


def test_return_complete_requires_eir_photo_400(client, db, driver, make_shipment, make_container, ready_order, send):
    shipment = make_shipment(status="AT_WAREHOUSE")
    container = _left_port(make_container, shipment)
    made = ready_order("RETURN_EMPTY", events=RETURN_EVENTS, shipment=shipment, container=container)
    res = send("RETURN_COMPLETE", made.order.id)
    assert res.status_code == 400 and res.json()["error"]["code"] == "EVIDENCE_REQUIRED"
    assert "EMPTY_RETURNED" not in _kinds(db, container)


def test_return_complete_writes_empty_returned_and_closes_det(client, db, driver, ft, ready_order, send):
    ft.standard_rules()
    container = ft.container(status="AT_WAREHOUSE", eta="2026-09-01",
                             milestones={"DISCHARGED": "2026-09-24", "GATE_OUT_FULL": "2026-09-26"})
    made = ready_order("RETURN_EMPTY", events=RETURN_EVENTS, shipment=db.get(Shipment, container.shipment_id),
                       container=container)
    assert send("RETURN_COMPLETE", made.order.id, jpeg()).status_code == 200
    db.refresh(made.order)
    today = datetime.now(VN).date()
    assert made.order.status == "COMPLETED" and _kinds(db, container)[-1] == "EMPTY_RETURNED"
    det = ft.rows(today, container)["DET"]
    assert (det["status"], det["returned_date"]) == ("CLOSED", today)


def test_container_to_door_completes_when_all_containers_returned(client, db, driver, make_shipment, make_container,
                                                                  ready_order, send):
    shipment = make_shipment(status="AT_WAREHOUSE", delivery_mode="CONTAINER_TO_DOOR")
    orders = [ready_order("RETURN_EMPTY", events=RETURN_EVENTS, shipment=shipment,
                          container=_left_port(make_container, shipment)) for _ in range(2)]
    assert send("RETURN_COMPLETE", orders[0].order.id, jpeg()).status_code == 200
    assert shipment.status == "AT_WAREHOUSE"
    assert send("RETURN_COMPLETE", orders[1].order.id, jpeg()).status_code == 200
    assert shipment.status == "COMPLETED"
    assert try_auto_advance(db, shipment) is False
    done = db.scalars(select(ShipmentEvent).where(ShipmentEvent.shipment_id == shipment.id,
                                                  ShipmentEvent.to_status == "COMPLETED")).all()
    assert [e.actor_id for e in done] == [None] and done[0].reason == "Tự chuyển: mọi container đã trả rỗng"


def test_via_warehouse_not_completed_by_empty_return_alone(client, db, driver, make_shipment, make_container,
                                                           ready_order, send):
    shipment = make_shipment(status="AT_WAREHOUSE", delivery_mode="VIA_WAREHOUSE")
    made = ready_order("RETURN_EMPTY", events=RETURN_EVENTS, shipment=shipment,
                       container=_left_port(make_container, shipment))
    assert send("RETURN_COMPLETE", made.order.id, jpeg()).status_code == 200
    assert shipment.status == "AT_WAREHOUSE"


def test_duplicate_return_complete_request_returns_first_result(client, db, driver, make_shipment, make_container,
                                                                ready_order, send):
    shipment = make_shipment(status="AT_WAREHOUSE")
    container = _left_port(make_container, shipment)
    made = ready_order("RETURN_EMPTY", events=RETURN_EVENTS, shipment=shipment, container=container)
    request_id = "0b9e6f3c-8d2a-4f57-9c1e-5a7d3b2c4e10"
    first, second = (send("RETURN_COMPLETE", made.order.id, jpeg(), request_id) for _ in range(2))
    assert first.json()["data"]["event_id"] == second.json()["data"]["event_id"]
    assert _kinds(db, container).count("EMPTY_RETURNED") == 1


def test_return_complete_before_start_409(client, driver, ready_order, send):
    made = ready_order("RETURN_EMPTY")
    res = send("RETURN_COMPLETE", made.order.id, jpeg())
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_TRANSITION"
