"""Fixture đơn giao nội địa cho test (đăng ký trong conftest bằng pytest_plugins)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.lastmile.models import LastMileEvent, LastMileOrder
from app.lastmile.state import derive_status
from app.lastmile.tracking_code import new_tracking_code


@pytest.fixture
def make_last_mile_order(db, make_driver):
    """Đơn giao dựng thẳng bằng ORM; `events` là danh sách loại event ghi theo thứ tự, trạng thái lấy từ `derive_status`.

    Có event ASSIGNED / REASSIGNED thì đơn gắn với `driver` (mặc định tạo tài xế mới)."""

    def _make(shipment, packages: int = 1, events: tuple[str, ...] = ("CREATED",), driver=None,
              planned_date=None, started_at: datetime | None = None, **fields) -> LastMileOrder:
        driver = driver or make_driver()
        order = LastMileOrder(
            shipment_id=shipment.id, tracking_code=fields.pop("tracking_code", new_tracking_code()),
            recipient_name=fields.pop("recipient_name", "Nguyễn Văn An"),
            recipient_phone=fields.pop("recipient_phone", "0901234567"),
            address=fields.pop("address", "12 Lê Lợi, Quận 1, TP.HCM"), packages=packages,
            planned_date=planned_date or db.scalar(text("SELECT nlq_today()")), **fields)
        db.add(order)
        db.flush()
        start = started_at or datetime.now(UTC) - timedelta(hours=len(events) + 1)
        rows = []
        for i, kind in enumerate(events):
            row = LastMileEvent(order_id=order.id, kind=kind, occurred_at=start + timedelta(minutes=i),
                                driver_id=driver.team.driver.id if kind in ("ASSIGNED", "REASSIGNED") else None)
            db.add(row)
            rows.append(row)
        db.flush()
        if any(e in ("ASSIGNED", "REASSIGNED") for e in events):
            order.driver_id = driver.team.driver.id
        order.status = derive_status(rows)
        db.flush()
        order.owner = driver  # tiện cho test: tài xế đang phụ trách
        return order

    return _make
