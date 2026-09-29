"""Hai giao dịch thật (commit thật, hai kết nối) giao hai đơn cuối cùng lúc: lô phải COMPLETED đúng một lần."""

import io
import threading
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.auth.models import User
from app.catalog.models import Carrier, Customer, Driver, Port, Trucker
from app.driver.process import ActionForm, process_driver_action
from app.lastmile.models import LastMileOrder
from app.shipments.models import Shipment, ShipmentEvent
from tests.driver_factories import jpeg

KEEP = ("alembic_version", "required_doc_rules")


@pytest.fixture
def committed_world(engine):
    """Dữ liệu commit thật (không rollback), dọn sạch bằng TRUNCATE khi xong."""
    with Session(engine) as s:
        customer, trucker = Customer(name="KH song song"), Trucker(name="Nha xe song song")
        carrier, pol, pod = (Carrier(code="PARA", name="Para"), Port(code="CNPAR", name="P1"),
                             Port(code="VNPAR", name="P2"))
        s.add_all([customer, trucker, carrier, pol, pod])
        s.flush()
        driver = Driver(trucker_id=trucker.id, full_name="Tai xe song song")
        s.add(driver)
        s.flush()
        staff = User(email="para-docs@test.local", full_name="Docs", role="DOCS", password_hash="x")
        user = User(email="para-driver@test.local", full_name="Driver", role="DRIVER", password_hash="x",
                    driver_id=driver.id)
        s.add_all([staff, user])
        s.flush()
        shipment = Shipment(load_type="LCL", delivery_mode="VIA_WAREHOUSE", customer_id=customer.id,
                            staff_id=staff.id, carrier_id=carrier.id, pol_port_id=pol.id, pod_port_id=pod.id,
                            mbl_no="PARA000001", eta=date(2026, 9, 1), total_packages=10, status="DELIVERING")
        s.add(shipment)
        s.flush()
        orders = [LastMileOrder(shipment_id=shipment.id, tracking_code=f"PARA00000{i}", recipient_name="A B",
                                recipient_phone="0901234567", address="12 Le Loi, Q1", packages=5,
                                driver_id=driver.id, planned_date=date.today(), status="PICKED_UP") for i in (1, 2)]
        s.add_all(orders)
        s.commit()
        ids = SimpleNamespace(user=user.id, shipment=shipment.id, orders=[o.id for o in orders])
    yield ids
    with engine.begin() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")) if r[0] not in KEEP]
        conn.execute(text("SET session_replication_role = replica"))  # bỏ qua trigger append-only khi dọn
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))  # noqa: S608
        conn.execute(text("SET session_replication_role = DEFAULT"))


class _Upload:
    def __init__(self, data: bytes):
        self.file, self.size = io.BytesIO(data), len(data)


def test_parallel_last_two_deliveries_complete_once(engine, committed_world):
    barrier, errors = threading.Barrier(2), []

    def deliver(order_id: int) -> None:
        try:
            with Session(engine) as s:
                user = s.get(User, committed_world.user)
                form = ActionForm(uuid4(), "LM_DELIVER", order_id)
                barrier.wait(timeout=10)
                process_driver_action(s, user, form, _Upload(jpeg()))
                s.commit()
        except Exception as error:  # noqa: BLE001 - gom lại để assert ngoài luồng
            errors.append(error)

    threads = [threading.Thread(target=deliver, args=(oid,)) for oid in committed_world.orders]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    with Session(engine) as s:
        shipment = s.get(Shipment, committed_world.shipment)
        completed = s.scalar(select(func.count()).select_from(ShipmentEvent).where(
            ShipmentEvent.shipment_id == shipment.id, ShipmentEvent.to_status == "COMPLETED"))
        assert (shipment.status, completed) == ("COMPLETED", 1)
