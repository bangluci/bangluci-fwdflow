from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import ratelimit
from app.lastmile import public_router
from app.lastmile.public_router import ip_limiter, mask_name, not_found_limiter
from app.main import app

DELIVERED = ("CREATED", "ASSIGNED", "PICKED_UP", "DELIVERED")
FROZEN_NOW = 1_700_000_000.0


@pytest.fixture(autouse=True)
def fresh_limiters(monkeypatch):
    # Đồng hồ limiter đứng yên: vòng lặp N request không thể vắt qua ranh giới cửa sổ cố định 60s.
    monkeypatch.setattr(ratelimit, "time", SimpleNamespace(time=lambda: FROZEN_NOW))
    ip_limiter.reset()
    not_found_limiter.reset()
    yield
    ip_limiter.reset()
    not_found_limiter.reset()


@pytest.fixture
def as_ip(client):
    """`as_ip("1.2.3.4")` → TestClient có địa chỉ nguồn riêng (dùng chung phiên DB của fixture `client`)."""
    opened = []

    def _make(ip: str) -> TestClient:
        c = TestClient(app, base_url="https://testserver", client=(ip, 50000))
        opened.append(c)
        return c

    yield _make
    for c in opened:
        c.close()


@pytest.fixture
def order(make_shipment, make_last_mile_order):
    return make_last_mile_order(make_shipment(status="DELIVERING", total_packages=10), 3, events=DELIVERED,
                                tracking_code="DEM00TRACK")


def test_track_returns_only_status_date_masked_name(client, order):
    res = client.get("/api/public/track/DEM00TRACK")
    data = res.json()["data"]
    assert res.status_code == 200
    assert set(data) == {"tracking_code", "status", "status_label", "updated_date", "recipient_masked"}
    assert data["tracking_code"] == "DEM00-TRACK" and data["status"] == "DELIVERED"
    assert data["status_label"] == "Đã giao" and data["recipient_masked"] == "N*** V*** A***"
    assert "0901234567" not in res.text and "Lê Lợi" not in res.text and "Nguyễn" not in res.text


@pytest.mark.parametrize("raw", ["dem00-track", "DEM0O-TRACK", " dem00 track "])
def test_track_normalizes_case_dash_and_ambiguous_chars(client, order, raw):
    assert client.get(f"/api/public/track/{raw}").status_code == 200


def test_unknown_and_malformed_code_same_not_found(client, order):
    bodies = {client.get(f"/api/public/track/{code}").text for code in ("ZZZZZZZZZZ", "%23%23%23", "UUUUU11111", "x")}
    assert len(bodies) == 1 and '"NOT_FOUND"' in bodies.pop()


@pytest.mark.parametrize(("days", "status"), [(30, 200), (31, 404)])
def test_tracking_expires_30_days_after_delivered(client, make_shipment, make_last_mile_order, days, status):
    delivered_at = datetime.now(UTC) - timedelta(days=days) - timedelta(hours=1)
    make_last_mile_order(make_shipment(status="DELIVERING", total_packages=1), 1, events=DELIVERED,
                         tracking_code="EXP00TRACK", started_at=delivered_at)
    assert client.get("/api/public/track/EXP00TRACK").status_code == status


def test_expired_response_identical_to_unknown(client, make_shipment, make_last_mile_order):
    make_last_mile_order(make_shipment(status="DELIVERING", total_packages=1), 1, events=DELIVERED,
                         tracking_code="EXP00TRACK", started_at=datetime.now(UTC) - timedelta(days=60))
    assert client.get("/api/public/track/EXP00TRACK").text == client.get("/api/public/track/ZZZZZZZZZZ").text


def test_public_headers_on_200_404_429(client, order):
    def check(res):
        assert res.headers["X-Robots-Tag"] == "noindex" and res.headers["Referrer-Policy"] == "no-referrer"
        assert res.headers["Cache-Control"] == "no-store"

    check(client.get("/api/public/track/DEM00TRACK"))
    check(client.get("/api/public/track/ZZZZZZZZZZ"))
    for _ in range(public_router.TRACK_LIMIT_PER_IP):
        client.get("/api/public/track/DEM00TRACK")
    limited = client.get("/api/public/track/DEM00TRACK")
    assert limited.status_code == 429 and limited.json()["error"]["code"] == "RATE_LIMITED"
    check(limited)
    assert "X-Robots-Tag" not in client.get("/api/health").headers


def test_one_ip_31_requests_blocked(as_ip, order):
    c = as_ip("203.0.113.5")
    codes = [c.get("/api/public/track/DEM00TRACK").status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


def test_two_ips_20_requests_each_not_blocked(as_ip, order):
    first, second = as_ip("203.0.113.5"), as_ip("203.0.113.6")
    for _ in range(20):
        assert first.get("/api/public/track/DEM00TRACK").status_code == 200
        assert second.get("/api/public/track/DEM00TRACK").status_code == 200


def test_ipv6_same_64_prefix_shares_limit(as_ip, order):
    a, b = as_ip("2001:db8:1:2::1"), as_ip("2001:db8:1:2:ffff::9")
    for _ in range(15):
        assert a.get("/api/public/track/DEM00TRACK").status_code == 200
        assert b.get("/api/public/track/DEM00TRACK").status_code == 200
    assert a.get("/api/public/track/DEM00TRACK").status_code == 429
    assert as_ip("2001:db8:1:3::1").get("/api/public/track/DEM00TRACK").status_code == 200


def test_global_not_found_cap_returns_429(as_ip, order, monkeypatch):
    monkeypatch.setattr(not_found_limiter, "limit", 5)
    codes = [as_ip(f"198.51.100.{i}").get("/api/public/track/ZZZZZZZZZZ").status_code for i in range(1, 7)]
    assert codes == [404] * 5 + [429]
    assert as_ip("198.51.100.99").get("/api/public/track/DEM00TRACK").status_code == 200


def test_mask_name_keeps_first_letter_per_word():
    assert mask_name("Nguyễn Văn An") == "N*** V*** A***"
    assert mask_name("  Trần   Bình ") == "T*** B***"
