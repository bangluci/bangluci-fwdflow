from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

VN = ZoneInfo("Asia/Ho_Chi_Minh")
URL = "/api/driver/tasks"


def _at(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), tzinfo=VN)


def test_lists_assigned_today_and_started_any_day(client, driver, today, ready_order):
    early = ready_order(planned_at=_at(today, 8))
    late = ready_order(planned_at=_at(today, 10))
    started = ready_order(events=("ASSIGNED", "STARTED"), planned_at=_at(today - timedelta(days=3), 9))
    ready_order(planned_at=_at(today + timedelta(days=1), 8))  # ngày mai
    ready_order(events=("ASSIGNED", "STARTED", "COMPLETED"), planned_at=_at(today, 7))
    ready_order(events=("CANCELLED",), planned_at=_at(today, 7))
    ready_order(events=(), planned_at=_at(today, 7))  # PLANNED chưa gán
    res = client.get(URL).json()["data"]
    assert [item["id"] for item in res] == [started.order.id, early.order.id, late.order.id]


def test_excludes_other_drivers_orders(client, driver, make_driver, today, ready_order):
    mine = ready_order(planned_at=_at(today, 8))
    ready_order(planned_at=_at(today, 9), team=make_driver().team)
    assert [item["id"] for item in client.get(URL).json()["data"]] == [mine.order.id]


def test_task_item_shape_and_pickup_full_actions(client, driver, today, ready_order):
    made = ready_order(planned_at=_at(today, 8))
    (item,) = client.get(URL).json()["data"]
    assert set(item) == {"kind", "id", "order_kind", "title", "status", "planned_at", "shipment_code",
                         "container_no", "container_type", "seal_no", "pickup_location", "drop_location",
                         "delivery_mode", "actions"}
    assert (item["kind"], item["order_kind"], item["title"], item["status"]) == (
        "TRUCKING", "PICKUP_FULL", "Lấy cont", "ASSIGNED")
    assert item["planned_at"].endswith("+07:00") and item["container_no"] == made.container.container_no
    assert item["actions"] == [{"action": "TRUCK_START", "label": "Đã lấy cont", "requires": ["photo"]}]


@pytest.mark.parametrize(("mode", "requires"), [("CONTAINER_TO_DOOR", ["photo", "signer_name"]),
                                                ("VIA_WAREHOUSE", [])])
def test_complete_requires_photo_and_signer_only_for_container_to_door(client, driver, today, ready_order, mode,
                                                                       requires):
    ready_order(events=("ASSIGNED", "STARTED"), delivery_mode=mode, planned_at=_at(today, 8))
    (item,) = client.get(URL).json()["data"]
    assert item["actions"] == [{"action": "TRUCK_COMPLETE", "label": "Đã tới kho đích", "requires": requires}]


def test_return_empty_actions(client, driver, today, ready_order):
    ready_order("RETURN_EMPTY", planned_at=_at(today, 8))
    ready_order("RETURN_EMPTY", events=("ASSIGNED", "STARTED"), planned_at=_at(today, 9))
    first, second = client.get(URL).json()["data"]
    assert first["title"] == "Trả vỏ rỗng"
    assert first["actions"] == [{"action": "RETURN_START", "label": "Đã nhận vỏ rỗng tại kho", "requires": []}]
    assert second["actions"] == [{"action": "RETURN_COMPLETE", "label": "Đã trả vỏ rỗng", "requires": ["photo"]}]


def test_today_follows_app_as_of_guc(client, db, driver, ready_order):
    db.execute(text("SELECT set_config('app.as_of', '2026-11-25', true)"))
    inside = ready_order(planned_at=datetime.fromisoformat("2026-11-24T17:30:00+00:00"))
    ready_order(planned_at=datetime.fromisoformat("2026-11-25T17:30:00+00:00"))
    assert [item["id"] for item in client.get(URL).json()["data"]] == [inside.order.id]


def test_cancelled_shipment_orders_hidden(client, driver, today, ready_order):
    ready_order(status="CANCELLED", planned_at=_at(today, 8))
    assert client.get(URL).json()["data"] == []


@pytest.mark.parametrize("role", ["ADMIN", "DOCS", "DISPATCH", "ACCOUNTANT", "CUSTOMER"])
def test_non_driver_roles_403_and_anonymous_401(client, login_as, role):
    assert client.get(URL).status_code == 401
    login_as(role)
    res = client.get(URL)
    assert res.status_code == 403 and res.json()["error"]["code"] == "FORBIDDEN"
