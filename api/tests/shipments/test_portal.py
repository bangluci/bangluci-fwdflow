import hashlib
from datetime import UTC, datetime

import pytest

from app.catalog.models import Customer
from app.documents.storage import path_for
from app.shipments.models import ShipmentEvent

PORTAL = "/api/portal"


@pytest.fixture
def customer(login_as, db):
    user = login_as("CUSTOMER")
    return db.get(Customer, user.customer_id)


def _real_document(db, make_document, shipment, data=b"%PDF-1.4 demo", **fields):
    sha = hashlib.sha256(data).hexdigest()
    path_for(sha).parent.mkdir(parents=True, exist_ok=True)
    path_for(sha).write_bytes(data)
    document = make_document(shipment, **fields)
    document.file_sha256 = sha
    db.flush()
    return document


def test_portal_lists_only_own_shipments(client, customer, make_shipment):
    mine = make_shipment(customer=customer, status="IN_TRANSIT")
    make_shipment()
    data = client.get(f"{PORTAL}/shipments").json()["data"]
    assert [s["id"] for s in data] == [mine.id]
    assert set(data[0]) == {"id", "code", "load_type", "status", "hbl_no", "vessel", "voyage", "etd", "eta",
                            "total_packages", "pol", "pod"}
    assert data[0]["pol"] == "CNSHA" and data[0]["pod"] == "VNSGN"


def test_portal_other_customer_shipment_404(client, customer, make_shipment):
    res = client.get(f"{PORTAL}/shipments/{make_shipment().id}")
    assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"


def test_portal_hidden_document_404(client, db, customer, make_shipment, make_document):
    shipment = make_shipment(customer=customer)
    document = _real_document(db, make_document, shipment, doc_type="DO")
    assert document.visible_to_customer is False
    assert client.get(f"{PORTAL}/documents/{document.id}/file").status_code == 404
    assert client.get(f"{PORTAL}/shipments/{shipment.id}").json()["data"]["documents"] == []


def test_portal_superseded_document_404(client, db, customer, make_shipment, make_document):
    shipment = make_shipment(customer=customer)
    old = _real_document(db, make_document, shipment, b"%PDF-1.4 old")
    new = _real_document(db, make_document, shipment, b"%PDF-1.4 new")
    old.superseded_by_id = new.id
    db.flush()
    assert client.get(f"{PORTAL}/documents/{old.id}/file").status_code == 404
    docs = client.get(f"{PORTAL}/shipments/{shipment.id}").json()["data"]["documents"]
    assert [d["id"] for d in docs] == [new.id] and set(docs[0]) == {"id", "doc_type", "created_at"}


def test_portal_other_customers_document_404(client, db, customer, make_shipment, make_document):
    document = _real_document(db, make_document, make_shipment())
    assert client.get(f"{PORTAL}/documents/{document.id}/file").status_code == 404


def test_portal_download_is_attachment_with_db_content_type(client, db, customer, make_shipment, make_document):
    document = _real_document(db, make_document, make_shipment(customer=customer), b"%PDF-1.4 noi dung")
    res = client.get(f"{PORTAL}/documents/{document.id}/file")
    assert res.status_code == 200 and res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"].startswith("attachment") and ".pdf" in res.headers["content-disposition"]
    assert res.headers["x-content-type-options"] == "nosniff"
    assert hashlib.sha256(res.content).hexdigest() == document.file_sha256


def test_portal_timeline_only_status_and_time(client, db, customer, make_shipment):
    shipment = make_shipment(customer=customer, status="CLEARED")
    cleared = db.query(ShipmentEvent).filter_by(shipment_id=shipment.id, to_status="CLEARED").one()
    db.add(ShipmentEvent(shipment_id=shipment.id, kind="VOID", adjusts_event_id=cleared.id,
                         occurred_at=datetime.now(UTC), reason="nhập nhầm"))
    db.flush()
    timeline = client.get(f"{PORTAL}/shipments/{shipment.id}").json()["data"]["timeline"]
    assert all(set(item) == {"status", "occurred_at"} for item in timeline)
    assert [item["status"] for item in timeline] == ["CREATED", "IN_TRANSIT", "ARRIVED", "CUSTOMS_CLEARING"]


def test_portal_detail_has_no_internal_fields(client, customer, make_shipment, make_container):
    shipment = make_shipment(customer=customer, do_no="DO-123")
    make_container(shipment)
    data = client.get(f"{PORTAL}/shipments/{shipment.id}").json()["data"]
    assert not {"do_no", "do_valid_until", "version", "claims_fta", "staff_id", "staff_name"} & set(data)
    assert set(data["containers"][0]) == {"container_no", "container_type"}


def test_customer_forbidden_on_backoffice_api(client, db, customer, make_shipment, make_document):
    shipment = make_shipment(customer=customer)
    document = _real_document(db, make_document, shipment)
    assert client.get("/api/shipments").status_code == 403
    assert client.get(f"/api/documents/{document.id}/file").status_code == 403


@pytest.mark.parametrize("role", ["ADMIN", "DOCS", "DISPATCH", "ACCOUNTANT", "DRIVER"])
def test_portal_is_for_customers_only(client, login_as, role):
    login_as(role)
    res = client.get(f"{PORTAL}/shipments")
    assert res.status_code == 403 and res.json()["error"]["code"] == "FORBIDDEN"


def test_portal_requires_login(client):
    assert client.get(f"{PORTAL}/shipments").status_code == 401
