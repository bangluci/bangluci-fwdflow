import pytest
from sqlalchemy import select

from app.shipments.models import ShipmentEvent
from tests.driver_factories import jpeg

ORDERS = "/api/last-mile-orders"
PICKED = ("CREATED", "ASSIGNED", "PICKED_UP")


def _void(client, order, kind, reason="Ghi nhầm trạng thái giao"):
    events = client.get(f"{ORDERS}/{order.id}").json()["data"]["events"]
    event_id = next(e["id"] for e in reversed(events) if e["kind"] == kind)
    return client.post(f"{ORDERS}/{order.id}/events/{event_id}/void", json={"reason": reason})


def test_void_delivered_reverts_completed(client, db, driver, login_as, make_shipment, make_last_mile_order, send):
    shipment = make_shipment(status="DELIVERING", load_type="LCL", total_packages=10)
    order = make_last_mile_order(shipment, 10, events=PICKED, driver=driver)
    assert send("LM_DELIVER", order.id, jpeg()).status_code == 200 and shipment.status == "COMPLETED"
    login_as("DISPATCH")
    res = _void(client, order, "DELIVERED")
    assert res.status_code == 200 and res.json()["data"]["status"] == "PICKED_UP"
    db.refresh(shipment)
    assert shipment.status == "DELIVERING"
    void = db.scalars(select(ShipmentEvent).where(ShipmentEvent.shipment_id == shipment.id,
                                                  ShipmentEvent.kind == "VOID")).one()
    assert void.actor_id is None and void.reason.startswith("Đảo do huỷ event #")


def test_void_pick_up_reverts_delivering(client, db, driver, login_as, make_shipment, make_last_mile_order, send):
    shipment = make_shipment(status="AT_WAREHOUSE", load_type="LCL", total_packages=10)
    order = make_last_mile_order(shipment, 4, events=("CREATED", "ASSIGNED"), driver=driver)
    assert send("LM_PICK_UP", order.id).status_code == 200 and shipment.status == "DELIVERING"
    login_as("DISPATCH")
    assert _void(client, order, "PICKED_UP").json()["data"]["status"] == "ASSIGNED"
    db.refresh(shipment)
    assert shipment.status == "AT_WAREHOUSE"


def test_void_only_latest_event(client, login_as, make_shipment, make_last_mile_order):
    login_as("DISPATCH")
    shipment = make_shipment(status="DELIVERING", load_type="LCL", total_packages=10)
    order = make_last_mile_order(shipment, 4, events=(*PICKED, "DELIVERED"))
    res = _void(client, order, "PICKED_UP")
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_LATEST_EVENT"
    res = _void(client, make_last_mile_order(shipment, 2, events=("CREATED", "ASSIGNED")), "ASSIGNED")
    assert res.status_code == 409 and res.json()["error"]["code"] == "NOT_VOIDABLE"


@pytest.mark.parametrize("role", ["DRIVER", "DOCS"])
def test_void_requires_dispatch_role(client, login_as, make_shipment, make_last_mile_order, role):
    shipment = make_shipment(status="DELIVERING", load_type="LCL", total_packages=10)
    order = make_last_mile_order(shipment, 4, events=PICKED)
    login_as(role)
    assert client.post(f"{ORDERS}/{order.id}/events/1/void", json={"reason": "Ghi nhầm giờ"}).status_code == 403
