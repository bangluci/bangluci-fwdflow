from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.documents.storage import path_for
from app.driver.actions import HANDLERS
from app.trucking.models import TruckingOrderEvent
from tests.driver.conftest import jpeg


def _events(db, order):
    return db.scalars(select(TruckingOrderEvent).where(TruckingOrderEvent.order_id == order.id)
                      .order_by(TruckingOrderEvent.id)).all()


def test_replay_returns_first_result_without_second_event(client, db, driver, ready_order, send):
    made, request_id = ready_order(), str(uuid4())
    first = send("TRUCK_START", made.order.id, jpeg(), request_id)
    second = send("TRUCK_START", made.order.id, jpeg(), request_id)
    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json()["meta"]["replayed"] is False and second.json()["meta"]["replayed"] is True
    assert second.json()["data"] == first.json()["data"]
    assert len([e for e in _events(db, made.order) if e.kind == "STARTED"]) == 1


def test_replay_still_works_after_order_is_reassigned(client, db, driver, make_driver, ready_order, send):
    made, request_id = ready_order(), str(uuid4())
    first = send("TRUCK_START", made.order.id, jpeg(), request_id)
    other = make_driver()
    made.order.driver_id, made.order.truck_id = other.team.driver.id, other.team.truck.id
    db.flush()
    again = send("TRUCK_START", made.order.id, jpeg(), request_id)
    assert again.status_code == 200 and again.json()["data"]["event_id"] == first.json()["data"]["event_id"]


def test_request_id_reused_by_other_driver_or_other_order_409(client, db, driver, make_driver, switch_to,
                                                              ready_order, send):
    made, request_id = ready_order(), str(uuid4())
    other_order = ready_order()
    assert send("TRUCK_START", made.order.id, jpeg(), request_id).status_code == 200
    assert send("TRUCK_START", other_order.order.id, jpeg(), request_id).json()["error"]["code"] == (
        "DUPLICATE_REQUEST_ID")
    switch_to(make_driver().user)
    res = send("TRUCK_START", made.order.id, jpeg(), request_id)
    assert res.status_code == 409 and res.json()["error"]["code"] == "DUPLICATE_REQUEST_ID"


def test_missing_required_evidence_400_lists_missing(client, db, driver, ready_order, send):
    made = ready_order()
    res = send("TRUCK_START", made.order.id)
    error = res.json()["error"]
    assert res.status_code == 400 and error["code"] == "EVIDENCE_REQUIRED" and error["details"]["missing"] == ["photo"]
    assert [e.kind for e in _events(db, made.order)] == ["ASSIGNED"] and made.order.status == "ASSIGNED"


def test_photo_is_saved_and_hash_stored_on_event(client, db, driver, ready_order, send):
    made = ready_order()
    assert send("TRUCK_START", made.order.id, jpeg()).status_code == 200
    started = next(e for e in _events(db, made.order) if e.kind == "STARTED")
    assert len(started.photo_sha256) == 64 and path_for(started.photo_sha256).is_file()


def test_coordinates_null_when_gps_off_and_stored_when_sent(client, db, driver, ready_order, send):
    first, second = ready_order(), ready_order()
    assert send("TRUCK_START", first.order.id, jpeg()).status_code == 200
    started = next(e for e in _events(db, first.order) if e.kind == "STARTED")
    assert (started.lat, started.lng) == (None, None)
    assert send("TRUCK_START", second.order.id, jpeg(), lat="10.7769", lng="106.7009").status_code == 200
    started = next(e for e in _events(db, second.order) if e.kind == "STARTED")
    assert (float(started.lat), float(started.lng)) == (10.7769, 106.7009)
    third = ready_order()
    for fields in ({"lat": "10.5"}, {"lat": "91", "lng": "100"}, {"lat": "10", "lng": "181"}):
        res = send("TRUCK_START", third.order.id, jpeg(), **fields)
        assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_device_time_is_stored_but_occurred_at_is_server_time(client, db, driver, ready_order, send):
    made = ready_order()
    device = datetime.now(UTC) + timedelta(hours=2)
    assert send("TRUCK_START", made.order.id, jpeg(), device_time=device.isoformat()).status_code == 200
    started = next(e for e in _events(db, made.order) if e.kind == "STARTED")
    assert abs((started.device_time - device).total_seconds()) < 1
    assert abs((datetime.now(UTC) - started.occurred_at).total_seconds()) < 5


def test_device_time_without_timezone_400(client, driver, ready_order, send):
    made = ready_order()
    res = send("TRUCK_START", made.order.id, jpeg(), device_time="2026-11-25T08:00:00")
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_other_drivers_order_404(client, driver, make_driver, ready_order, send):
    made = ready_order(team=make_driver().team)
    res = send("TRUCK_START", made.order.id, jpeg())
    assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"


def test_unknown_action_and_wrong_order_kind_400(client, driver, ready_order, send):
    made = ready_order()
    assert send("XYZ", made.order.id).json()["error"]["code"] == "UNKNOWN_ACTION"
    res = send("RETURN_START", made.order.id)
    assert res.status_code == 400 and res.json()["error"]["code"] == "WRONG_ORDER_KIND"


def test_wrong_state_409_invalid_transition(client, driver, ready_order, send):
    made = ready_order(events=("ASSIGNED", "STARTED"))
    res = send("TRUCK_START", made.order.id, jpeg())
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_TRANSITION"


def test_bad_request_id_and_unavailable_action(client, driver, ready_order, send, monkeypatch):
    made = ready_order()
    assert send("TRUCK_START", made.order.id, jpeg(), request_id="not-a-uuid").status_code == 422
    monkeypatch.delitem(HANDLERS, "TRUCK_START")
    res = send("TRUCK_START", made.order.id, jpeg())
    assert res.status_code == 501 and res.json()["error"]["code"] == "ACTION_NOT_AVAILABLE"


def test_signer_and_reason_length_limits(client, driver, ready_order, send):
    made = ready_order()
    assert send("TRUCK_START", made.order.id, jpeg(), signer_name="x" * 101).status_code == 422
    assert send("TRUCK_START", made.order.id, jpeg(), reason="y" * 501).status_code == 422


@pytest.mark.parametrize("role", ["ADMIN", "DOCS", "DISPATCH", "ACCOUNTANT", "CUSTOMER"])
def test_non_driver_403_and_anonymous_401(client, login_as, send, role):
    assert send("TRUCK_START", 1).status_code == 401
    login_as(role)
    assert send("TRUCK_START", 1).status_code == 403


def test_empty_photo_part_counts_as_missing(client, driver, ready_order, send):
    made = ready_order()
    res = send("TRUCK_START", made.order.id, photo=b"")
    assert res.status_code == 400 and res.json()["error"]["details"]["missing"] == ["photo"]
