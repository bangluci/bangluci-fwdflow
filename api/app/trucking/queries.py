"""Đọc lệnh xe cho API: danh sách lọc theo ngày VN của `planned_at`, chi tiết kèm event."""

from datetime import date
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.catalog.models import Driver, Truck, Trucker
from app.envelope import AppError
from app.events import effective_events
from app.shipments.models import Container, Shipment
from app.trucking.models import TruckingOrder, TruckingOrderEvent

PLANNED_DAY_VN = func.date(func.timezone("Asia/Ho_Chi_Minh", TruckingOrder.planned_at))


def _base() -> Select:
    return (select(TruckingOrder, Shipment.code, Container.container_no, Trucker.name, Truck.plate_no,
                   Driver.full_name)
            .join(Shipment, Shipment.id == TruckingOrder.shipment_id)
            .join(Container, Container.id == TruckingOrder.container_id)
            .join(Trucker, Trucker.id == TruckingOrder.trucker_id)
            .outerjoin(Truck, Truck.id == TruckingOrder.truck_id)
            .outerjoin(Driver, Driver.id == TruckingOrder.driver_id))


def _row(order: TruckingOrder, shipment_code, container_no, trucker_name, plate_no, driver_name) -> dict[str, Any]:
    return {"id": order.id, "shipment_id": order.shipment_id, "shipment_code": shipment_code,
            "container_id": order.container_id, "container_no": container_no, "kind": order.kind,
            "trucker_id": order.trucker_id, "trucker_name": trucker_name, "truck_id": order.truck_id,
            "plate_no": plate_no, "driver_id": order.driver_id, "driver_name": driver_name,
            "pickup_location": order.pickup_location, "drop_location": order.drop_location,
            "planned_at": order.planned_at, "status": order.status}


def list_orders(db: Session, date_from: date | None, date_to: date | None, kind: str | None, status: str | None,
                shipment_id: int | None) -> list[dict[str, Any]]:
    stmt = _base().order_by(TruckingOrder.planned_at, TruckingOrder.id)
    if date_from is not None:
        stmt = stmt.where(PLANNED_DAY_VN >= date_from)
    if date_to is not None:
        stmt = stmt.where(PLANNED_DAY_VN <= date_to)
    for column, value in ((TruckingOrder.kind, kind), (TruckingOrder.status, status),
                          (TruckingOrder.shipment_id, shipment_id)):
        if value is not None:
            stmt = stmt.where(column == value)
    return [_row(*row) for row in db.execute(stmt)]


def get_order(db: Session, order_id: int) -> dict[str, Any]:
    row = db.execute(_base().where(TruckingOrder.id == order_id)).first()
    if row is None:
        raise AppError("NOT_FOUND", "Không tìm thấy lệnh xe", 404)
    events = db.scalars(select(TruckingOrderEvent).where(TruckingOrderEvent.order_id == order_id)
                        .order_by(TruckingOrderEvent.recorded_at, TruckingOrderEvent.id)).all()
    live = {e.id for e in effective_events(events)}
    return _row(*row) | {"events": [
        {"id": e.id, "kind": e.kind, "occurred_at": e.occurred_at, "recorded_at": e.recorded_at,
         "actor_id": e.actor_id, "reason": e.reason, "truck_id": e.truck_id, "driver_id": e.driver_id,
         "voided": e.kind not in ("RETIME", "VOID") and e.id not in live} for e in events]}
