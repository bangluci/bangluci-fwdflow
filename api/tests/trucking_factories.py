"""Fixture nhà xe / lệnh xe cho test (đăng ký trong conftest bằng pytest_plugins)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.catalog.models import Driver, Truck, Trucker
from app.trucking.models import TruckingOrder, TruckingOrderEvent
from app.trucking.state import derive_status


@pytest.fixture
def make_trucker(db):
    """Một nhà xe có 1 xe và 1 tài xế (thêm bằng `extra_trucks` / `extra_drivers`)."""
    counter = iter(range(1, 10_000))

    def _make(name: str | None = None) -> SimpleNamespace:
        n = next(counter)
        trucker = Trucker(name=name or f"Nha xe {n}")
        db.add(trucker)
        db.flush()
        truck = Truck(trucker_id=trucker.id, plate_no=f"51C-{n:05d}")
        driver = Driver(trucker_id=trucker.id, full_name=f"Tai xe {n}")
        db.add_all([truck, driver])
        db.flush()
        return SimpleNamespace(trucker=trucker, truck=truck, driver=driver)

    return _make


@pytest.fixture
def make_trucking_order(db, make_trucker):
    """Lệnh xe dựng thẳng bằng ORM; `events` là danh sách loại event (`ASSIGNED`, `STARTED`, ...) ghi theo thứ tự
    và trạng thái cache lấy từ `derive_status`."""

    def _make(container, kind: str = "PICKUP_FULL", events: tuple[str, ...] = (), team=None,
              planned_at: datetime | None = None, **fields) -> TruckingOrder:
        team = team or make_trucker()
        order = TruckingOrder(
            shipment_id=container.shipment_id, container_id=container.id, kind=kind, trucker_id=team.trucker.id,
            pickup_location="Cảng Cát Lái", drop_location="Kho Bình Dương",
            planned_at=planned_at or datetime(2026, 11, 26, 8, 0, tzinfo=UTC), **fields)
        db.add(order)
        db.flush()
        start = datetime(2026, 11, 26, 9, 0, tzinfo=UTC)
        rows = []
        for i, event_kind in enumerate(events):
            assigned = event_kind in ("ASSIGNED", "REASSIGNED")
            row = TruckingOrderEvent(order_id=order.id, kind=event_kind, occurred_at=start + timedelta(minutes=i),
                                     truck_id=team.truck.id if assigned else None,
                                     driver_id=team.driver.id if assigned else None)
            db.add(row)
            rows.append(row)
        db.flush()
        if events:
            order.truck_id, order.driver_id = team.truck.id, team.driver.id
        order.status = derive_status(rows)
        db.flush()
        return order

    return _make
