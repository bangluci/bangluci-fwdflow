"""Nghiệp vụ lệnh xe: tạo, phân công, đổi xe / tài xế, huỷ. Hàm không tự commit; mỗi hàm mở đầu bằng khoá lô."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.service import record_audit, register_audit_fields, snapshot
from app.auth.models import User
from app.catalog.models import Driver, Truck, Trucker
from app.envelope import AppError
from app.shipments.models import Container
from app.shipments.service import lock_shipment
from app.shipments.state import ShipmentStatus
from app.trucking.models import TruckingOrder, TruckingOrderEvent
from app.trucking.schemas import OrderCreate
from app.trucking.state import TruckingStatus, assert_can_reassign, assert_transition

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
