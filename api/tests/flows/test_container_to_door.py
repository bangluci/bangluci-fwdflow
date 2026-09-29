"""Luồng giao container tới cửa (FCL, CONTAINER_TO_DOOR) từ CREATED tới COMPLETED, đi qua API như người dùng thật."""

from sqlalchemy import func, select

from app.lastmile.models import LastMileOrder
from tests.driver_factories import discharged_at, jpeg
from tests.flows.steps import create_truck_order, refresh_status, walk_to_cleared


def _cleared_lot(client, login_as, make_shipment, make_container, make_required_documents):
    login_as("DOCS")
    shipment = make_shipment(status="CREATED", delivery_mode="CONTAINER_TO_DOOR")
    walk_to_cleared(client, shipment, make_required_documents)
    return shipment, make_container(shipment, milestones={"DISCHARGED": discharged_at()})


def test_container_to_door_created_to_completed(client, db, login_as, switch_to, send, make_driver, make_shipment,
                                                make_container, make_required_documents):
    shipment, container = _cleared_lot(client, login_as, make_shipment, make_container, make_required_documents)
    team = make_driver()

    login_as("DISPATCH")
    pickup = create_truck_order(client, container, team.team, "PICKUP_FULL")
    switch_to(team.user)
    assert send("TRUCK_START", pickup, jpeg()).status_code == 200
    assert send("TRUCK_COMPLETE", pickup, jpeg(), signer_name="Nguyễn Văn An").status_code == 200
    assert refresh_status(db, shipment) == "AT_WAREHOUSE"  # container đã tới cửa khách: hệ thống tự chuyển

    login_as("DISPATCH")
    empty = create_truck_order(client, container, team.team, "RETURN_EMPTY")
    switch_to(team.user)
    assert send("RETURN_START", empty).status_code == 200
    assert refresh_status(db, shipment) == "AT_WAREHOUSE"
    assert send("RETURN_COMPLETE", empty, jpeg()).status_code == 200

    assert refresh_status(db, shipment) == "COMPLETED"
    assert db.scalar(select(func.count()).select_from(LastMileOrder).where(LastMileOrder.shipment_id == shipment.id)) == 0


def test_container_to_door_completed_without_signer_rejected(client, db, login_as, switch_to, send, make_driver,
                                                             make_shipment, make_container, make_required_documents):
    shipment, container = _cleared_lot(client, login_as, make_shipment, make_container, make_required_documents)
    team = make_driver()
    login_as("DISPATCH")
    pickup = create_truck_order(client, container, team.team, "PICKUP_FULL")
    switch_to(team.user)
    assert send("TRUCK_START", pickup, jpeg()).status_code == 200
    response = send("TRUCK_COMPLETE", pickup, jpeg())  # có ảnh nhưng thiếu người ký nhận
    assert response.status_code == 400 and response.json()["error"]["code"] == "EVIDENCE_REQUIRED"
    assert response.json()["error"]["details"]["missing"] == ["signer_name"]
    assert refresh_status(db, shipment) == "CLEARED"
