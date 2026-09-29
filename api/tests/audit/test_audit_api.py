from datetime import datetime

from app.audit.models import AuditLog

VN_TZ = "+07:00"


def _row(db, actor, entity, at=None, action="UPDATE"):
    row = AuditLog(actor_id=actor.id, action=action, entity=entity, entity_id="1",
                   **({"created_at": datetime.fromisoformat(at)} if at else {}))
    db.add(row)
    db.flush()
    return row


def test_admin_filters_by_entity(client, db, login_as):
    admin = login_as("ADMIN")
    _row(db, admin, "shipment")
    _row(db, admin, "user")
    res = client.get("/api/audit", params={"entity": "shipment"}).json()
    assert [r["entity"] for r in res["data"]] == ["shipment"]
    assert res["meta"] == {"total": 1, "page": 1, "limit": 50}
    assert "shipment" in client.get("/api/audit/entities").json()["data"]


def test_admin_filters_by_actor(client, db, login_as, make_user):
    admin = login_as("ADMIN")
    other = make_user("DOCS", full_name="Nguyễn Văn Docs")
    _row(db, admin, "shipment")
    _row(db, other, "shipment")
    res = client.get("/api/audit", params={"actor_id": other.id}).json()["data"]
    assert [(r["actor_id"], r["actor_name"]) for r in res] == [(other.id, "Nguyễn Văn Docs")]


def test_admin_filters_by_date_range_vn(client, db, login_as):
    admin = login_as("ADMIN")
    edges = {label: _row(db, admin, "shipment", at).id for label, at in (
        ("before", f"2026-11-24T23:59:59{VN_TZ}"), ("start", f"2026-11-25T00:00:00{VN_TZ}"),
        ("end", f"2026-11-26T23:59:59{VN_TZ}"), ("after", f"2026-11-27T00:00:00{VN_TZ}"))}
    res = client.get("/api/audit", params={"date_from": "2026-11-25", "date_to": "2026-11-26", "entity": "shipment"})
    assert [r["id"] for r in res.json()["data"]] == [edges["end"], edges["start"]]


def test_non_admin_forbidden(client, login_as):
    login_as("DOCS")
    assert client.get("/api/audit").status_code == 403
    assert client.get("/api/audit/entities").status_code == 403


def test_audit_payload_has_no_password_hash_or_token(client, db, login_as, make_user):
    login_as("ADMIN")
    target = make_user("DOCS")
    reset = client.post(f"/api/users/{target.id}/reset-password", json={"password": "Mat-khau-moi-456"})
    assert reset.status_code == 200
    res = client.get("/api/audit", params={"entity": "user", "entity_id": str(target.id)})
    assert "$argon2id$" not in res.text and "token_hash" not in res.text
    assert any((r["after"] or {}).get("password_hash") == "<changed>" for r in res.json()["data"])
