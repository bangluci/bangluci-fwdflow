from sqlalchemy import select

from app.audit.models import AuditLog
from app.auth.models import Session


def test_cross_site_post_rejected(client, login_as):
    login_as("ADMIN")
    res = client.post("/api/catalog/carriers", json={"code": "RCL", "name": "RCL"},
                      headers={"Sec-Fetch-Site": "cross-site"})
    assert res.status_code == 403 and res.json()["error"]["code"] == "CSRF_REJECTED"


def test_foreign_origin_rejected(client, login_as):
    login_as("ADMIN")
    res = client.post("/api/catalog/carriers", json={"code": "RCL", "name": "RCL"},
                      headers={"Origin": "https://evil.example"})
    assert res.status_code == 403


def test_same_origin_post_allowed(client, login_as):
    login_as("ADMIN")
    res = client.post("/api/catalog/carriers", json={"code": "RCL", "name": "RCL"},
                      headers={"Origin": "http://localhost:8088", "Sec-Fetch-Site": "same-origin"})
    assert res.status_code == 201


def test_non_admin_cannot_manage_users(client, login_as):
    login_as("DOCS")
    assert client.get("/api/users").status_code == 403


def test_role_change_revokes_sessions(client, db, login_as, make_user):
    target = make_user("DOCS")
    from app.auth.service import create_session

    create_session(db, target, "1.1.1.1", "x")
    db.flush()
    login_as("ADMIN")
    assert client.patch(f"/api/users/{target.id}", json={"role": "DISPATCH"}).status_code == 200
    assert db.scalar(select(Session).where(Session.user_id == target.id)) is None


def test_reset_password_audit_hides_hash(client, db, login_as, make_user):
    target = make_user("DOCS")
    login_as("ADMIN")
    client.post(f"/api/users/{target.id}/reset-password", json={"password": "Mat-khau-moi-123"})
    row = db.scalar(select(AuditLog).where(AuditLog.action == "RESET_PASSWORD"))
    assert row.after == {"password_hash": "<changed>"}


def test_create_customer_user_requires_customer(client, login_as):
    login_as("ADMIN")
    res = client.post("/api/users", json={"email": "c@x.vn", "full_name": "C", "role": "CUSTOMER",
                                          "password": "12345678"})
    assert res.status_code == 422
