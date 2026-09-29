"""Đọc lô: danh sách (tìm kiếm / lọc / phân trang) và chi tiết đầy đủ."""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.audit.service import snapshot
from app.auth.models import User
from app.auth.scope import scope_shipments
from app.catalog.models import Carrier, Customer, Port
from app.events import effective_events
from app.shipments.audit_fields import DECLARATION_FIELDS, ITEM_FIELDS, SHIPMENT_FIELDS
from app.shipments.iso6346 import normalize_container_no
from app.shipments.models import Container, ContainerEvent, CustomsDeclaration, Shipment, ShipmentEvent, ShipmentItem
from app.shipments.state import MANUAL_TRANSITIONS, ShipmentStatus, missing_for_in_transit

DETAIL_FIELDS = (*SHIPMENT_FIELDS, "created_at", "updated_at")
EVENT_FIELDS = ("id", "kind", "occurred_at", "recorded_at", "actor_id", "adjusts_event_id", "reason")


@dataclass
class ShipmentFilters:
    q: str | None = None
    statuses: list[str] = field(default_factory=list)
    customer_id: int | None = None
    carrier_id: int | None = None
    eta_from: date | None = None
    eta_to: date | None = None
    page: int = 1
    limit: int = 20


def _like(text: str) -> str:
    """Mẫu LIKE khớp một phần, escape `%`, `_` và `\\` trong chuỗi người dùng nhập."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _conditions(f: ShipmentFilters) -> list:
    conds = []
    if f.q and f.q.strip():
        q = f.q.strip()
        container_like = _like(normalize_container_no(q))
        conds.append(or_(
            Shipment.code.ilike(_like(q), escape="\\"),
            Shipment.mbl_no.ilike(_like(q), escape="\\"),
            Shipment.hbl_no.ilike(_like(q), escape="\\"),
            func.unaccent(Customer.name).ilike(func.unaccent(_like(q)), escape="\\"),
            exists().where(Container.shipment_id == Shipment.id,
                           Container.container_no.like(container_like, escape="\\")),
        ))
    if f.statuses:
        conds.append(Shipment.status.in_(f.statuses))
    if f.customer_id:
        conds.append(Shipment.customer_id == f.customer_id)
    if f.carrier_id:
        conds.append(Shipment.carrier_id == f.carrier_id)
    if f.eta_from:
        conds.append(Shipment.eta >= f.eta_from)
    if f.eta_to:
        conds.append(Shipment.eta <= f.eta_to)
    return conds


def list_shipments(db: Session, user: User, f: ShipmentFilters) -> tuple[list[dict], int]:
    conds = _conditions(f)
    count_stmt = select(func.count(Shipment.id)).join(Customer, Customer.id == Shipment.customer_id)
    total = db.scalar(scope_shipments(count_stmt, user).where(*conds))
    container_count = (select(func.count(Container.id)).where(Container.shipment_id == Shipment.id)
                       .correlate(Shipment).scalar_subquery())
    stmt = (
        scope_shipments(
            select(Shipment, Customer.name, Carrier.code, Port.code, User.full_name, container_count)
            .join(Customer, Customer.id == Shipment.customer_id)
            .join(User, User.id == Shipment.staff_id)
            .outerjoin(Carrier, Carrier.id == Shipment.carrier_id)
            .outerjoin(Port, Port.id == Shipment.pod_port_id),
            user,
        )
        .where(*conds)
        .order_by(Shipment.eta.desc().nulls_last(), Shipment.id.desc())
        .limit(f.limit)
        .offset((f.page - 1) * f.limit)
    )
    rows = [
        {"id": s.id, "code": s.code, "load_type": s.load_type, "delivery_mode": s.delivery_mode, "status": s.status,
         "customer_id": s.customer_id, "customer_name": customer, "carrier_id": s.carrier_id, "carrier_code": carrier,
         "mbl_no": s.mbl_no, "hbl_no": s.hbl_no, "pod_code": pod, "eta": s.eta, "do_valid_until": s.do_valid_until,
         "staff_id": s.staff_id, "staff_name": staff, "total_packages": s.total_packages, "version": s.version,
         "container_count": count}
        for s, customer, carrier, pod, staff, count in db.execute(stmt)
    ]
    return rows, total or 0


def _event_out(event) -> dict:
    return {key: getattr(event, key) for key in EVENT_FIELDS}


def container_detail(container: Container, events: list[ContainerEvent]) -> dict:
    milestones = {e.kind: {"event_id": e.id, "occurred_at": e.occurred_at} for e in effective_events(events)}
    return {"id": container.id, **snapshot(container, ("container_no", "container_type", "seal_no",
                                                        "gross_weight_kg", "status")),
            "events": [_event_out(e) for e in events], "milestones": milestones}


def shipment_detail(db: Session, shipment: Shipment) -> dict:
    items = db.scalars(select(ShipmentItem).where(ShipmentItem.shipment_id == shipment.id)
                       .order_by(ShipmentItem.line_no)).all()
    declarations = db.scalars(select(CustomsDeclaration).where(CustomsDeclaration.shipment_id == shipment.id)
                              .order_by(CustomsDeclaration.id)).all()
    containers = db.scalars(select(Container).where(Container.shipment_id == shipment.id).order_by(Container.id)).all()
    events_by_container: dict[int, list[ContainerEvent]] = {c.id: [] for c in containers}
    if containers:
        for event in db.scalars(select(ContainerEvent).where(ContainerEvent.container_id.in_(events_by_container))
                                .order_by(ContainerEvent.id)):
            events_by_container[event.container_id].append(event)
    shipment_events = db.scalars(select(ShipmentEvent).where(ShipmentEvent.shipment_id == shipment.id)
                                 .order_by(ShipmentEvent.id)).all()
    is_created = shipment.status == ShipmentStatus.CREATED
    return {
        "id": shipment.id,
        **snapshot(shipment, DETAIL_FIELDS),
        "customer_name": db.get(Customer, shipment.customer_id).name,
        "items": [{"id": i.id, **snapshot(i, ITEM_FIELDS)} for i in items],
        "declarations": [{"id": d.id, **snapshot(d, DECLARATION_FIELDS)} for d in declarations],
        "containers": [container_detail(c, events_by_container[c.id]) for c in containers],
        "events": [{**_event_out(e), "from_status": e.from_status, "to_status": e.to_status} for e in shipment_events],
        "allowed_transitions": sorted(MANUAL_TRANSITIONS.get(ShipmentStatus(shipment.status), set())),
        "in_transit_missing": missing_for_in_transit(shipment) if is_created else [],
    }
