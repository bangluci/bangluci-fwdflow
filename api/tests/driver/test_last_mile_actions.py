from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.lastmile.models import LastMileEvent
from tests.driver_factories import jpeg

TASKS = "/api/driver/tasks"
ASSIGNED = ("CREATED", "ASSIGNED")
PICKED = ("CREATED", "ASSIGNED", "PICKED_UP")


@pytest.fixture
def shipment(make_shipment):
    return make_shipment(status="DELIVERING", total_packages=20)


def _kinds(db, order):
    return [e.kind for e in db.scalars(select(LastMileEvent).where(LastMileEvent.order_id == order.id)
                                       .order_by(LastMileEvent.id))]


def test_driver_tasks_include_today_last_mile_orders(client, driver, shipment, today, make_last_mile_order):
    mine = make_last_mile_order(shipment, 2, events=ASSIGNED, driver=driver, planned_date=today)
    old_pick = make_last_mile_order(shipment, 3, events=PICKED, driver=driver, planned_date=today - timedelta(days=2))
    make_last_mile_order(shipment, 1, events=ASSIGNED, driver=driver, planned_date=today + timedelta(days=1))
    make_last_mile_order(shipment, 1, events=(*PICKED, "DELIVERED"), driver=driver, planned_date=today)
    make_last_mile_order(shipment, 1, events=ASSIGNED, planned_date=today)  # tài xế khác
    items = [i for i in client.get(TASKS).json()["data"] if i["kind"] == "LAST_MILE"]
    assert [i["id"] for i in items] == [old_pick.id, mine.id]
    first = items[1]
    assert set(first) == {"kind", "id", "status", "planned_date", "tracking_code", "shipment_code", "recipient_name",
                          "recipient_phone", "address", "packages", "weight_kg", "actions"}
    assert first["actions"] == [{"action": "LM_PICK_UP", "label": "Đã lấy hàng", "requires": []}]
    assert {a["action"]: a["requires"] for a in items[0]["actions"]} == {"LM_DELIVER": ["photo"],
                                                                        "LM_FAIL": ["reason"]}


def test_pick_up_then_deliver_with_pod_photo(client, db, driver, shipment, make_last_mile_order, send):
    order = make_last_mile_order(shipment, 2, events=ASSIGNED, driver=driver)
    assert send("LM_PICK_UP", order.id).json()["data"]["status"] == "PICKED_UP"
    res = send("LM_DELIVER", order.id, jpeg())
    assert res.status_code == 200 and res.json()["data"]["target_kind"] == "LAST_MILE"
    assert _kinds(db, order) == [*ASSIGNED, "PICKED_UP", "DELIVERED"] and order.status == "DELIVERED"
    delivered = db.scalars(select(LastMileEvent).where(LastMileEvent.kind == "DELIVERED")).one()
    assert len(delivered.photo_sha256) == 64 and delivered.actor_id == driver.user.id


def test_deliver_requires_pod_photo(client, db, driver, shipment, make_last_mile_order, send):
    order = make_last_mile_order(shipment, 2, events=PICKED, driver=driver)
    res = send("LM_DELIVER", order.id)
    assert res.status_code == 400 and res.json()["error"]["code"] == "EVIDENCE_REQUIRED"
    assert "DELIVERED" not in _kinds(db, order)


def test_fail_requires_reason(client, db, driver, shipment, make_last_mile_order, send):
    order = make_last_mile_order(shipment, 2, events=PICKED, driver=driver)
    res = send("LM_FAIL", order.id)
    assert res.status_code == 400 and res.json()["error"]["details"]["missing"] == ["reason"]
    assert send("LM_FAIL", order.id, reason="Người nhận vắng nhà").json()["data"]["status"] == "FAILED"
    failed = db.scalars(select(LastMileEvent).where(LastMileEvent.kind == "FAILED")).one()
    assert failed.reason == "Người nhận vắng nhà"


def test_deliver_without_gps_stores_null_coordinates(client, db, driver, shipment, make_last_mile_order, send):
    order = make_last_mile_order(shipment, 2, events=PICKED, driver=driver)
    assert send("LM_DELIVER", order.id, jpeg()).status_code == 200
    delivered = db.scalars(select(LastMileEvent).where(LastMileEvent.kind == "DELIVERED")).one()
    assert (delivered.lat, delivered.lng) == (None, None)


def test_deliver_with_gps_stores_coordinates(client, db, driver, shipment, make_last_mile_order, send):
    order = make_last_mile_order(shipment, 2, events=PICKED, driver=driver)
    assert send("LM_DELIVER", order.id, jpeg(), lat="10.7769", lng="106.7009").status_code == 200
    delivered = db.scalars(select(LastMileEvent).where(LastMileEvent.kind == "DELIVERED")).one()
    assert (float(delivered.lat), float(delivered.lng)) == (10.7769, 106.7009)


def test_duplicate_deliver_request_returns_first_result(client, db, driver, shipment, make_last_mile_order, send):
    order = make_last_mile_order(shipment, 2, events=PICKED, driver=driver)
    request_id = str(uuid4())
    first, second = (send("LM_DELIVER", order.id, jpeg(), request_id) for _ in range(2))
    assert first.json()["data"]["event_id"] == second.json()["data"]["event_id"]
    assert second.json()["meta"]["replayed"] is True and _kinds(db, order).count("DELIVERED") == 1


def test_reassigned_order_returns_404_for_previous_driver(client, db, driver, make_driver, shipment,
                                                          make_last_mile_order, send):
    order = make_last_mile_order(shipment, 2, events=ASSIGNED, driver=driver)
    order.driver_id = make_driver().team.driver.id
    db.flush()
    res = send("LM_PICK_UP", order.id)
    assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"


def test_deliver_before_pick_up_rejected(client, driver, shipment, make_last_mile_order, send):
    order = make_last_mile_order(shipment, 2, events=ASSIGNED, driver=driver)
    res = send("LM_DELIVER", order.id, jpeg())
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_TRANSITION"


def test_request_id_from_trucking_cannot_be_reused_for_last_mile(client, driver, shipment, make_last_mile_order,
                                                                 ready_order, send):
    truck = ready_order()
    order = make_last_mile_order(shipment, 2, events=ASSIGNED, driver=driver)
    request_id = str(uuid4())
    assert send("TRUCK_START", truck.order.id, jpeg(), request_id).status_code == 200
    res = send("LM_PICK_UP", order.id, request_id=request_id)
    assert res.status_code == 409 and res.json()["error"]["code"] == "DUPLICATE_REQUEST_ID"
