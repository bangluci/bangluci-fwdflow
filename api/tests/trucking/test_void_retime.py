from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.shipments.models import ContainerEvent, Shipment, ShipmentEvent
from app.trucking.models import TruckingOrderEvent
from tests.driver_factories import discharged_at, jpeg

VN = ZoneInfo("Asia/Ho_Chi_Minh")


@pytest.fixture
def staff(client, login_as):
    """Đổi phiên sang nhân viên: `staff("DISPATCH")`. Phiên tài xế của `driver` bị thay, nên gọi `send` trước."""

    def _login(role: str):
        return login_as(role)

    return _login


def _event_id(client, order, kind):
    events = client.get(f"/api/trucking-orders/{order.id}").json()["data"]["events"]
    return next(e["id"] for e in reversed(events) if e["kind"] == kind)


def _void(client, order, kind, reason="Ghi nhầm giờ lấy cont"):
    return client.post(f"/api/trucking-orders/{order.id}/events/{_event_id(client, order, kind)}/void",
                       json={"reason": reason})


def _live_milestones(db, container):
    rows = db.scalars(select(ContainerEvent).where(ContainerEvent.container_id == container.id)).all()
    voided = {e.adjusts_event_id for e in rows if e.kind == "VOID"}
    return [e.kind for e in rows if e.kind not in ("VOID", "RETIME") and e.id not in voided]


def test_void_start_reverts_order_and_gate_out(client, db, driver, staff, ft, ready_order, send):
    ft.standard_rules()
    container = ft.container(status="CLEARED", eta="2026-09-01", milestones={"DISCHARGED": "2026-09-25"})
    made = ready_order(shipment=db.get(Shipment, container.shipment_id), container=container)
    assert send("TRUCK_START", made.order.id, jpeg()).status_code == 200
    today = datetime.now(VN).date()
    assert ft.rows(today, container)["DEM"]["status"] == "CLOSED"
    staff("DISPATCH")
    res = _void(client, made.order, "STARTED")
    assert res.status_code == 200 and res.json()["data"]["status"] == "ASSIGNED"
    assert _live_milestones(db, container) == ["DISCHARGED"]
    assert ft.rows(today, container)["DEM"]["status"] == "OPEN"


def test_void_complete_reverts_at_warehouse(client, db, driver, staff, ready_order, send):
    made = ready_order(events=("ASSIGNED", "STARTED"))
    assert send("TRUCK_COMPLETE", made.order.id).status_code == 200
    assert made.shipment.status == "AT_WAREHOUSE"
    staff("DISPATCH")
    assert _void(client, made.order, "COMPLETED").json()["data"]["status"] == "STARTED"
    db.refresh(made.shipment)
    assert made.shipment.status == "CLEARED"
    void = db.scalars(select(ShipmentEvent).where(ShipmentEvent.shipment_id == made.shipment.id,
                                                  ShipmentEvent.kind == "VOID")).one()
    assert void.actor_id is None and void.reason.startswith("Đảo do huỷ event #")


def test_void_empty_return_reverts_container_to_door_completed(client, db, driver, staff, ready_order, send,
                                                               make_trucking_order):
    made = ready_order(events=("ASSIGNED",), delivery_mode="CONTAINER_TO_DOOR")
    assert send("TRUCK_START", made.order.id, jpeg()).status_code == 200
    assert send("TRUCK_COMPLETE", made.order.id, jpeg(), signer_name="Nguyễn Văn A").status_code == 200
    assert made.shipment.status == "AT_WAREHOUSE"
    back = make_trucking_order(made.container, "RETURN_EMPTY", events=("ASSIGNED",), team=driver.team)
    assert send("RETURN_START", back.id).status_code == 200
    assert send("RETURN_COMPLETE", back.id, jpeg()).status_code == 200
    assert made.shipment.status == "COMPLETED"
    staff("DISPATCH")
    assert _void(client, back, "COMPLETED").status_code == 200
    db.refresh(made.shipment)
    assert made.shipment.status == "AT_WAREHOUSE"
    assert _live_milestones(db, made.container) == ["DISCHARGED", "GATE_OUT_FULL"]


def test_void_only_latest_event(client, staff, driver, ready_order):
    made = ready_order(events=("ASSIGNED", "STARTED", "COMPLETED"))
    staff("DISPATCH")
    res = _void(client, made.order, "STARTED")
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_LATEST_EVENT"
    assert _void(client, made.order, "ASSIGNED").json()["error"]["code"] == "NOT_LATEST_EVENT"


def test_void_assigned_event_not_voidable(client, staff, driver, ready_order):
    made = ready_order(events=("ASSIGNED",))
    staff("DISPATCH")
    res = _void(client, made.order, "ASSIGNED")
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_VOIDABLE"


def test_void_pickup_complete_blocked_by_return_order(client, staff, driver, ready_order, make_trucking_order):
    made = ready_order(events=("ASSIGNED", "STARTED", "COMPLETED"))
    make_trucking_order(made.container, "RETURN_EMPTY", events=("ASSIGNED",), team=driver.team)
    staff("DISPATCH")
    res = _void(client, made.order, "COMPLETED")
    assert res.status_code == 409 and res.json()["error"]["code"] == "DEPENDENT_ORDER_EXISTS"


@pytest.mark.parametrize("reason", ["", "   ", "abc"])
def test_void_requires_reason(client, staff, driver, ready_order, reason):
    made = ready_order(events=("ASSIGNED", "STARTED"))
    staff("DISPATCH")
    res = _void(client, made.order, "STARTED", reason)
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("role", ["DOCS", "DRIVER"])
def test_void_requires_dispatch_role(client, staff, driver, ready_order, role):
    made = ready_order(events=("ASSIGNED", "STARTED"))
    staff(role)  # quyền được kiểm trước khi tra event nên id nào cũng được
    res = client.post(f"/api/trucking-orders/{made.order.id}/events/1/void", json={"reason": "Ghi nhầm giờ"})
    assert res.status_code == 403


def _retime(client, order, kind, when, reason="Chỉnh theo phiếu EIR"):
    return client.post(f"/api/trucking-orders/{order.id}/events/{_event_id(client, order, kind)}/retime",
                       json={"occurred_at": when.isoformat(), "reason": reason})


def test_retime_gate_out_updates_freetime(client, db, driver, staff, ft, ready_order, send):
    ft.standard_rules()
    container = ft.container(status="CLEARED", eta="2026-09-01", milestones={"DISCHARGED": "2026-09-25"})
    made = ready_order(shipment=db.get(Shipment, container.shipment_id), container=container)
    assert send("TRUCK_START", made.order.id, jpeg()).status_code == 200
    today = datetime.now(VN).date()
    before = ft.rows(today, container)["DEM"]["days_used"]
    staff("DOCS")
    res = _retime(client, made.order, "STARTED", datetime.now(UTC) - timedelta(days=1))
    assert res.status_code == 200
    assert ft.rows(today, container)["DEM"]["days_used"] == before - 1


def test_retime_breaking_milestone_order_rejected(client, db, driver, staff, ready_order, send):
    made = ready_order()
    assert send("TRUCK_START", made.order.id, jpeg()).status_code == 200
    staff("DOCS")
    res = _retime(client, made.order, "STARTED", discharged_at() - timedelta(days=1))
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_MILESTONE_ORDER"
    kinds = [e.kind for e in db.scalars(select(TruckingOrderEvent).where(TruckingOrderEvent.order_id == made.order.id))]
    assert "RETIME" not in kinds


def test_retime_future_time_rejected(client, driver, staff, ready_order, send):
    made = ready_order()
    assert send("TRUCK_START", made.order.id, jpeg()).status_code == 200
    staff("DOCS")
    res = _retime(client, made.order, "STARTED", datetime.now(UTC) + timedelta(hours=1))
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_retime_requires_docs_role(client, driver, staff, ready_order, send):
    made = ready_order()
    assert send("TRUCK_START", made.order.id, jpeg()).status_code == 200
    staff("DISPATCH")
    res = client.post(f"/api/trucking-orders/{made.order.id}/events/1/retime",
                      json={"occurred_at": datetime.now(UTC).isoformat(), "reason": "Chỉnh giờ"})
    assert res.status_code == 403
