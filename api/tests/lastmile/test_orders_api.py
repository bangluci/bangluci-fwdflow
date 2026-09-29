from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.audit.models import AuditLog

ORDERS = "/api/last-mile-orders"


@pytest.fixture
def today(db):
    return db.scalar(text("SELECT nlq_today()"))


def _order(today, packages=6, **extra):
    return {"recipient_name": "Nguyễn Văn An", "recipient_phone": "0901 234 567", "address": "12 Lê Lợi, Quận 1",
            "packages": packages, "planned_date": today.isoformat(), **extra}


def _split(client, shipment, *orders):
    return client.post(f"/api/shipments/{shipment.id}/last-mile-orders", json={"orders": list(orders)})


@pytest.fixture
def warehouse_shipment(make_shipment):
    return make_shipment(status="AT_WAREHOUSE", total_packages=10)


def test_split_creates_orders_with_codes_and_created_events(client, login_as, warehouse_shipment, today):
    login_as("DISPATCH")
    res = _split(client, warehouse_shipment, _order(today, 6), _order(today, 4))
    assert res.status_code == 201
    orders = res.json()["data"]
    assert [o["status"] for o in orders] == ["CREATED", "CREATED"]
    assert orders[0]["tracking_code"] != orders[1]["tracking_code"] and orders[0]["recipient_phone"] == "0901234567"
    assert [e["kind"] for e in orders[0]["events"]] == ["CREATED"]
    meta = client.get(ORDERS, params={"shipment_id": warehouse_shipment.id}).json()["meta"]
    assert meta == {"total_packages": 10, "packages_available": 0}


def test_split_with_driver_writes_assigned_event(client, login_as, warehouse_shipment, today, make_driver):
    login_as("DISPATCH")
    driver = make_driver()
    (order,) = _split(client, warehouse_shipment, _order(today, 3, driver_id=driver.team.driver.id)).json()["data"]
    assert order["status"] == "ASSIGNED" and [e["kind"] for e in order["events"]] == ["CREATED", "ASSIGNED"]


def test_split_rejects_container_to_door(client, login_as, make_shipment, today):
    login_as("DISPATCH")
    shipment = make_shipment(status="AT_WAREHOUSE", delivery_mode="CONTAINER_TO_DOOR", total_packages=10)
    res = _split(client, shipment, _order(today, 1))
    assert res.status_code == 409 and res.json()["error"]["code"] == "WRONG_DELIVERY_MODE"


def test_split_rejects_before_at_warehouse(client, login_as, make_shipment, today):
    login_as("DISPATCH")
    res = _split(client, make_shipment(status="CLEARED", total_packages=10), _order(today, 1))
    assert res.status_code == 409 and res.json()["error"]["code"] == "SHIPMENT_NOT_AT_WAREHOUSE"


def test_split_exceeding_package_pool_rejected(client, login_as, warehouse_shipment, today):
    login_as("DISPATCH")
    res = _split(client, warehouse_shipment, _order(today, 6), _order(today, 5))
    assert res.status_code == 409 and res.json()["error"]["code"] == "PACKAGES_EXCEEDED"
    assert res.json()["error"]["details"] == {"available": 10}
    assert client.get(ORDERS, params={"shipment_id": warehouse_shipment.id}).json()["data"] == []


def test_cancelled_and_returned_packages_back_to_pool(client, login_as, warehouse_shipment, today):
    login_as("DISPATCH")
    first, second = _split(client, warehouse_shipment, _order(today, 6), _order(today, 4)).json()["data"]
    assert client.post(f"{ORDERS}/{first['id']}/cancel", json={"reason": "Khách hoãn nhận"}).status_code == 200
    meta = client.get(ORDERS, params={"shipment_id": warehouse_shipment.id}).json()["meta"]
    assert meta["packages_available"] == 6
    assert _split(client, warehouse_shipment, _order(today, 6)).status_code == 201
    assert second["status"] == "CREATED"


def test_assign_then_reassign_requires_reason(client, login_as, warehouse_shipment, today, make_driver):
    login_as("DISPATCH")
    (order,) = _split(client, warehouse_shipment, _order(today, 2)).json()["data"]
    first, second = make_driver(), make_driver()
    url = f"{ORDERS}/{order['id']}"
    assigned = client.post(f"{url}/assign", json={"driver_id": first.team.driver.id, "planned_date": str(today)})
    assert assigned.json()["data"]["status"] == "ASSIGNED"
    body = {"driver_id": second.team.driver.id, "planned_date": str(today + timedelta(days=1))}
    assert client.post(f"{url}/reassign", json={**body, "reason": "   "}).status_code == 422
    res = client.post(f"{url}/reassign", json={**body, "reason": "Xe hỏng giữa đường"})
    data = res.json()["data"]
    assert (data["status"], data["driver_id"]) == ("ASSIGNED", second.team.driver.id)
    assert data["planned_date"] == str(today + timedelta(days=1))
    assert [e["kind"] for e in data["events"]] == ["CREATED", "ASSIGNED", "REASSIGNED"]


def test_failed_order_can_be_reassigned_or_returned(client, login_as, warehouse_shipment, today, make_driver,
                                                    make_last_mile_order):
    login_as("DISPATCH")
    events = ("CREATED", "ASSIGNED", "PICKED_UP", "FAILED")
    retry, back = (make_last_mile_order(warehouse_shipment, 2, events=events) for _ in range(2))
    driver = make_driver()
    res = client.post(f"{ORDERS}/{retry.id}/assign", json={"driver_id": driver.team.driver.id,
                                                            "planned_date": str(today)})
    assert res.json()["data"]["status"] == "ASSIGNED"
    res = client.post(f"{ORDERS}/{back.id}/return", json={"reason": "Người nhận từ chối"})
    assert res.json()["data"]["status"] == "RETURNED"
    assert client.post(f"{ORDERS}/{back.id}/cancel", json={"reason": "Không còn hợp lệ"}).status_code == 409


def test_invalid_driver_and_past_date_rejected(client, login_as, warehouse_shipment, today, make_driver):
    login_as("DISPATCH")
    res = _split(client, warehouse_shipment, _order(today, 1, driver_id=999_999))
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_DRIVER"
    res = _split(client, warehouse_shipment, _order(today - timedelta(days=1), 1))
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_PLANNED_DATE"
    for bad in ({"recipient_phone": "12345"}, {"address": "abc"}, {"packages": 0}):
        res = _split(client, warehouse_shipment, {**_order(today, 1), **bad})
        assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_docs_cannot_split_orders(client, login_as, warehouse_shipment, today):
    login_as("DOCS")
    assert _split(client, warehouse_shipment, _order(today, 1)).status_code == 403
    assert client.get(ORDERS).status_code == 200
    login_as("ACCOUNTANT")
    assert client.get(ORDERS).status_code == 200


def test_split_writes_audit_without_raw_phone(client, db, login_as, warehouse_shipment, today):
    login_as("DISPATCH")
    assert _split(client, warehouse_shipment, _order(today, 1)).status_code == 201
    rows = db.scalars(select(AuditLog).where(AuditLog.entity == "last_mile_order")).all()
    assert len(rows) == 1 and "0901234567" not in str(rows[0].after) and "Lê Lợi" not in str(rows[0].after)


def test_search_by_tracking_code_normalizes(client, login_as, warehouse_shipment, today):
    login_as("DISPATCH")
    (order,) = _split(client, warehouse_shipment, _order(today, 1)).json()["data"]
    code = order["tracking_code"].lower()
    found = client.get(ORDERS, params={"tracking_code": f"{code[:5]}-{code[5:]}"}).json()["data"]
    assert [o["id"] for o in found] == [order["id"]]
    assert client.get(ORDERS, params={"tracking_code": "###"}).json()["data"] == []
