"""Luồng hàng lẻ (LCL) qua kho từ CREATED tới COMPLETED, đi qua API như người dùng thật."""

from sqlalchemy import func, select

from app.shipments.models import Container
from tests.driver_factories import jpeg
from tests.flows.steps import refresh_status, walk_to_cleared


def test_lcl_created_to_completed(client, db, login_as, switch_to, send, make_driver, make_shipment, today,
                                  make_required_documents):
    login_as("DOCS")
    shipment = make_shipment(status="CREATED", load_type="LCL", delivery_mode="VIA_WAREHOUSE", total_packages=100)
    walk_to_cleared(client, shipment, make_required_documents)

    login_as("DISPATCH")
    received = client.post(f"/api/shipments/{shipment.id}/receive-at-warehouse", data={"note": "nhận đủ kiện"},
                           files={"photo": ("cfs.jpg", jpeg("gray"), "image/jpeg")})
    assert received.status_code == 200 and received.json()["data"]["status"] == "AT_WAREHOUSE"

    driver = make_driver()
    orders = [{"recipient_name": name, "recipient_phone": phone, "address": "12 Lê Lợi, Quận 1, TP.HCM",
               "packages": packages, "planned_date": today.isoformat(), "driver_id": driver.team.driver.id}
              for name, phone, packages in (("Nguyễn Văn An", "0901234567", 60), ("Trần Thị Bích", "0912345678", 40))]
    split = client.post(f"/api/shipments/{shipment.id}/last-mile-orders", json={"orders": orders})
    assert split.status_code == 201, split.text
    ids = [row["id"] for row in split.json()["data"]]

    switch_to(driver.user)
    assert send("LM_PICK_UP", ids[0]).status_code == 200
    assert refresh_status(db, shipment) == "DELIVERING"
    assert send("LM_DELIVER", ids[0], jpeg("red")).status_code == 200
    assert refresh_status(db, shipment) == "DELIVERING"  # còn 40 kiện chưa giao
    assert send("LM_PICK_UP", ids[1]).status_code == 200
    assert send("LM_DELIVER", ids[1], jpeg("blue")).status_code == 200

    assert refresh_status(db, shipment) == "COMPLETED"
    assert db.scalar(select(func.count()).select_from(Container).where(Container.shipment_id == shipment.id)) == 0


def test_lcl_rejects_container_to_door(client, db, login_as, make_shipment):
    login_as("DOCS")
    customer_id = make_shipment().customer_id
    response = client.post("/api/shipments", json={"load_type": "LCL", "delivery_mode": "CONTAINER_TO_DOOR",
                                                   "customer_id": customer_id})
    assert response.status_code == 422, response.text  # plan ghi 400; kiểm dữ liệu của repo trả 422
