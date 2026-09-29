"""Container của lô FCL và các mốc DISCHARGED / GATE_OUT_FULL / EMPTY_RETURNED (append-only, chỉnh giờ bằng RETIME)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record_audit, snapshot
from app.auth.models import User
from app.envelope import AppError
from app.events import EffectiveEvent, effective_events
from app.shipments.audit_fields import CONTAINER_EVENT_FIELDS, CONTAINER_FIELDS
from app.shipments.iso6346 import is_valid_container_no, normalize_container_no
from app.shipments.models import Container, ContainerEvent, Shipment
from app.shipments.schemas import ContainerIn
from app.shipments.service import assert_open, get_open_shipment, lock_shipment, utcnow
from app.shipments.state import CONTAINER_MILESTONE_ORDER, DISCHARGE_ALLOWED
from app.shipments.validation import validate_patch

CONTAINER_INPUT_FIELDS = tuple(ContainerIn.model_fields)


def _events(db: Session, container_id: int) -> list[ContainerEvent]:
    return list(db.scalars(select(ContainerEvent).where(ContainerEvent.container_id == container_id)
                           .order_by(ContainerEvent.id)))


def _get_container(db: Session, shipment_id: int, container_id: int) -> Container:
    container = db.get(Container, container_id)
    if container is None or container.shipment_id != shipment_id:
        raise AppError("NOT_FOUND", "Không tìm thấy container", 404)
    return container


def _valid_number(db: Session, shipment_id: int, raw: str, except_id: int | None = None) -> str:
    number = normalize_container_no(raw)
    if not is_valid_container_no(number):
        raise AppError("INVALID_CONTAINER_NO", "Số container sai check digit ISO 6346", 400)
    existing = db.scalar(select(Container.id).where(Container.shipment_id == shipment_id,
                                                    Container.container_no == number))
    if existing is not None and existing != except_id:
        raise AppError("DUPLICATE_CONTAINER", "Container đã có trong lô", 409)
    return number


def add_container(db: Session, shipment_id: int, data: ContainerIn, actor: User) -> Container:
    shipment = get_open_shipment(db, shipment_id)
    if shipment.load_type != "FCL":
        raise AppError("CONTAINERS_FCL_ONLY", "Chỉ lô FCL mới có container", 409)
    values = data.model_dump()
    values["container_no"] = _valid_number(db, shipment_id, data.container_no)
    container = Container(shipment_id=shipment_id, **values)
    db.add(container)
    db.flush()
    record_audit(db, actor.id, "CREATE", "container", container.id, after=snapshot(container, CONTAINER_FIELDS))
    return container


def update_container(db: Session, shipment_id: int, container_id: int, payload: dict, actor: User) -> Container:
    get_open_shipment(db, shipment_id)
    container = _get_container(db, shipment_id, container_id)
    values = validate_patch(ContainerIn, snapshot(container, CONTAINER_INPUT_FIELDS), payload)
    if "container_no" in payload:
        if _events(db, container.id):
            raise AppError("CONTAINER_HAS_EVENTS", "Container đã có mốc, không đổi số container được", 409)
        values["container_no"] = _valid_number(db, shipment_id, values["container_no"], except_id=container.id)
    before = snapshot(container, CONTAINER_FIELDS)
    for key in payload.keys() & values.keys():
        setattr(container, key, values[key])
    db.flush()
    record_audit(db, actor.id, "UPDATE", "container", container.id, before=before,
                 after=snapshot(container, CONTAINER_FIELDS))
    return container


def delete_container(db: Session, shipment_id: int, container_id: int, actor: User) -> None:
    get_open_shipment(db, shipment_id)
    container = _get_container(db, shipment_id, container_id)
    if _events(db, container.id):
        raise AppError("CONTAINER_HAS_EVENTS", "Container đã có mốc, không xoá được", 409)
    before = snapshot(container, CONTAINER_FIELDS)
    db.delete(container)
    db.flush()
    record_audit(db, actor.id, "DELETE", "container", container_id, before=before)


def _assert_not_future(occurred_at: datetime) -> None:
    if occurred_at > utcnow():
        raise AppError("FUTURE_OCCURRED_AT", "Thời điểm xảy ra không được ở tương lai", 400)


def _milestone_order_error() -> AppError:
    return AppError("INVALID_MILESTONE_ORDER", "Mốc container phải theo thứ tự DISCHARGED, GATE_OUT_FULL, "
                    "EMPTY_RETURNED và giờ không được lùi", 409)


def _load_locked(db: Session, container_id: int) -> tuple[Container, Shipment, list[EffectiveEvent]]:
    container = db.get(Container, container_id)
    if container is None:
        raise AppError("NOT_FOUND", "Không tìm thấy container", 404)
    shipment = lock_shipment(db, container.shipment_id)
    assert_open(shipment)
    return container, shipment, effective_events(_events(db, container_id))


def add_container_event(db: Session, container_id: int, kind: str, occurred_at: datetime | None,
                        actor: User | None) -> ContainerEvent:
    """Ghi mốc kế tiếp của container. Khoá lô trước; `actor` None = hệ thống. Không commit."""
    container, shipment, effective = _load_locked(db, container_id)
    occurred_at = occurred_at or utcnow()
    _assert_not_future(occurred_at)
    if kind == "DISCHARGED" and shipment.status not in DISCHARGE_ALLOWED:
        raise AppError("INVALID_SHIPMENT_STATUS", "Chỉ ghi DISCHARGED khi lô đã đến cảng (ARRIVED trở đi)", 409)
    expected = CONTAINER_MILESTONE_ORDER[len(effective)] if len(effective) < len(CONTAINER_MILESTONE_ORDER) else None
    if kind != expected or (effective and occurred_at < effective[-1].occurred_at):
        raise _milestone_order_error()
    event = ContainerEvent(container_id=container_id, kind=kind, occurred_at=occurred_at,
                           actor_id=actor.id if actor else None)
    db.add(event)
    container.status = kind
    db.flush()
    record_audit(db, actor.id if actor else None, "CREATE", "container_event", event.id,
                 after=snapshot(event, CONTAINER_EVENT_FIELDS))
    return event


def retime_container_event(db: Session, container_id: int, target_id: int, occurred_at: datetime, reason: str,
                           actor: User) -> ContainerEvent:
    """Chỉnh giờ một mốc còn hiệu lực bằng event RETIME; thứ tự mốc vẫn phải hợp lệ."""
    container, _, effective = _load_locked(db, container_id)
    target = next((e for e in effective if e.id == target_id), None)
    if target is None:
        raise AppError("INVALID_ADJUSTMENT", "Không chỉnh giờ được sự kiện này", 400)
    _assert_not_future(occurred_at)
    times = {e.kind: e.occurred_at for e in effective}
    times[target.kind] = occurred_at
    ordered = [times[kind] for kind in CONTAINER_MILESTONE_ORDER if kind in times]
    if ordered != sorted(ordered):
        raise _milestone_order_error()
    event = ContainerEvent(container_id=container.id, kind="RETIME", adjusts_event_id=target_id,
                           occurred_at=occurred_at, reason=reason, actor_id=actor.id)
    db.add(event)
    db.flush()
    record_audit(db, actor.id, "RETIME", "container_event", event.id, after=snapshot(event, CONTAINER_EVENT_FIELDS))
    return event


def void_container_event(db: Session, container_id: int, target_id: int, reason: str, actor: User) -> ContainerEvent:
    """Huỷ mốc còn hiệu lực mới nhất bằng event VOID (huỷ mốc giữa chuỗi sẽ làm hỏng thứ tự nên không cho)."""
    container, _, effective = _load_locked(db, container_id)
    if not effective or effective[-1].id != target_id:
        raise AppError("INVALID_ADJUSTMENT", "Chỉ huỷ được mốc container mới nhất", 409)
    event = ContainerEvent(container_id=container.id, kind="VOID", adjusts_event_id=target_id,
                           occurred_at=utcnow(), reason=reason, actor_id=actor.id)
    db.add(event)
    container.status = effective[-2].kind if len(effective) > 1 else None
    db.flush()
    record_audit(db, actor.id, "VOID", "container_event", event.id, after=snapshot(event, CONTAINER_EVENT_FIELDS))
    return event
