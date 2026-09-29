import re

from sqlalchemy import select

from app.audit.models import AuditLog
from app.catalog.models import Customer


def _customer(db, name="KH A", active=True):
    customer = Customer(name=name, active=active)
    db.add(customer)
    db.flush()
    return customer


def _create(client, customer, **overrides):
    body = {"load_type": "FCL", "delivery_mode": "VIA_WAREHOUSE", "customer_id": customer.id, **overrides}
    return client.post("/api/shipments", json=body)


def test_create_fcl_minimal_defaults_staff_to_actor(client, db, login_as):
    user = login_as("DOCS")
    res = _create(client, _customer(db))
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["staff_id"] == user.id and data["status"] == "CREATED" and data["version"] == 1
    assert re.fullmatch(r"FF\d{7}", data["code"])


def test_create_writes_created_event_and_audit(client, db, login_as):
    login_as("DOCS")
    data = _create(client, _customer(db)).json()["data"]
    assert [(e["kind"], e["from_status"], e["to_status"]) for e in data["events"]] == [("TRANSITION", None, "CREATED")]
    audit = db.scalar(select(AuditLog).where(AuditLog.entity == "shipment", AuditLog.action == "CREATE"))
    assert audit is not None and audit.after["code"] == data["code"]


def test_create_lcl_container_to_door_422(client, db, login_as):
    login_as("DOCS")
    res = _create(client, _customer(db), load_type="LCL", delivery_mode="CONTAINER_TO_DOOR")
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_inactive_customer_400(client, db, login_as):
    login_as("DOCS")
    res = _create(client, _customer(db, active=False))
    assert res.status_code == 400 and res.json()["error"]["code"] == "INACTIVE_REFERENCE"


def test_create_driver_as_staff_400(client, db, login_as, make_user):
    login_as("DOCS")
    res = _create(client, _customer(db), staff_id=make_user("DRIVER").id)
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_STAFF"


def test_update_stale_version_409_version_conflict(client, db, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    first = client.patch(f"/api/shipments/{shipment.id}", json={"version": 1, "vessel": "EVER GIVEN"})
    assert first.status_code == 200 and first.json()["data"]["version"] == 2
    second = client.patch(f"/api/shipments/{shipment.id}", json={"version": 1, "vessel": "OTHER"})
    assert second.status_code == 409 and second.json()["error"]["code"] == "VERSION_CONFLICT"


def test_update_explicit_null_clears_value(client, login_as, make_shipment, db):
    login_as("DOCS")
    shipment = make_shipment(hbl_no="HBL1")
    res = client.patch(f"/api/shipments/{shipment.id}", json={"version": 1, "hbl_no": None, "mbl_no": "maeu9"})
    data = res.json()["data"]
    assert data["hbl_no"] is None and data["mbl_no"] == "MAEU9"


def test_update_cancelled_409_shipment_closed(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment(status="CANCELLED")
    res = client.patch(f"/api/shipments/{shipment.id}", json={"version": 1, "vessel": "X"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "SHIPMENT_CLOSED"


def test_update_rejects_etd_after_stored_eta(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    res = client.patch(f"/api/shipments/{shipment.id}", json={"version": 1, "etd": "2099-01-01"})
    assert res.status_code == 422


def test_detail_allowed_transitions_created(client, login_as, make_shipment):
    login_as("DOCS")
    data = client.get(f"/api/shipments/{make_shipment().id}").json()["data"]
    assert data["allowed_transitions"] == ["IN_TRANSIT"] and data["in_transit_missing"] == []


def test_detail_reports_missing_fields_for_in_transit(client, login_as, make_shipment):
    login_as("DOCS")
    data = client.get(f"/api/shipments/{make_shipment(eta=None, mbl_no=None).id}").json()["data"]
    assert data["in_transit_missing"] == ["bl_no", "eta"]


def test_accountant_create_403(client, db, login_as):
    login_as("ACCOUNTANT")
    assert _create(client, _customer(db)).status_code == 403


def test_detail_missing_404(client, login_as):
    login_as("DOCS")
    res = client.get("/api/shipments/999999")
    assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"


def test_customer_cannot_read_other_customers_shipment(client, login_as, make_shipment):
    login_as("CUSTOMER")
    assert client.get(f"/api/shipments/{make_shipment().id}").status_code == 403
