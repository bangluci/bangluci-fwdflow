from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from app.audit.models import AuditLog
from app.auth.models import Session
from app.config import get_settings
from tests.conftest import TEST_PASSWORD

COOKIE = get_settings().session_cookie_name


def _login(client, identifier, password=TEST_PASSWORD, ip_headers=None):
    return client.post("/api/auth/login", json={"identifier": identifier, "password": password},
                       headers=ip_headers or {})


def test_login_sets_host_cookie_and_me_works(client, make_user):
    user = make_user("DOCS", email="docs@test.local")
    res = _login(client, "DOCS@test.local ")
    assert res.status_code == 200
    set_cookie = res.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE}=")
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert flag.lower() in set_cookie.lower()
    assert "domain=" not in set_cookie.lower()
    me = client.get("/api/auth/me").json()
    assert me["data"]["id"] == user.id and me["data"]["role"] == "DOCS"


def test_me_lists_role_permissions(client, login_as):
    login_as("DOCS")
    permissions = client.get("/api/auth/me").json()["data"]["permissions"]
    assert "shipment.write" in permissions and "users.manage" not in permissions
    assert permissions == sorted(permissions)


def test_login_by_phone(client, make_user):
    make_user("DRIVER", email=None, phone="0901234567")
    assert _login(client, "0901 234 567").status_code == 200


def test_wrong_password_and_unknown_user_same_message(client, make_user):
    make_user("ADMIN", email="a@test.local")
    wrong = _login(client, "a@test.local", "sai-mat-khau").json()
    unknown = _login(client, "khong-co@test.local", "sai-mat-khau").json()
    assert wrong["error"] == unknown["error"]
    assert wrong["error"]["code"] == "BAD_CREDENTIALS"


def test_inactive_user_cannot_login(client, make_user):
    make_user("ADMIN", email="off@test.local", is_active=False)
    assert _login(client, "off@test.local").status_code == 401


def test_me_requires_session(client):
    assert client.get("/api/auth/me").json()["error"]["code"] == "UNAUTHENTICATED"


def test_logout_deletes_session(client, db, make_user):
    make_user("ADMIN", email="out@test.local")
    _login(client, "out@test.local")
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.clear()
    assert db.scalar(select(Session).limit(1)) is None


def test_idle_session_expires_for_internal_user(client, db, login_as):
    login_as("ACCOUNTANT")
    db.execute(text("UPDATE sessions SET last_seen_at = now() - interval '9 hours'"))
    assert client.get("/api/auth/me").status_code == 401


def test_driver_session_survives_one_day_idle(client, db, login_as):
    login_as("DRIVER")
    db.execute(text("UPDATE sessions SET last_seen_at = now() - interval '1 day'"))
    assert client.get("/api/auth/me").status_code == 200


def test_absolute_expiry(client, db, login_as):
    login_as("DRIVER")
    db.query(Session).update({Session.absolute_expires_at: datetime.now(UTC) - timedelta(seconds=1)})
    assert client.get("/api/auth/me").status_code == 401


def test_login_is_audited_without_secrets(client, db, make_user):
    make_user("ADMIN", email="audit@test.local")
    _login(client, "audit@test.local")
    row = db.scalar(select(AuditLog).where(AuditLog.action == "LOGIN"))
    assert row is not None and "password" not in str(row.after)
