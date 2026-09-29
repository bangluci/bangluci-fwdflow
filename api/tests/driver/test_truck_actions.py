from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.shipments.models import ContainerEvent, Shipment, ShipmentEvent
from app.trucking.models import TruckingOrderEvent
from tests.driver.conftest import discharged_at, jpeg

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _container_events(db, container, kind):
    return db.scalars(select(ContainerEvent).where(ContainerEvent.container_id == container.id,
                                                   ContainerEvent.kind == kind)).all()


def _order_events(db, order, kind=None):
    stmt = select(TruckingOrderEvent).where(TruckingOrderEvent.order_id == order.id).order_by(TruckingOrderEvent.id)
    return [e for e in db.scalars(stmt) if kind is None or e.kind == kind]


def test_truck_start_writes_started_and_gate_out_full_with_same_time(client, db, driver, ready_order, send):
    made = ready_order()
    res = send("TRUCK_START", made.order.id, jpeg())
    assert res.status_code == 200 and res.json()["data"]["status"] == "STARTED"
    db.refresh(made.order)
    (gate_out,) = _container_events(db, made.container, "GATE_OUT_FULL")
    (started,) = _order_events(db, made.order, "STARTED")
    assert made.order.status == "STARTED" and gate_out.occurred_at == started.occurred_at


def test_start_without_photo_400_evidence_required(client, db, driver, ready_order, send):
    made = ready_order()
    res = send("TRUCK_START", made.order.id)
    assert res.status_code == 400 and res.json()["error"]["code"] == "EVIDENCE_REQUIRED"
    assert _order_events(db, made.order, "STARTED") == [] and _container_events(db, made.container, "GATE_OUT_FULL") == []


def test_duplicate_gate_out_request_returns_first_result(client, db, driver, ready_order, send):
    made = ready_order()
    request_id = "6f1b4a52-3f0e-4c0c-9a55-1d2b7f0c9a11"
    first, second = (send("TRUCK_START", made.order.id, jpeg(), request_id) for _ in range(2))
    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json()["data"]["event_id"] == second.json()["data"]["event_id"]
    assert len(_container_events(db, made.container, "GATE_OUT_FULL")) == 1
    assert len(_order_events(db, made.order, "STARTED")) == 1


@pytest.mark.parametrize(("status", "discharged", "code"), [("ARRIVED", True, "SHIPMENT_NOT_CLEARED"),
                                                            ("CLEARED", False, "NOT_DISCHARGED")])
def test_start_requires_shipment_cleared_and_container_discharged(client, driver, make_shipment, make_container,
                                                                  ready_order, send, status, discharged, code):
    shipment = make_shipment(status=status)
    container = make_container(shipment, milestones={"DISCHARGED": discharged_at()} if discharged else None)
    made = ready_order(shipment=shipment, container=container)
    res = send("TRUCK_START", made.order.id, jpeg())
    assert res.status_code == 409 and res.json()["error"]["code"] == code


def test_complete_before_start_409(client, driver, ready_order, send):
    made = ready_order()
    res = send("TRUCK_COMPLETE", made.order.id)
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_TRANSITION"


def test_complete_via_warehouse_needs_no_evidence(client, db, driver, ready_order, send):
    made = ready_order(events=("ASSIGNED", "STARTED"))
    assert send("TRUCK_COMPLETE", made.order.id).status_code == 200
    db.refresh(made.order)
    assert made.order.status == "COMPLETED"


@pytest.mark.parametrize(("fields", "with_photo", "missing"), [
    ({"signer_name": "Nguyễn Văn A"}, False, ["photo"]),
    ({}, True, ["signer_name"]),
    ({"signer_name": "   "}, True, ["signer_name"]),
])
def test_complete_container_to_door_requires_photo_and_signer(client, db, driver, ready_order, send, fields,
                                                              with_photo, missing):
    made = ready_order(events=("ASSIGNED", "STARTED"), delivery_mode="CONTAINER_TO_DOOR")
    res = send("TRUCK_COMPLETE", made.order.id, jpeg() if with_photo else None, **fields)
    assert res.status_code == 400 and res.json()["error"]["details"]["missing"] == missing
    db.refresh(made.order)
    assert made.order.status == "STARTED"


def test_complete_container_to_door_stores_pod_and_signer(client, db, driver, ready_order, send):
    made = ready_order(events=("ASSIGNED", "STARTED"), delivery_mode="CONTAINER_TO_DOOR")
    assert send("TRUCK_COMPLETE", made.order.id, jpeg(), signer_name="Nguyễn Văn A").status_code == 200
    (done,) = _order_events(db, made.order, "COMPLETED")
    assert len(done.photo_sha256) == 64 and done.signer_name == "Nguyễn Văn A"


def test_last_pickup_completed_moves_shipment_to_at_warehouse_once(client, db, driver, make_shipment,
                                                                   make_container, ready_order, send):
    shipment = make_shipment(status="CLEARED")
    first = ready_order(shipment=shipment, container=make_container(shipment, milestones={"DISCHARGED": discharged_at()}),
                        events=("ASSIGNED", "STARTED"))
    second = ready_order(shipment=shipment, container=make_container(shipment, milestones={"DISCHARGED": discharged_at()}),
                         events=("ASSIGNED", "STARTED"))
    assert send("TRUCK_COMPLETE", first.order.id).status_code == 200
    assert shipment.status == "CLEARED"
    assert send("TRUCK_COMPLETE", second.order.id).status_code == 200
    assert shipment.status == "AT_WAREHOUSE"
    moves = db.scalars(select(ShipmentEvent).where(ShipmentEvent.shipment_id == shipment.id,
                                                   ShipmentEvent.to_status == "AT_WAREHOUSE")).all()
    assert [m.actor_id for m in moves] == [None]


def test_gate_out_closes_dem_and_opens_det(client, db, driver, ft, ready_order, send):
    ft.standard_rules()
    container = ft.container(status="CLEARED", eta="2026-09-01", milestones={"DISCHARGED": "2026-09-25"})
    made = ready_order(shipment=db.get(Shipment, container.shipment_id), container=container)
    assert send("TRUCK_START", made.order.id, jpeg()).status_code == 200
    today = datetime.now(VN).date()
    rows = ft.rows(today, container)
    assert (rows["DEM"]["status"], rows["DEM"]["end_date"]) == ("CLOSED", today)
    assert (rows["DET"]["status"], rows["DET"]["start_date"]) == ("OPEN", today)


def test_start_on_order_of_other_driver_404(client, db, driver, make_driver, switch_to, ready_order, send):
    made = ready_order()
    other = make_driver()
    switch_to(other.user)
    assert send("TRUCK_START", made.order.id, jpeg()).status_code == 404
    made.order.driver_id, made.order.truck_id = other.team.driver.id, other.team.truck.id
    db.flush()
    switch_to(driver.user)
    res = send("TRUCK_START", made.order.id, jpeg())
    assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"


def test_start_writes_audit_rows(client, db, driver, ready_order, send):
    made = ready_order()
    assert send("TRUCK_START", made.order.id, jpeg(), lat="10.7769", lng="106.7009",
                signer_name="Trần B").status_code == 200
    rows = db.scalars(select(AuditLog).where(AuditLog.actor_id == driver.user.id)).all()
    pairs = {(r.action, r.entity) for r in rows}
    assert {("CREATE", "trucking_order_event"), ("CREATE", "container_event"), ("UPDATE", "trucking_order")} <= pairs
    event_audit = next(r for r in rows if r.entity == "trucking_order_event")
    assert event_audit.after["lat"] == "***" and event_audit.after["signer_name"] == "***"


def test_gate_out_before_discharge_time_409(client, db, driver, make_shipment, make_container, ready_order, send):
    shipment = make_shipment(status="CLEARED")
    container = make_container(shipment, milestones={"DISCHARGED": datetime.now(UTC) + timedelta(hours=1)})
    made = ready_order(shipment=shipment, container=container)
    res = send("TRUCK_START", made.order.id, jpeg())
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_MILESTONE_ORDER"
    assert _order_events(db, made.order, "STARTED") == []
