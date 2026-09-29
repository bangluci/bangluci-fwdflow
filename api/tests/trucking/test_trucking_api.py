import pytest

URL = "/api/trucking-orders"


@pytest.fixture
def world(make_shipment, make_container, make_trucker):
    shipment = make_shipment(status="CLEARED")
    return type("World", (), {"shipment": shipment, "container": make_container(shipment), "team": make_trucker()})


def _create(client, world, planned_at="2026-11-26T08:00:00+07:00", **extra):
    return client.post(URL, json={"container_id": world.container.id, "kind": "PICKUP_FULL",
                                  "trucker_id": world.team.trucker.id, "pickup_location": "Cảng Cát Lái",
                                  "drop_location": "Kho Bình Dương", "planned_at": planned_at, **extra})


def test_dispatch_creates_and_assigns_order(client, login_as, world):
    login_as("DISPATCH")
    created = _create(client, world)
    assert created.status_code == 201
    order = created.json()["data"]
    assert (order["status"], order["truck_id"], order["container_no"]) == (
        "PLANNED", None, world.container.container_no)
    res = client.post(f"{URL}/{order['id']}/assign",
                      json={"truck_id": world.team.truck.id, "driver_id": world.team.driver.id})
    data = res.json()["data"]
    assert res.status_code == 200 and data["status"] == "ASSIGNED" and data["plate_no"] == world.team.truck.plate_no
    assert [e["kind"] for e in client.get(f"{URL}/{order['id']}").json()["data"]["events"]] == ["ASSIGNED"]
    cancelled = client.post(f"{URL}/{order['id']}/cancel", json={"reason": "Khách hoãn"})
    assert cancelled.json()["data"]["status"] == "CANCELLED"


def test_docs_cannot_create_order(client, login_as, world):
    login_as("DOCS")
    assert _create(client, world).status_code == 403
    assert client.get(URL).status_code == 200  # nhân viên nội bộ đọc được


def test_driver_cannot_list_orders(client, login_as, world):
    login_as("DRIVER")
    assert client.get(URL).status_code == 403
    login_as("CUSTOMER")
    assert client.get(URL).status_code == 403


def test_list_filters_by_planned_date_range(client, login_as, world, make_shipment, make_container):
    login_as("DISPATCH")
    ids = {}
    for label, planned in (("edge_start", "2026-11-25T00:30:00+07:00"), ("edge_end", "2026-11-27T23:30:00+07:00"),
                           ("before", "2026-11-24T23:59:00+07:00"), ("after", "2026-11-28T00:00:00+07:00")):
        other = type("W", (), {"container": make_container(make_shipment(status="CLEARED")), "team": world.team})
        ids[label] = _create(client, other, planned_at=planned).json()["data"]["id"]
    res = client.get(URL, params={"date_from": "2026-11-25", "date_to": "2026-11-27"}).json()["data"]
    assert [row["id"] for row in res] == [ids["edge_start"], ids["edge_end"]]
    assert [r["id"] for r in client.get(URL, params={"status": "CANCELLED"}).json()["data"]] == []
    assert len(client.get(URL, params={"kind": "PICKUP_FULL"}).json()["data"]) == 4


@pytest.mark.parametrize("field", ["drop_location", "pickup_location"])
def test_blank_drop_location_rejected(client, login_as, world, field):
    login_as("DISPATCH")
    res = _create(client, world, **{field: "   "})
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"
