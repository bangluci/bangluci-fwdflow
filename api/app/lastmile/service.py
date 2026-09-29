"""Nghiệp vụ đơn giao nội địa: tách đơn từ quỹ kiện, phân công, đổi tài xế, huỷ, hoàn về kho, huỷ event.

Mỗi hàm ghi đi theo thứ tự: khoá lô → kiểm cạnh → event → cột cache `status` → tự chuyển lô → audit. Không tự commit.
"""

from datetime import UTC, date, datetime

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.service import record_audit, snapshot
from app.auth.models import User
from app.catalog.models import Driver
from app.driver.actions import DriverCall, DriverResult, driver_event_fields
from app.envelope import AppError
from app.events import effective_events
from app.lastmile.models import EVENT_FIELDS, ORDER_FIELDS, LastMileEvent, LastMileOrder
from app.lastmile.schemas import OrderIn
from app.lastmile.state import POOL_EXCLUDED, LastMileStatus, assert_transition, derive_status
from app.lastmile.tracking_code import new_tracking_code
from app.shipments.auto_advance import revert_auto_advance, try_auto_advance
from app.shipments.models import Shipment
from app.shipments.service import lock_shipment
from app.shipments.state import ShipmentStatus

L = LastMileStatus
SPLITTABLE = (ShipmentStatus.AT_WAREHOUSE, ShipmentStatus.DELIVERING)
CODE_ATTEMPTS = 3
VOIDABLE = ("PICKED_UP", "DELIVERED", "FAILED")


def _now() -> datetime:
    return datetime.now(UTC)


def _today(db: Session) -> date:
    return db.scalar(text("SELECT nlq_today()"))


def packages_available(db: Session, shipment: Shipment) -> int:
    """Quỹ kiện còn lại của lô: tổng kiện trừ kiện của các đơn chưa bị huỷ / hoàn về."""
    used = db.scalar(select(func.coalesce(func.sum(LastMileOrder.packages), 0)).where(
        LastMileOrder.shipment_id == shipment.id, LastMileOrder.status.notin_(list(POOL_EXCLUDED))))
    return (shipment.total_packages or 0) - used


def _check_driver_and_date(db: Session, driver_id: int | None, planned_date: date) -> None:
    if planned_date < _today(db):
        raise AppError("INVALID_PLANNED_DATE", "Ngày giao dự kiến không được ở quá khứ", 400)
    if driver_id is not None:
        driver = db.get(Driver, driver_id)
        if driver is None or not driver.active:
            raise AppError("INVALID_DRIVER", "Tài xế không tồn tại hoặc đã ngừng dùng", 400)


def _add_event(db: Session, order: LastMileOrder, kind: str, actor_id: int | None, **fields) -> LastMileEvent:
    event = LastMileEvent(order_id=order.id, kind=kind, occurred_at=_now(), actor_id=actor_id, **fields)
    db.add(event)
    db.flush()
    return event


def _new_order(db: Session, shipment: Shipment, data: OrderIn, actor: User) -> LastMileOrder:
    values = data.model_dump(exclude={"driver_id"})
    for _ in range(CODE_ATTEMPTS):
        order = LastMileOrder(shipment_id=shipment.id, tracking_code=new_tracking_code(), created_by=actor.id,
                              driver_id=data.driver_id, status=L.ASSIGNED if data.driver_id else L.CREATED, **values)
        try:
            with db.begin_nested():
                db.add(order)
                db.flush()
            return order
        except IntegrityError:
            continue
    raise AppError("TRACKING_CODE_COLLISION", "Không sinh được mã tra cứu, thử lại", 500)


def create_orders(db: Session, actor: User, shipment_id: int, orders: list[OrderIn]) -> list[LastMileOrder]:
    shipment = lock_shipment(db, shipment_id)
    if shipment.delivery_mode != "VIA_WAREHOUSE":
        raise AppError("WRONG_DELIVERY_MODE", "Chỉ tách đơn giao cho lô giao qua kho", 409)
    if shipment.status not in SPLITTABLE:
        raise AppError("SHIPMENT_NOT_AT_WAREHOUSE", "Lô chưa về kho hoặc đã đóng, chưa tách đơn được", 409)
    for data in orders:
        _check_driver_and_date(db, data.driver_id, data.planned_date)
    available = packages_available(db, shipment)
    if sum(o.packages for o in orders) > available:
        raise AppError("PACKAGES_EXCEEDED", f"Số kiện vượt quỹ kiện còn lại ({available})", 409,
                       details={"available": available})
    made = []
    for data in orders:
        order = _new_order(db, shipment, data, actor)
        _add_event(db, order, "CREATED", actor.id)
        if data.driver_id:
            _add_event(db, order, "ASSIGNED", actor.id, driver_id=data.driver_id)
        record_audit(db, actor.id, "CREATE", "last_mile_order", order.id, after=snapshot(order, ORDER_FIELDS))
        made.append(order)
    try_auto_advance(db, shipment)
    return made


def _lock_order(db: Session, order_id: int) -> tuple[LastMileOrder, Shipment]:
    order = db.get(LastMileOrder, order_id)
    if order is None:
        raise AppError("NOT_FOUND", "Không tìm thấy đơn giao", 404)
    shipment = lock_shipment(db, order.shipment_id)
    db.refresh(order)
    return order, shipment


def _change(db: Session, actor: User, order: LastMileOrder, shipment: Shipment, action: str, kind: str,
            to_status: str | None = None, **event_fields) -> LastMileOrder:
    before = snapshot(order, ORDER_FIELDS)
    _add_event(db, order, kind, actor.id, **event_fields)
    if to_status:
        order.status = to_status
    if "driver_id" in event_fields:
        order.driver_id = event_fields["driver_id"]
    db.flush()
    try_auto_advance(db, shipment)
    record_audit(db, actor.id, action, "last_mile_order", order.id, before=before,
                 after=snapshot(order, ORDER_FIELDS))
    return order


def assign_order(db: Session, actor: User, order_id: int, driver_id: int, planned_date: date) -> LastMileOrder:
    order, shipment = _lock_order(db, order_id)
    assert_transition(order.status, L.ASSIGNED)  # CREATED hoặc FAILED (giao lại)
    _check_driver_and_date(db, driver_id, planned_date)
    order.planned_date = planned_date
    return _change(db, actor, order, shipment, "ASSIGN", "ASSIGNED", L.ASSIGNED, driver_id=driver_id)


def reassign_order(db: Session, actor: User, order_id: int, driver_id: int, planned_date: date | None,
                   reason: str) -> LastMileOrder:
    order, shipment = _lock_order(db, order_id)
    if order.status != L.ASSIGNED:
        raise AppError("INVALID_TRANSITION", "Chỉ đổi tài xế khi đơn đang ở trạng thái đã phân công", 409)
    _check_driver_and_date(db, driver_id, planned_date or order.planned_date)
    if planned_date:
        order.planned_date = planned_date
    return _change(db, actor, order, shipment, "REASSIGN", "REASSIGNED", driver_id=driver_id, reason=reason)


def cancel_order(db: Session, actor: User, order_id: int, reason: str) -> LastMileOrder:
    order, shipment = _lock_order(db, order_id)
    assert_transition(order.status, L.CANCELLED)
    return _change(db, actor, order, shipment, "CANCEL", "CANCELLED", L.CANCELLED, reason=reason)


def return_order(db: Session, actor: User, order_id: int, reason: str) -> LastMileOrder:
    order, shipment = _lock_order(db, order_id)
    assert_transition(order.status, L.RETURNED)
    return _change(db, actor, order, shipment, "RETURN", "RETURNED", L.RETURNED, reason=reason)


def _driver_step(db: Session, call: DriverCall) -> DriverResult:
    order: LastMileOrder = call.order
    fields = driver_event_fields(call)
    fields.pop("signer_name")  # đơn giao không lưu người ký
    event = LastMileEvent(order_id=order.id, driver_id=order.driver_id, **fields)
    db.add(event)
    before = snapshot(order, ORDER_FIELDS)
    order.status = call.action.to_status
    db.flush()
    record_audit(db, call.user.id, "CREATE", "last_mile_event", event.id, after=snapshot(event, EVENT_FIELDS))
    record_audit(db, call.user.id, "UPDATE", "last_mile_order", order.id, before=before,
                 after=snapshot(order, ORDER_FIELDS))
    try_auto_advance(db, call.shipment)
    return DriverResult(event.id, "LAST_MILE", order.id, order.status, event.occurred_at)


def pick_up_order(db: Session, call: DriverCall) -> DriverResult:
    return _driver_step(db, call)


def deliver_order(db: Session, call: DriverCall) -> DriverResult:
    return _driver_step(db, call)


def fail_order(db: Session, call: DriverCall) -> DriverResult:
    return _driver_step(db, call)


def void_event(db: Session, actor: User, order_id: int, event_id: int, reason: str) -> LastMileOrder:
    """Huỷ event PICKED_UP / DELIVERED / FAILED mới nhất, tính lại trạng thái và đảo bước tự chuyển của lô."""
    order, shipment = _lock_order(db, order_id)
    events = list(db.scalars(select(LastMileEvent).where(LastMileEvent.order_id == order.id)
                             .order_by(LastMileEvent.recorded_at, LastMileEvent.id)))
    target = next((e for e in events if e.id == event_id), None)
    if target is None:
        raise AppError("NOT_FOUND", "Không tìm thấy event", 404)
    live = effective_events(events)
    if not live or live[-1].id != event_id:
        raise AppError("NOT_LATEST_EVENT", "Chỉ huỷ được event mới nhất còn hiệu lực của đơn", 409)
    if target.kind not in VOIDABLE:
        raise AppError("NOT_VOIDABLE", "Chỉ huỷ được event lấy hàng / giao xong / giao thất bại", 409)
    before = snapshot(order, ORDER_FIELDS)
    void = _add_event(db, order, "VOID", actor.id, adjusts_event_id=event_id, reason=reason)
    order.status = derive_status(events + [void])
    db.flush()
    record_audit(db, actor.id, "VOID", "last_mile_event", void.id, after=snapshot(void, EVENT_FIELDS))
    record_audit(db, actor.id, "UPDATE", "last_mile_order", order.id, before=before,
                 after=snapshot(order, ORDER_FIELDS))
    revert_auto_advance(db, shipment)
    return order
