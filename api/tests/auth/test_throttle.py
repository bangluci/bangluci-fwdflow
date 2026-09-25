from sqlalchemy import text

from tests.conftest import TEST_PASSWORD


def _login(client, identifier, password):
    return client.post("/api/auth/login", json={"identifier": identifier, "password": password})


def _set_ip(db, ip):
    # TestClient luôn có IP "testclient"; mô phỏng IP khác bằng cách sửa attempts đã ghi.
    db.execute(text("UPDATE login_attempts SET ip = :ip WHERE ip = 'testclient'"), {"ip": ip})


def test_pair_throttled_after_five_failures(client, make_user):
    make_user("DRIVER", email="tx@test.local")
    for _ in range(5):
        assert _login(client, "tx@test.local", "sai").status_code == 401
    res = _login(client, "tx@test.local", TEST_PASSWORD)
    assert res.status_code == 429 and res.json()["error"]["code"] == "RATE_LIMITED"


def test_attacker_ip_does_not_lock_owner_on_other_ip(client, db, make_user):
    make_user("DRIVER", email="owner@test.local")
    for _ in range(8):
        _login(client, "owner@test.local", "sai")
    _set_ip(db, "203.0.113.9")  # các lần sai thuộc về IP kẻ tấn công
    assert _login(client, "owner@test.local", TEST_PASSWORD).status_code == 200


def test_ip_cap_blocks_password_spraying(client, db, make_user):
    for i in range(20):
        _login(client, f"spray{i}@test.local", "Password1")
    res = _login(client, "spray99@test.local", "Password1")
    assert res.status_code == 429


def test_admin_unlock_clears_failures(client, login_as, make_user):
    target = make_user("DISPATCH", email="locked@test.local")
    for _ in range(6):
        _login(client, "locked@test.local", "sai")
    login_as("ADMIN")
    assert client.post(f"/api/users/{target.id}/unlock").status_code == 200
    client.cookies.clear()
    assert _login(client, "locked@test.local", TEST_PASSWORD).status_code == 200
