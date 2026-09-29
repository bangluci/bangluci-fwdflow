from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.shipments.models import ShipmentEvent
from tests.driver_factories import jpeg


def _last_event(db, shipment):
    return db.scalars(select(ShipmentEvent).where(ShipmentEvent.shipment_id == shipment.id)
                      .order_by(ShipmentEvent.id.desc())).first()


def _receive(client, shipment, photo=True, **data):
    files = {"photo": ("cfs.jpg", jpeg(), "image/jpeg")} if photo else None
    return client.post(f"/api/shipments/{shipment.id}/receive-at-warehouse", data=data, files=files)


def _close(client, shipment, photo=True, **data):
    files = {"photo": ("bien-ban.jpg", jpeg(), "image/jpeg")} if photo else None
    return client.post(f"/api/shipments/{shipment.id}/close", data=data, files=files)


def test_lcl_receive_requires_cfs_photo(client, login_as, make_shipment):
    login_as("DISPATCH")
    res = _receive(client, make_shipment(status="CLEARED", load_type="LCL"), photo=False)
    assert res.status_code == 400 and res.json()["error"]["code"] == "EVIDENCE_REQUIRED"


def test_lcl_receive_moves_cleared_to_at_warehouse(client, db, login_as, make_shipment):
    user = login_as("DISPATCH")
    shipment = make_shipment(status="CLEARED", load_type="LCL")
    res = _receive(client, shipment, note="Nhận đủ 100 kiện")
    assert res.status_code == 200 and res.json()["data"]["status"] == "AT_WAREHOUSE"
    event = _last_event(db, shipment)
    assert (event.actor_id, event.to_status, event.reason) == (user.id, "AT_WAREHOUSE", "Nhận đủ 100 kiện")
    assert len(event.photo_sha256) == 64


def test_lcl_receive_rejected_for_fcl(client, login_as, make_shipment):
    login_as("DISPATCH")
    res = _receive(client, make_shipment(status="CLEARED", load_type="FCL"))
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_LCL"
    res = _receive(client, make_shipment(status="ARRIVED", load_type="LCL"))
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_TRANSITION"


def test_lcl_receive_requires_dispatch_role(client, login_as, make_shipment):
    login_as("DOCS")
    assert _receive(client, make_shipment(status="CLEARED", load_type="LCL")).status_code == 403


def test_close_requires_reason_and_photo(client, login_as, make_shipment):
    login_as("DISPATCH")
    shipment = make_shipment(status="AT_WAREHOUSE", load_type="LCL")
    assert _close(client, shipment, reason="abc").status_code == 422
    res = _close(client, shipment, photo=False, reason="Khách không nhận hết")
    assert res.status_code == 400 and res.json()["error"]["code"] == "EVIDENCE_REQUIRED"
    assert client.post(f"/api/shipments/{shipment.id}/close").status_code == 422


def test_close_rejected_with_unfinished_orders(client, login_as, make_shipment, make_last_mile_order):
    login_as("DISPATCH")
    shipment = make_shipment(status="AT_WAREHOUSE", load_type="LCL", total_packages=10)
    make_last_mile_order(shipment, 3, events=("CREATED",))
    res = _close(client, shipment, reason="Khách không nhận hết")
    assert res.status_code == 409 and res.json()["error"]["code"] == "UNFINISHED_ORDERS"


def test_close_rejected_when_container_not_returned(client, login_as, make_shipment, make_container):
    login_as("DISPATCH")
    shipment = make_shipment(status="AT_WAREHOUSE", total_packages=10)
    now = datetime.now(UTC)
    make_container(shipment, milestones={"DISCHARGED": now - timedelta(days=3), "GATE_OUT_FULL": now - timedelta(days=2)})
    res = _close(client, shipment, reason="Khách không nhận hết")
    assert res.status_code == 409 and res.json()["error"]["code"] == "CONTAINERS_NOT_RETURNED"


def test_close_with_undelivered_packages_completes(client, db, login_as, make_shipment, make_container,
                                                   make_last_mile_order):
    user = login_as("DISPATCH")
    shipment = make_shipment(status="AT_WAREHOUSE", total_packages=10)
    now = datetime.now(UTC)
    make_container(shipment, milestones={"DISCHARGED": now - timedelta(days=4), "GATE_OUT_FULL": now - timedelta(days=3),
                                         "EMPTY_RETURNED": now - timedelta(days=2)})
    make_last_mile_order(shipment, 7, events=("CREATED", "ASSIGNED", "PICKED_UP", "DELIVERED"))
    res = _close(client, shipment, reason="Còn 3 kiện khách huỷ nhận")
    assert res.status_code == 200 and res.json()["data"]["status"] == "COMPLETED"
    event = _last_event(db, shipment)
    assert (event.actor_id, event.reason) == (user.id, "Còn 3 kiện khách huỷ nhận") and event.photo_sha256


@pytest.mark.parametrize("status", ["CLEARED", "CANCELLED", "COMPLETED"])
def test_close_rejected_from_other_statuses(client, login_as, make_shipment, status):
    login_as("DISPATCH")
    res = _close(client, make_shipment(status=status), reason="Khách không nhận hết")
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_TRANSITION"
