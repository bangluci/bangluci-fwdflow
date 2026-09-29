"""Đọc đơn giao cho API nội bộ: danh sách lọc, chi tiết kèm timeline event."""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.catalog.models import Driver
from app.envelope import AppError
from app.events import effective_events
from app.lastmile.models import LastMileEvent, LastMileOrder
from app.lastmile.service import packages_available
from app.shipments.models import Shipment


def _row(order: LastMileOrder, shipment_code: str, driver_name: str | None) -> dict[str, Any]:
    return {"id": order.id, "shipment_id": order.shipment_id, "shipment_code": shipment_code,
            "tracking_code": order.tracking_code, "recipient_name": order.recipient_name,
            "recipient_phone": order.recipient_phone, "address": order.address, "packages": order.packages,
            "weight_kg": order.weight_kg, "driver_id": order.driver_id, "driver_name": driver_name,
            "planned_date": order.planned_date, "status": order.status, "created_at": order.created_at}


def list_orders(db: Session, shipment_id: int | None, status: str | None, driver_id: int | None,
                planned_date: date | None, tracking_code: str | None) -> tuple[list[dict[str, Any]], dict]:
    stmt = (select(LastMileOrder, Shipment.code, Driver.full_name)
            .join(Shipment, Shipment.id == LastMileOrder.shipment_id)
            .outerjoin(Driver, Driver.id == LastMileOrder.driver_id)
            .order_by(LastMileOrder.planned_date, LastMileOrder.id))
    for column, value in ((LastMileOrder.shipment_id, shipment_id), (LastMileOrder.status, status),
                          (LastMileOrder.driver_id, driver_id), (LastMileOrder.planned_date, planned_date),
                          (LastMileOrder.tracking_code, tracking_code)):
        if value is not None:
            stmt = stmt.where(column == value)
    meta: dict = {}
    if shipment_id is not None:
        shipment = db.get(Shipment, shipment_id)
        if shipment is not None:
            meta = {"total_packages": shipment.total_packages, "packages_available": packages_available(db, shipment)}
    return [_row(*row) for row in db.execute(stmt)], meta


def get_order(db: Session, order_id: int) -> dict[str, Any]:
    row = db.execute(select(LastMileOrder, Shipment.code, Driver.full_name)
                     .join(Shipment, Shipment.id == LastMileOrder.shipment_id)
                     .outerjoin(Driver, Driver.id == LastMileOrder.driver_id)
                     .where(LastMileOrder.id == order_id)).first()
    if row is None:
        raise AppError("NOT_FOUND", "Không tìm thấy đơn giao", 404)
    events = db.scalars(select(LastMileEvent).where(LastMileEvent.order_id == order_id)
                        .order_by(LastMileEvent.recorded_at, LastMileEvent.id)).all()
    live = {e.id for e in effective_events(events)}
    actors = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(
        {e.actor_id for e in events if e.actor_id})))}
    return _row(*row) | {"events": [
        {"id": e.id, "kind": e.kind, "occurred_at": e.occurred_at, "actor_id": e.actor_id,
         "actor_name": actors.get(e.actor_id), "reason": e.reason, "lat": e.lat, "lng": e.lng,
         "has_photo": e.photo_sha256 is not None, "voided": e.kind not in ("RETIME", "VOID") and e.id not in live}
        for e in events]}
