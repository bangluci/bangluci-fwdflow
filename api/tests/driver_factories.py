"""Dữ liệu chung cho test app tài xế: tài xế đăng nhập, ảnh JPEG, gửi thao tác multipart."""

import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import text

from app.auth.service import create_session
from app.catalog.models import Driver, Truck, Trucker
from app.config import get_settings

ACTIONS_URL = "/api/driver/actions"


def jpeg(color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buffer, "JPEG")
    return buffer.getvalue()


def discharged_at() -> datetime:
    return datetime.now(UTC) - timedelta(days=2)


@pytest.fixture
def make_driver(db, make_user):
    """Tài xế (user + nhà xe + xe) — chưa đăng nhập."""

    def _make() -> SimpleNamespace:
        user = make_user("DRIVER")
        driver = db.get(Driver, user.driver_id)
        truck = Truck(trucker_id=driver.trucker_id, plate_no=f"51D-{user.id:05d}")
        db.add(truck)
        db.flush()
        return SimpleNamespace(user=user, team=SimpleNamespace(trucker=db.get(Trucker, driver.trucker_id),
                                                               truck=truck, driver=driver))

    return _make


@pytest.fixture
def switch_to(client, db):
    def _switch(user) -> None:
        token = create_session(db, user, "127.0.0.1", "pytest")
        db.flush()
        client.cookies.set(get_settings().session_cookie_name, token)

    return _switch


@pytest.fixture
def driver(make_driver, switch_to):
    """Tài xế đã đăng nhập."""
    made = make_driver()
    switch_to(made.user)
    return made


@pytest.fixture
def today(db):
    return db.scalar(text("SELECT nlq_today()"))


@pytest.fixture
def send(client):
    """`send(action, target_id, photo=None, request_id=None, **fields)` → response."""

    def _send(action: str, target_id: int, photo: bytes | None = None, request_id: str | None = None, **fields):
        data = {"client_request_id": request_id or str(uuid4()), "action": action, "target_id": str(target_id),
                **{k: str(v) for k, v in fields.items()}}
        files = {"photo": ("photo.jpg", photo, "image/jpeg")} if photo is not None else None
        return client.post(ACTIONS_URL, data=data, files=files)

    return _send


@pytest.fixture
def ready_order(db, driver, make_shipment, make_container, make_trucking_order):
    """Lô `CLEARED` đã dỡ hàng, một lệnh `PICKUP_FULL` `ASSIGNED` của tài xế đang đăng nhập."""

    def _make(kind="PICKUP_FULL", events=("ASSIGNED",), delivery_mode="VIA_WAREHOUSE", status="CLEARED",
              shipment=None, container=None, team=None, **fields):
        shipment = shipment or make_shipment(status=status, delivery_mode=delivery_mode)
        container = container or make_container(shipment, milestones={"DISCHARGED": discharged_at()})
        order = make_trucking_order(container, kind, events=events, team=team or driver.team, **fields)
        return SimpleNamespace(shipment=shipment, container=container, order=order)

    return _make
