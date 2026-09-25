import pytest
from sqlalchemy import select

from app.audit.models import AuditLog


def test_docs_creates_port_with_aliases(client, login_as):
    login_as("DOCS")
    res = client.post("/api/catalog/ports", json={"code": "vnsgn", "name": "TP.HCM", "aliases": ["vncli", "Cat Lai"]})
    assert res.status_code == 201
    assert res.json()["data"]["code"] == "VNSGN"
    assert res.json()["data"]["aliases"] == ["CAT LAI", "VNCLI"]


def test_invalid_unlocode_rejected(client, login_as):
    login_as("DOCS")
    res = client.post("/api/catalog/ports", json={"code": "SGN", "name": "x"})
    assert res.status_code == 422


@pytest.mark.parametrize(("role", "kind", "status"), [
    ("DOCS", "customers", 201), ("DISPATCH", "customers", 403), ("ACCOUNTANT", "customers", 403),
    ("DISPATCH", "truckers", 201), ("DOCS", "truckers", 403), ("ADMIN", "truckers", 201),
])
def test_write_permissions_by_role(client, login_as, role, kind, status):
    login_as(role)
    payload = {"name": "X"}
    assert client.post(f"/api/catalog/{kind}", json=payload).status_code == status


def test_customer_role_cannot_read_catalog(client, login_as):
    login_as("CUSTOMER")
    assert client.get("/api/catalog/customers").status_code == 403


def test_search_and_deactivate(client, login_as):
    login_as("DOCS")
    cid = client.post("/api/catalog/customers", json={"name": "Công ty Minh Long"}).json()["data"]["id"]
    client.post("/api/catalog/customers", json={"name": "Công ty Hải Âu"})
    found = client.get("/api/catalog/customers", params={"q": "minh"}).json()["data"]
    assert [c["id"] for c in found] == [cid]
    assert client.patch(f"/api/catalog/customers/{cid}", json={"active": False}).json()["data"]["active"] is False
    assert all(c["id"] != cid for c in client.get("/api/catalog/customers?active=true").json()["data"])


def test_referenced_record_cannot_be_deleted(client, login_as):
    login_as("DISPATCH")
    tid = client.post("/api/catalog/truckers", json={"name": "Nhà xe A"}).json()["data"]["id"]
    client.post("/api/catalog/drivers", json={"trucker_id": tid, "full_name": "Tài xế B"})
    res = client.delete(f"/api/catalog/truckers/{tid}")
    assert res.status_code == 409 and res.json()["error"]["code"] == "IN_USE"


def test_audit_masks_pii(client, db, login_as):
    login_as("DOCS")
    client.post("/api/catalog/customers", json={"name": "KH", "phone": "0901234567", "email": "kh@abc.vn"})
    row = db.scalar(select(AuditLog).where(AuditLog.entity == "customers"))
    assert row.after["phone"] == "09******67"
    assert row.after["email"] == "k***@abc.vn"


def test_duplicate_plate_conflict(client, login_as):
    login_as("DISPATCH")
    tid = client.post("/api/catalog/truckers", json={"name": "A"}).json()["data"]["id"]
    assert client.post("/api/catalog/trucks", json={"trucker_id": tid, "plate_no": "51c-12345"}).status_code == 201
    res = client.post("/api/catalog/trucks", json={"trucker_id": tid, "plate_no": "51C-12345"})
    assert res.status_code == 409
