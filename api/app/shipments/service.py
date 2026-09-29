"""Vòng đời lô: tạo, sửa (khoá lạc quan theo version), chuyển trạng thái tay, huỷ.

Các hàm không commit; route commit sau khi ghi audit cùng transaction.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.extraction.discrepancies import unresolved_blocking_keys
from app.ai.extraction.models import Extraction, ExtractionStatus, assert_extraction_transition
from app.audit.service import record_audit, snapshot
from app.auth.models import User
from app.catalog.models import Carrier, Customer, Port, Warehouse
from app.documents.checklist import missing_documents
from app.documents.models import DOC_TYPE_LABELS, DocType
from app.envelope import AppError
from app.events import effective_events
from app.shipments.audit_fields import SHIPMENT_FIELDS
from app.shipments.models import Container, ContainerEvent, CustomsDeclaration, Shipment, ShipmentEvent
from app.shipments.schemas import ShipmentCreate, ShipmentUpdate
from app.shipments.state import (
    IN_TRANSIT_FIELD_LABELS,
    STATUS_LABEL_VI,
    ShipmentStatus,
    assert_manual_transition,
    missing_for_in_transit,
)

REFERENCES = {
    "customer_id": (Customer, "Khách hàng"),
    "carrier_id": (Carrier, "Hãng tàu"),
    "pol_port_id": (Port, "Cảng xếp"),
    "pod_port_id": (Port, "Cảng dỡ"),
    "dest_warehouse_id": (Warehouse, "Kho đích"),
}
NOT_NULL_FIELDS = frozenset({"customer_id", "staff_id", "claims_fta"})


def utcnow() -> datetime:
    return datetime.now(UTC)


def lock_shipment(db: Session, shipment_id: int) -> Shipment:
    """`SELECT ... FOR UPDATE`: mọi thay đổi trạng thái container / lệnh / đơn phải mở đầu bằng hàm này."""
    stmt = select(Shipment).where(Shipment.id == shipment_id).with_for_update()
    shipment = db.scalar(stmt.execution_options(populate_existing=True))
    if shipment is None:
        raise AppError("NOT_FOUND", "Không tìm thấy lô hàng", 404)
    return shipment


def assert_open(shipment: Shipment) -> None:
    if shipment.status == ShipmentStatus.CANCELLED:
        raise AppError("SHIPMENT_CLOSED", "Lô đã huỷ, không sửa được", 409)


def get_open_shipment(db: Session, shipment_id: int) -> Shipment:
    """Lô tồn tại và chưa huỷ (dùng cho các thao tác ghi không đổi trạng thái)."""
    shipment = db.get(Shipment, shipment_id)
    if shipment is None:
        raise AppError("NOT_FOUND", "Không tìm thấy lô hàng", 404)
    assert_open(shipment)
    return shipment


def _check_references(db: Session, values: dict) -> None:
    for field, (model, label) in REFERENCES.items():
        ref_id = values.get(field)
        if ref_id is None:
            continue
        ref = db.get(model, ref_id)
        if ref is None or not ref.active:
            raise AppError("INACTIVE_REFERENCE", f"{label} không tồn tại hoặc đã ngừng dùng", 400)


def _check_staff(db: Session, staff_id: int) -> None:
    staff = db.get(User, staff_id)
    if staff is None or not staff.is_active or not staff.is_internal:
        raise AppError("INVALID_STAFF", "Nhân viên phụ trách phải là người dùng nội bộ đang hoạt động", 400)


def record_transition(db: Session, shipment: Shipment, to_status: str, actor_id: int | None,
                      from_status: str | None = None, reason: str | None = None) -> ShipmentEvent:
    """Ghi event TRANSITION và cập nhật cột cache `status` (actor null = hệ thống)."""
    event = ShipmentEvent(shipment_id=shipment.id, kind="TRANSITION", from_status=from_status, to_status=to_status,
                          occurred_at=utcnow(), actor_id=actor_id, reason=reason)
    db.add(event)
    shipment.status = to_status
    db.flush()
    return event


def create_shipment(db: Session, data: ShipmentCreate, actor: User) -> Shipment:
    values = data.model_dump(exclude={"staff_id"})
    staff_id = data.staff_id or actor.id
    _check_references(db, values)
    _check_staff(db, staff_id)
    shipment = Shipment(**values, staff_id=staff_id)
    db.add(shipment)
    db.flush()
    record_transition(db, shipment, ShipmentStatus.CREATED, actor.id)
    record_audit(db, actor.id, "CREATE", "shipment", shipment.id, after=snapshot(shipment, SHIPMENT_FIELDS))
    return shipment


def update_shipment(db: Session, shipment_id: int, data: ShipmentUpdate, actor: User) -> Shipment:
    shipment = lock_shipment(db, shipment_id)
    assert_open(shipment)
    if shipment.version != data.version:
        raise AppError("VERSION_CONFLICT", "Dữ liệu đã thay đổi, tải lại", 409)
    changes = {key: getattr(data, key) for key in data.model_fields_set if key != "version"}
    for key in NOT_NULL_FIELDS & changes.keys():
        if changes[key] is None:
            raise AppError("VALIDATION_ERROR", f"Trường {key} không được để trống", 422)
    etd, eta = changes.get("etd", shipment.etd), changes.get("eta", shipment.eta)
    if etd and eta and etd > eta:
        raise AppError("VALIDATION_ERROR", "ETD không được sau ETA", 422)
    if not changes:
        return shipment
    _check_references(db, changes)
    if changes.get("staff_id"):
        _check_staff(db, changes["staff_id"])
    before = snapshot(shipment, SHIPMENT_FIELDS)
    for key, value in changes.items():
        setattr(shipment, key, value)
    shipment.version += 1
    db.flush()
    record_audit(db, actor.id, "UPDATE", "shipment", shipment.id, before=before,
                 after=snapshot(shipment, SHIPMENT_FIELDS))
    return shipment


def _declarations_block_clearance(db: Session, shipment: Shipment) -> bool:
    declarations = db.scalars(select(CustomsDeclaration).where(CustomsDeclaration.shipment_id == shipment.id)).all()
    return not declarations or any(d.cleared_at is None for d in declarations)


def _guard_transition(db: Session, shipment: Shipment, to_status: str) -> None:
    if to_status == ShipmentStatus.IN_TRANSIT:
        missing = missing_for_in_transit(shipment)
        if missing:
            labels = ", ".join(IN_TRANSIT_FIELD_LABELS[key] for key in missing)
            raise AppError("MISSING_FIELDS", f"Còn thiếu: {labels}", 409)
    if to_status == ShipmentStatus.CUSTOMS_CLEARING:
        keys = unresolved_blocking_keys(db, shipment)
        if keys:
            raise AppError("UNRESOLVED_DISCREPANCY", "Còn sai lệch chứng từ chưa xử lý: " + ", ".join(keys), 409,
                           {"keys": keys})
    if to_status == ShipmentStatus.CLEARED:
        if _declarations_block_clearance(db, shipment):
            raise AppError("DECLARATION_NOT_CLEARED",
                           "Cần ít nhất 1 tờ khai và mọi tờ khai đã có ngày thông quan", 409)
        missing = missing_documents(db, shipment, at_status=ShipmentStatus.CLEARED)
        if missing:
            labels = ", ".join(DOC_TYPE_LABELS[DocType(doc_type)] for doc_type in missing)
            raise AppError("MISSING_DOCUMENTS", f"Thiếu chứng từ: {labels}", 409)


def transition_shipment(db: Session, shipment_id: int, to_status: str, actor: User) -> Shipment:
    shipment = lock_shipment(db, shipment_id)
    assert_manual_transition(shipment.status, to_status)
    _guard_transition(db, shipment, to_status)
    from_status = shipment.status
    record_transition(db, shipment, to_status, actor.id, from_status=from_status)
    record_audit(db, actor.id, "TRANSITION", "shipment", shipment.id, before={"status": from_status},
                 after={"status": to_status})
    return shipment


def _has_effective_gate_out(db: Session, shipment: Shipment) -> bool:
    container_ids = db.scalars(select(Container.id).where(Container.shipment_id == shipment.id)).all()
    for container_id in container_ids:
        events = db.scalars(select(ContainerEvent).where(ContainerEvent.container_id == container_id)).all()
        if any(e.kind == "GATE_OUT_FULL" for e in effective_events(events)):
            return True
    return False


def _cancel_pending_extractions(db: Session, shipment: Shipment) -> None:
    pending = db.scalars(select(Extraction).where(Extraction.shipment_id == shipment.id,
                                                  Extraction.status == ExtractionStatus.PENDING))
    for extraction in pending:
        assert_extraction_transition(extraction.status, ExtractionStatus.CANCELLED)
        extraction.status = ExtractionStatus.CANCELLED


def cancel_shipment(db: Session, shipment_id: int, reason: str, actor: User) -> Shipment:
    shipment = lock_shipment(db, shipment_id)
    if shipment.status in (ShipmentStatus.COMPLETED, ShipmentStatus.CANCELLED):
        label = STATUS_LABEL_VI[ShipmentStatus(shipment.status)]
        raise AppError("INVALID_TRANSITION", f"Lô đang ở trạng thái {label}, không huỷ được", 409)
    if _has_effective_gate_out(db, shipment):
        raise AppError("CANCEL_AFTER_GATE_OUT", "Container đã ra khỏi cảng, không huỷ được lô", 409)
    from_status = shipment.status
    _cancel_pending_extractions(db, shipment)
    record_transition(db, shipment, ShipmentStatus.CANCELLED, actor.id, from_status=from_status, reason=reason)
    record_audit(db, actor.id, "CANCEL", "shipment", shipment.id, before={"status": from_status},
                 after={"status": ShipmentStatus.CANCELLED})
    return shipment
