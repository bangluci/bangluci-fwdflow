import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def test_health_reports_db_ok(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"success": True, "data": {"status": "ok", "db": "ok"}, "error": None, "meta": None}


def test_unknown_route_uses_envelope(client):
    res = client.get("/api/khong-ton-tai")
    assert res.status_code == 404
    body = res.json()
    assert body["success"] is False and body["error"]["code"] == "NOT_FOUND"


def test_extensions_installed(db):
    names = set(db.execute(text("SELECT extname FROM pg_extension")).scalars())
    assert {"vector", "pg_trgm", "unaccent"} <= names


def test_audit_logs_are_append_only(db):
    db.execute(text("INSERT INTO audit_logs (action, entity) VALUES ('X', 'test')"))
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE audit_logs SET action = 'Y'"))
