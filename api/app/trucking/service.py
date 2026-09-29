"""Nghiệp vụ lệnh xe: tạo, phân công, đổi xe / tài xế, huỷ. Hàm không tự commit; mỗi hàm mở đầu bằng khoá lô."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.service import record_audit, register_audit_fields, snapshot
from app.auth.models import User
from app.catalog.models import Driver, Truck, Trucker
from app.driver.actions import DriverCall, DriverResult, driver_event_fields
from app.envelope import AppError
from app.events import effective_events
from app.shipments.auto_advance import revert_auto_advance, try_auto_advance
from app.shipments.containers import add_container_event, retime_container_event, void_container_event
from app.shipments.models import Container, ContainerEvent, Shipment
from app.shipments.service import lock_shipment
from app.shipments.state import ShipmentStatus
from app.trucking.models import TruckingOrder, TruckingOrderEvent
from app.trucking.schemas import OrderCreate
from app.trucking.state import TruckingStatus, assert_can_reassign, assert_transition, derive_status

ORDER_FIELDS = ("shipment_id", "container_id", "kind", "trucker_id", "truck_id", "driver_id", "pickup_location",
                "drop_location", "planned_at", "status")
EVENT_FIELDS = ("order_id", "kind", "truck_id", "driver_id", "reason", "signer_name", "lat", "lng")
register_audit_fields("trucking_order", ORDER_FIELDS)
register_audit_fields("trucking_order_event", EVENT_FIELDS)

CLOSED_SHIPMENT = (ShipmentStatus.CANCELLED, ShipmentStatus.COMPLETED)


def _now() -> datetime:
    return datetime.now(UTC)


def _reason(reason: str) -> str:
    if not reason.strip():
        raise AppError("REASON_REQUIRED", "Cần nhập lý do", 422)
    return reason.strip()


def _lock_order(db: Session, order_id: int) -> TruckingOrder:
    """Khoá lô của lệnh trước, rồi đọc lại lệnh để thấy trạng thái mới nhất."""
    order = db.get(TruckingOrder, order_id)
    if order is None:
        raise AppError("NOT_FOUND", "Không tìm thấy lệnh xe", 404)
    lock_shipment(db, order.shipment_id)
    db.refresh(order)
    return order


def _check_team(db: Session, order: TruckingOrder, truck_id: int, driver_id: int) -> None:
    truck, driver = db.get(Truck, truck_id), db.get(Driver, driver_id)
    if truck is None or driver is None:
        raise AppError("INACTIVE_REFERENCE", "Xe hoặc tài xế không tồn tại", 422)
    if truck.trucker_id != order.trucker_id or driver.trucker_id != order.trucker_id:
        raise AppError("TRUCKER_MISMATCH", "Xe và tài xế phải thuộc nhà xe của lệnh", 422)
    if not truck.active or not driver.active:
        raise AppError("INACTIVE_REFERENCE", "Xe hoặc tài xế đã ngừng dùng", 422)


def add_event(db: Session, order: TruckingOrder, kind: str, actor_id: int | None, **fields) -> TruckingOrderEvent:
    event = TruckingOrderEvent(order_id=order.id, kind=kind, occurred_at=_now(), actor_id=actor_id, **fields)
    db.add(event)
    db.flush()
    return event


def _duplicate() -> AppError:
    return AppError("DUPLICATE_ORDER", "Container đã có lệnh xe cùng loại chưa huỷ", 409)


def create_order(db: Session, actor: User, data: OrderCreate) -> TruckingOrder:
    container = db.get(Container, data.container_id)
    if container is None:
        raise AppError("NOT_FOUND", "Không tìm thấy container", 404)
    shipment = lock_shipment(db, container.shipment_id)
    if shipment.load_type != "FCL":
        raise AppError("NOT_FCL", "Chỉ điều xe cho container của lô FCL", 422)
    if shipment.status in CLOSED_SHIPMENT:
        raise AppError("SHIPMENT_CLOSED", "Lô đã đóng, không tạo lệnh xe được", 409)
    trucker = db.get(Trucker, data.trucker_id)
    if trucker is None or not trucker.active:
        raise AppError("INACTIVE_REFERENCE", "Nhà xe không tồn tại hoặc đã ngừng dùng", 422)
    orders = db.scalars(select(TruckingOrder).where(TruckingOrder.container_id == container.id,
                                                    TruckingOrder.status != TruckingStatus.CANCELLED)).all()
    if any(o.kind == data.kind for o in orders):
        raise _duplicate()
    if data.kind == "RETURN_EMPTY" and not any(
            o.kind == "PICKUP_FULL" and o.status == TruckingStatus.COMPLETED for o in orders):
        raise AppError("PICKUP_NOT_COMPLETED", "Chỉ trả vỏ sau khi lệnh lấy hàng đầy đã hoàn tất", 409)
    order = TruckingOrder(**data.model_dump(), shipment_id=shipment.id, created_by_id=actor.id)
    try:
        with db.begin_nested():
            db.add(order)
            db.flush()
    except IntegrityError as error:
        raise _duplicate() from error
    record_audit(db, actor.id, "CREATE", "trucking_order", order.id, after=snapshot(order, ORDER_FIELDS))
    return order


def _staff_event(db: Session, actor: User, order: TruckingOrder, action: str, kind: str, to_status: str | None = None,
                 **fields) -> TruckingOrder:
    before = snapshot(order, ORDER_FIELDS)
    add_event(db, order, kind, actor.id, **fields)
    if to_status:
        order.status = to_status
    if "truck_id" in fields:
        order.truck_id, order.driver_id = fields["truck_id"], fields["driver_id"]
    db.flush()
    record_audit(db, actor.id, action, "trucking_order", order.id, before=before, after=snapshot(order, ORDER_FIELDS))
    return order


def assign_order(db: Session, actor: User, order_id: int, truck_id: int, driver_id: int) -> TruckingOrder:
    order = _lock_order(db, order_id)
    assert_transition(order.status, TruckingStatus.ASSIGNED)
    _check_team(db, order, truck_id, driver_id)
    return _staff_event(db, actor, order, "ASSIGN", "ASSIGNED", TruckingStatus.ASSIGNED, truck_id=truck_id,
                        driver_id=driver_id)


def reassign_order(db: Session, actor: User, order_id: int, truck_id: int, driver_id: int, reason: str
                   ) -> TruckingOrder:
    order = _lock_order(db, order_id)
    assert_can_reassign(order.status)
    reason = _reason(reason)
    _check_team(db, order, truck_id, driver_id)
    return _staff_event(db, actor, order, "REASSIGN", "REASSIGNED", truck_id=truck_id, driver_id=driver_id,
                        reason=reason)


def cancel_order(db: Session, actor: User, order_id: int, reason: str) -> TruckingOrder:
    order = _lock_order(db, order_id)
    assert_transition(order.status, TruckingStatus.CANCELLED)
    return _staff_event(db, actor, order, "CANCEL", "CANCELLED", TruckingStatus.CANCELLED, reason=_reason(reason))


def _driver_event(db: Session, call: DriverCall) -> TruckingOrderEvent:
    order = call.order
    event = TruckingOrderEvent(order_id=order.id, truck_id=order.truck_id, driver_id=order.driver_id,
                               **driver_event_fields(call))
    db.add(event)
    db.flush()
    record_audit(db, call.user.id, "CREATE", "trucking_order_event", event.id, after=snapshot(event, EVENT_FIELDS))
    return event


def _finish_driver_step(db: Session, call: DriverCall, event: TruckingOrderEvent) -> DriverResult:
    order, before = call.order, {"status": call.order.status}
    order.status = call.action.to_status
    db.flush()
    record_audit(db, call.user.id, "UPDATE", "trucking_order", order.id, before=before, after={"status": order.status})
    return DriverResult(event.id, "TRUCKING", order.id, order.status, event.occurred_at)


def _has_discharged(db: Session, container_id: int) -> bool:
    events = db.scalars(select(ContainerEvent).where(ContainerEvent.container_id == container_id)).all()
    return any(e.kind == "DISCHARGED" for e in effective_events(events))


def start_order(db: Session, call: DriverCall) -> DriverResult:
    """`TRUCK_START` ghi thêm mốc GATE_OUT_FULL cùng giờ; `RETURN_START` chỉ đổi trạng thái lệnh."""
    order = call.order
    if order.kind == "PICKUP_FULL":
        if call.shipment.status != ShipmentStatus.CLEARED:
            raise AppError("SHIPMENT_NOT_CLEARED", "Lô chưa thông quan, chưa lấy cont được", 409)
        if not _has_discharged(db, order.container_id):
            raise AppError("NOT_DISCHARGED", "Container chưa được ghi nhận dỡ khỏi tàu", 409)
        # mốc container trước: sai thứ tự / giờ thì lỗi ngay, chưa ghi gì
        add_container_event(db, order.container_id, "GATE_OUT_FULL", call.occurred_at, call.user)
    return _finish_driver_step(db, call, _driver_event(db, call))


def complete_order(db: Session, call: DriverCall) -> DriverResult:
    """Hoàn tất lệnh: lấy hàng đầy có thể đẩy lô sang AT_WAREHOUSE, trả vỏ ghi EMPTY_RETURNED (rồi có thể COMPLETED)."""
    if call.order.kind == "RETURN_EMPTY":
        add_container_event(db, call.order.container_id, "EMPTY_RETURNED", call.occurred_at, call.user)
    result = _finish_driver_step(db, call, _driver_event(db, call))
    try_auto_advance(db, call.shipment)
    return result


# Cặp event vận chuyển ↔ mốc container (lấy hàng đầy ↔ GATE_OUT_FULL, trả vỏ xong ↔ EMPTY_RETURNED)
PAIRED_MILESTONE = {("PICKUP_FULL", "STARTED"): "GATE_OUT_FULL", ("RETURN_EMPTY", "COMPLETED"): "EMPTY_RETURNED"}
ADJUSTABLE = ("STARTED", "COMPLETED")
RETIME_FUTURE_LIMIT = timedelta(minutes=5)


def _order_events(db: Session, order_id: int) -> list[TruckingOrderEvent]:
    return list(db.scalars(select(TruckingOrderEvent).where(TruckingOrderEvent.order_id == order_id)
                           .order_by(TruckingOrderEvent.recorded_at, TruckingOrderEvent.id)))


def _paired_container_event(db: Session, order: TruckingOrder, event: TruckingOrderEvent) -> ContainerEvent | None:
    kind = PAIRED_MILESTONE.get((order.kind, event.kind))
    if kind is None:
        return None
    events = db.scalars(select(ContainerEvent).where(ContainerEvent.container_id == order.container_id)).all()
    live = next((e for e in effective_events(events) if e.kind == kind), None)
    return next((e for e in events if live and e.id == live.id), None)


def void_trucking_event(db: Session, actor: User, order_id: int, event_id: int, reason: str) -> TruckingOrder:
    """Huỷ event `STARTED` / `COMPLETED` mới nhất của lệnh, huỷ mốc container đi cặp và đảo bước tự chuyển của lô."""
    order = _lock_order(db, order_id)
    reason = _reason(reason)
    events = _order_events(db, order.id)
    live = effective_events(events)
    target = next((e for e in events if e.id == event_id and e.order_id == order.id), None)
    if target is None:
        raise AppError("NOT_FOUND", "Không tìm thấy event", 404)
    if not live or live[-1].id != event_id:
        raise AppError("NOT_LATEST_EVENT", "Chỉ huỷ được event mới nhất còn hiệu lực của lệnh", 409)
    if target.kind not in ADJUSTABLE:
        raise AppError("NOT_VOIDABLE", "Chỉ huỷ được event lấy cont / hoàn tất", 409)
    if order.kind == "PICKUP_FULL" and target.kind == "COMPLETED" and db.scalar(
            select(TruckingOrder.id).where(TruckingOrder.container_id == order.container_id,
                                           TruckingOrder.kind == "RETURN_EMPTY",
                                           TruckingOrder.status != TruckingStatus.CANCELLED).limit(1)):
        raise AppError("DEPENDENT_ORDER_EXISTS", "Container đã có lệnh trả vỏ, huỷ lệnh đó trước", 409)
    before = snapshot(order, ORDER_FIELDS)
    paired = _paired_container_event(db, order, target)
    if paired is not None:
        void_container_event(db, order.container_id, paired.id, reason, actor)
    void = TruckingOrderEvent(order_id=order.id, kind="VOID", adjusts_event_id=event_id, occurred_at=_now(),
                              actor_id=actor.id, reason=reason)
    db.add(void)
    db.flush()
    order.status = derive_status(events + [void])
    db.flush()
    record_audit(db, actor.id, "VOID", "trucking_order_event", void.id, after=snapshot(void, EVENT_FIELDS))
    record_audit(db, actor.id, "UPDATE", "trucking_order", order.id, before=before,
                 after=snapshot(order, ORDER_FIELDS))
    revert_auto_advance(db, db.get(Shipment, order.shipment_id))
    return order


def retime_trucking_event(db: Session, actor: User, order_id: int, event_id: int, occurred_at: datetime,
                          reason: str) -> TruckingOrderEvent:
    """Chỉnh giờ event `STARTED` / `COMPLETED`; mốc container đi cặp đổi cùng giờ, sai thứ tự thì không ghi gì."""
    if occurred_at.tzinfo is None:
        raise AppError("VALIDATION_ERROR", "occurred_at phải có múi giờ", 422)
    if occurred_at > _now() + RETIME_FUTURE_LIMIT:
        raise AppError("VALIDATION_ERROR", "Thời điểm không được ở tương lai", 422)
    order = _lock_order(db, order_id)
    reason = _reason(reason)
    events = _order_events(db, order.id)
    target = next((e for e in effective_events(events) if e.id == event_id), None)
    if target is None or target.kind not in ADJUSTABLE:
        raise AppError("INVALID_ADJUSTMENT", "Không chỉnh giờ được event này", 400)
    paired = _paired_container_event(db, order, next(e for e in events if e.id == event_id))
    if paired is not None:  # mốc container trước: sai thứ tự thì lỗi ngay, chưa ghi gì
        retime_container_event(db, order.container_id, paired.id, occurred_at, reason, actor)
    retime = TruckingOrderEvent(order_id=order.id, kind="RETIME", adjusts_event_id=event_id, occurred_at=occurred_at,
                                actor_id=actor.id, reason=reason)
    db.add(retime)
    db.flush()
    record_audit(db, actor.id, "RETIME", "trucking_order_event", retime.id, after=snapshot(retime, EVENT_FIELDS))
    return retime
