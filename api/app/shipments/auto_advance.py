"""Bước lô hàng do hệ thống tự chuyển (actor null): điều kiện, chuyển tới, và đảo lại khi một event bị huỷ.

Cạnh tự động: CLEARED → AT_WAREHOUSE (FCL, mọi container lấy hàng xong), AT_WAREHOUSE → DELIVERING (đã lấy hàng giao),
AT_WAREHOUSE / DELIVERING → COMPLETED (giao tới cửa: mọi container trả rỗng; qua kho: giao đủ kiện, hết đơn dở).
"""

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.events import effective_events
from app.shipments.models import Container, Shipment, ShipmentEvent
from app.shipments.service import record_transition, utcnow
from app.shipments.state import ShipmentStatus

S = ShipmentStatus
AUTO_EDGES = {
    S.CLEARED: (S.AT_WAREHOUSE,),
    S.AT_WAREHOUSE: (S.DELIVERING, S.COMPLETED),
    S.DELIVERING: (S.COMPLETED,),
}
AUTO_TARGETS = frozenset(t for targets in AUTO_EDGES.values() for t in targets)

_PICKUPS_DONE = ("SELECT count(DISTINCT container_id) FROM trucking_orders WHERE shipment_id = :shipment_id "
                 "AND kind = 'PICKUP_FULL' AND status = 'COMPLETED'")
_EMPTIES_RETURNED = ("SELECT count(*) FROM effective_container_milestones m JOIN containers c ON c.id = m.container_id "
                     "WHERE c.shipment_id = :shipment_id AND m.kind = 'EMPTY_RETURNED'")
_ANY_PICKED_UP = ("SELECT count(*) FROM last_mile_events e JOIN last_mile_orders o ON o.id = e.order_id "
                  "WHERE o.shipment_id = :shipment_id AND e.kind = 'PICKED_UP' AND NOT EXISTS ("
                  "SELECT 1 FROM last_mile_events v WHERE v.kind = 'VOID' AND v.adjusts_event_id = e.id)")
_DELIVERY_DONE = ("SELECT coalesce(bool_or(status = 'DELIVERED'), false) AND NOT coalesce(bool_or(status IN "
                  "('CREATED', 'ASSIGNED', 'PICKED_UP', 'FAILED')), false) AND coalesce(sum(packages) FILTER "
                  "(WHERE status = 'DELIVERED'), 0) = :total FROM last_mile_orders WHERE shipment_id = :shipment_id")


def _all_containers_have(db: Session, shipment: Shipment, count_sql: str) -> bool:
    total = db.scalar(select(func.count()).select_from(Container).where(Container.shipment_id == shipment.id))
    return bool(total) and total == db.scalar(text(count_sql), {"shipment_id": shipment.id})


def _delivered_in_full(db: Session, shipment: Shipment) -> bool:
    if not db.scalar(text(_DELIVERY_DONE), {"shipment_id": shipment.id, "total": shipment.total_packages or 0}):
        return False
    return shipment.load_type != "FCL" or _all_containers_have(db, shipment, _EMPTIES_RETURNED)


def auto_condition_holds(db: Session, shipment: Shipment, to_status: str) -> bool:
    """Điều kiện để hệ thống tự đưa lô tới `to_status` (dùng chung cho chuyển tới và đảo lại khi huỷ event)."""
    if to_status == S.AT_WAREHOUSE:
        return shipment.load_type == "FCL" and _all_containers_have(db, shipment, _PICKUPS_DONE)
    if to_status == S.DELIVERING:
        return shipment.delivery_mode == "VIA_WAREHOUSE" and bool(
            db.scalar(text(_ANY_PICKED_UP), {"shipment_id": shipment.id}))
    if to_status == S.COMPLETED:
        if shipment.delivery_mode == "CONTAINER_TO_DOOR":
            return _all_containers_have(db, shipment, _EMPTIES_RETURNED)
        return _delivered_in_full(db, shipment)
    return False


def _reason(shipment: Shipment, to_status: str) -> str:
    if to_status == S.AT_WAREHOUSE:
        return "Tự chuyển: mọi container đã tới kho đích"
    if to_status == S.DELIVERING:
        return "Tự chuyển: đã có đơn giao được lấy hàng"
    if shipment.delivery_mode == "CONTAINER_TO_DOOR":
        return "Tự chuyển: mọi container đã trả rỗng"
    return "Tự chuyển: đã giao đủ kiện"


def try_auto_advance(db: Session, shipment: Shipment) -> bool:
    """Tự chuyển trạng thái lô tới khi hết cạnh hợp lệ; gọi sau mỗi thay đổi lệnh xe / đơn giao (lô đã bị khoá)."""
    moved = False
    while True:
        target = next((t for t in AUTO_EDGES.get(shipment.status, ()) if auto_condition_holds(db, shipment, t)), None)
        if target is None:
            return moved
        record_transition(db, shipment, target, None, from_status=shipment.status, reason=_reason(shipment, target))
        moved = True


def revert_auto_advance(db: Session, shipment: Shipment) -> None:
    """Sau khi huỷ một event: đảo các bước tự chuyển (actor null) không còn đủ điều kiện, dừng ở bước do người làm."""
    while True:
        events = db.scalars(select(ShipmentEvent).where(ShipmentEvent.shipment_id == shipment.id)).all()
        live = [e for e in effective_events(events) if e.kind == "TRANSITION"]
        if not live:
            return
        latest = next(e for e in events if e.id == live[-1].id)
        if (latest.actor_id is not None or latest.to_status not in AUTO_TARGETS
                or auto_condition_holds(db, shipment, latest.to_status)):
            return
        db.add(ShipmentEvent(shipment_id=shipment.id, kind="VOID", adjusts_event_id=latest.id, occurred_at=utcnow(),
                             actor_id=None, reason=f"Đảo do huỷ event #{latest.id}"))
        shipment.status = latest.from_status
        db.flush()
