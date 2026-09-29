"""Các bước dùng chung của test luồng đầy đủ: mỗi hàm gọi API như người dùng thật, không sửa DB tay."""

from datetime import UTC, datetime, timedelta

DECLARATION = {"declaration_no": "301234567890", "type_code": "A11", "registered_at": "2026-10-01T02:00:00Z",
               "cleared_at": "2026-10-02T02:00:00Z"}


def transition(client, shipment, to_status: str):
    response = client.post(f"/api/shipments/{shipment.id}/transition", json={"to_status": to_status})
    assert response.status_code == 200, f"{to_status}: {response.status_code} {response.text[:200]}"
    return response.json()["data"]


def walk_to_cleared(client, shipment, make_required_documents) -> None:
    """DOCS chuyển tay CREATED → IN_TRANSIT → ARRIVED → CUSTOMS_CLEARING → CLEARED (có tờ khai đã thông quan, đủ chứng từ)."""
    for status in ("IN_TRANSIT", "ARRIVED", "CUSTOMS_CLEARING"):
        transition(client, shipment, status)
    declaration = client.post(f"/api/shipments/{shipment.id}/customs-declarations", json=DECLARATION)
    assert declaration.status_code == 201, declaration.text
    make_required_documents(shipment)
    assert transition(client, shipment, "CLEARED")["status"] == "CLEARED"


def create_truck_order(client, container, team, kind: str) -> int:
    """DISPATCH tạo lệnh xe cho tài xế của `team` rồi phân công; trả id lệnh."""
    created = client.post("/api/trucking-orders", json={
        "container_id": container.id, "kind": kind, "trucker_id": team.trucker.id, "pickup_location": "Cảng Cát Lái",
        "drop_location": "Kho khách hàng", "planned_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()})
    assert created.status_code == 201, created.text
    order_id = created.json()["data"]["id"]
    assigned = client.post(f"/api/trucking-orders/{order_id}/assign", json={"truck_id": team.truck.id,
                                                                            "driver_id": team.driver.id})
    assert assigned.status_code == 200, assigned.text
    return order_id


def refresh_status(db, shipment) -> str:
    db.refresh(shipment)
    return shipment.status
