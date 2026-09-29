from datetime import UTC, datetime, timedelta

import pytest

from app.envelope import AppError
from app.shipments.containers import add_container_event

NOW = datetime.now(UTC)
VALID_NO = "CSQU3054383"


def _containers(shipment):
    return f"/api/shipments/{shipment.id}/containers"


def _add(client, shipment, **overrides):
    return client.post(_containers(shipment), json={"container_no": VALID_NO, "container_type": "40HC", **overrides})


def _event(client, container_id, **body):
    return client.post(f"/api/containers/{container_id}/events", json=body)


def _detail(client, shipment):
    return client.get(f"/api/shipments/{shipment.id}").json()["data"]["containers"][0]


def _iso(delta_days):
    return (NOW - timedelta(days=delta_days)).isoformat()


def test_add_container_to_lcl_409(client, login_as, make_shipment):
    login_as("DOCS")
    res = _add(client, make_shipment(load_type="LCL"))
    assert res.status_code == 409 and res.json()["error"]["code"] == "CONTAINERS_FCL_ONLY"


def test_add_container_bad_check_digit_400(client, login_as, make_shipment):
    login_as("DOCS")
    res = _add(client, make_shipment(), container_no="CSQU3054384")
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_CONTAINER_NO"


def test_add_container_normalizes_number(client, login_as, make_shipment):
    login_as("DOCS")
    res = _add(client, make_shipment(), container_no="csqu 305438-3", seal_no=" ab12 ")
    assert res.status_code == 201 and res.json()["data"]["container_no"] == VALID_NO
    assert res.json()["data"]["seal_no"] == "AB12"


def test_add_container_duplicate_409(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    assert _add(client, shipment).status_code == 201
    res = _add(client, shipment)
    assert res.status_code == 409 and res.json()["error"]["code"] == "DUPLICATE_CONTAINER"


def test_update_container_seal_and_type(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    cid = _add(client, shipment).json()["data"]["id"]
    res = client.patch(f"{_containers(shipment)}/{cid}", json={"seal_no": "sl99", "container_type": "20GP"})
    assert (res.json()["data"]["seal_no"], res.json()["data"]["container_type"]) == ("SL99", "20GP")


def test_update_container_number_with_events_409(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    shipment = make_shipment(status="ARRIVED")
    container = make_container(shipment, milestones={"DISCHARGED": NOW - timedelta(hours=1)})
    res = client.patch(f"{_containers(shipment)}/{container.id}", json={"container_no": "TGHU1234567"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "CONTAINER_HAS_EVENTS"


def test_delete_container_with_events_409(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    shipment = make_shipment(status="ARRIVED")
    container = make_container(shipment, milestones={"DISCHARGED": NOW - timedelta(hours=1)})
    assert client.delete(f"{_containers(shipment)}/{container.id}").status_code == 409


def test_delete_container_without_events(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    cid = _add(client, shipment).json()["data"]["id"]
    assert client.delete(f"{_containers(shipment)}/{cid}").status_code == 200
    assert client.get(f"/api/shipments/{shipment.id}").json()["data"]["containers"] == []


def test_discharged_when_in_transit_409(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    container = make_container(make_shipment(status="IN_TRANSIT"))
    res = _event(client, container.id, kind="DISCHARGED")
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_SHIPMENT_STATUS"


def test_discharged_when_arrived_updates_status_cache(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    container = make_container(make_shipment(status="ARRIVED"))
    res = _event(client, container.id, kind="DISCHARGED", occurred_at=_iso(1))
    data = res.json()["data"]
    assert res.status_code == 201 and data["status"] == "DISCHARGED" and "DISCHARGED" in data["milestones"]


def test_discharged_twice_409(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    container = make_container(make_shipment(status="ARRIVED"))
    assert _event(client, container.id, kind="DISCHARGED").status_code == 201
    res = _event(client, container.id, kind="DISCHARGED")
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_MILESTONE_ORDER"


def test_api_rejects_gate_out_kind_422(client, login_as, make_shipment, make_container):
    login_as("ADMIN")
    container = make_container(make_shipment(status="CLEARED"), milestones={"DISCHARGED": NOW - timedelta(days=1)})
    assert _event(client, container.id, kind="GATE_OUT_FULL").status_code == 422


def test_gate_out_before_discharged_409(db, make_shipment, make_container):
    container = make_container(make_shipment(status="CLEARED"))
    with pytest.raises(AppError) as err:
        add_container_event(db, container.id, "GATE_OUT_FULL", NOW - timedelta(hours=1), None)
    assert err.value.code == "INVALID_MILESTONE_ORDER"


def test_gate_out_earlier_than_discharged_409(db, make_shipment, make_container):
    container = make_container(make_shipment(status="CLEARED"), milestones={"DISCHARGED": NOW - timedelta(hours=2)})
    with pytest.raises(AppError) as err:
        add_container_event(db, container.id, "GATE_OUT_FULL", NOW - timedelta(hours=3), None)
    assert err.value.code == "INVALID_MILESTONE_ORDER"


def test_gate_out_after_discharged_updates_cache(db, make_shipment, make_container):
    container = make_container(make_shipment(status="CLEARED"), milestones={"DISCHARGED": NOW - timedelta(hours=2)})
    event = add_container_event(db, container.id, "GATE_OUT_FULL", NOW - timedelta(hours=1), None)
    assert event.actor_id is None and container.status == "GATE_OUT_FULL"


def test_future_occurred_at_400(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    container = make_container(make_shipment(status="ARRIVED"))
    res = _event(client, container.id, kind="DISCHARGED", occurred_at=(NOW + timedelta(days=1)).isoformat())
    assert res.status_code == 400 and res.json()["error"]["code"] == "FUTURE_OCCURRED_AT"


def _discharged_and_gate_out(make_shipment, make_container, status="CLEARED"):
    shipment = make_shipment(status=status)
    container = make_container(shipment, milestones={"DISCHARGED": NOW - timedelta(days=3),
                                                     "GATE_OUT_FULL": NOW - timedelta(days=1)})
    return shipment, container


def test_retime_updates_effective_time_in_detail(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    shipment, container = _discharged_and_gate_out(make_shipment, make_container)
    target = _detail(client, shipment)["milestones"]["DISCHARGED"]["event_id"]
    new_time = _iso(2)
    res = _event(client, container.id, kind="RETIME", adjusts_event_id=target, occurred_at=new_time, reason="Sửa giờ dỡ")
    assert res.status_code == 201
    milestone = res.json()["data"]["milestones"]["DISCHARGED"]
    assert datetime.fromisoformat(milestone["occurred_at"]) == datetime.fromisoformat(new_time)


def test_retime_breaking_order_409(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    shipment, container = _discharged_and_gate_out(make_shipment, make_container)
    target = _detail(client, shipment)["milestones"]["DISCHARGED"]["event_id"]
    res = _event(client, container.id, kind="RETIME", adjusts_event_id=target, occurred_at=_iso(0.5),
                 reason="Sai thứ tự")
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_MILESTONE_ORDER"


def test_retime_without_reason_422(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    shipment, container = _discharged_and_gate_out(make_shipment, make_container)
    target = _detail(client, shipment)["milestones"]["DISCHARGED"]["event_id"]
    assert _event(client, container.id, kind="RETIME", adjusts_event_id=target, occurred_at=_iso(2),
                  reason=" ").status_code == 422


def test_retime_targeting_retime_400(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    shipment, container = _discharged_and_gate_out(make_shipment, make_container)
    target = _detail(client, shipment)["milestones"]["DISCHARGED"]["event_id"]
    _event(client, container.id, kind="RETIME", adjusts_event_id=target, occurred_at=_iso(2), reason="Lần 1")
    retime_id = max(e["id"] for e in _detail(client, shipment)["events"])
    res = _event(client, container.id, kind="RETIME", adjusts_event_id=retime_id, occurred_at=_iso(2), reason="Lần 2")
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_ADJUSTMENT"


def test_retime_event_of_other_container_400(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    shipment, _ = _discharged_and_gate_out(make_shipment, make_container)
    other_shipment, other = _discharged_and_gate_out(make_shipment, make_container)
    foreign = _detail(client, other_shipment)["milestones"]["DISCHARGED"]["event_id"]
    container_id = _detail(client, shipment)["id"]
    res = _event(client, container_id, kind="RETIME", adjusts_event_id=foreign, occurred_at=_iso(2), reason="Nhầm")
    assert res.status_code == 400 and other.id != container_id


def test_retime_allowed_on_completed_shipment(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    shipment, container = _discharged_and_gate_out(make_shipment, make_container, status="COMPLETED")
    target = _detail(client, shipment)["milestones"]["DISCHARGED"]["event_id"]
    assert _event(client, container.id, kind="RETIME", adjusts_event_id=target, occurred_at=_iso(2),
                  reason="Sửa sau khi hoàn tất").status_code == 201


def test_dispatch_add_discharged_403(client, login_as, make_shipment, make_container):
    login_as("DISPATCH")
    container = make_container(make_shipment(status="ARRIVED"))
    assert _event(client, container.id, kind="DISCHARGED").status_code == 403
