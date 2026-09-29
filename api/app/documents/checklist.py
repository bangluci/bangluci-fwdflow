"""Checklist chứng từ bắt buộc theo loại lô, FTA và trạng thái (bảng `required_doc_rules`)."""

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.documents.models import Document, RequiredDocRule
from app.shipments.models import Shipment
from app.shipments.state import STATUS_RANK, ShipmentStatus


@dataclass(frozen=True)
class ChecklistItem:
    doc_type: str
    required_from_status: str
    present: bool


def checklist_items(db: Session, shipment: Shipment, at_status: str | None = None) -> list[ChecklistItem]:
    """Các loại bắt buộc tới mốc `at_status` (mặc định là trạng thái hiện tại); lô đã huỷ thì không cần gì."""
    if shipment.status == ShipmentStatus.CANCELLED:
        return []
    rank = STATUS_RANK[ShipmentStatus(at_status or shipment.status)]
    rules = db.scalars(
        select(RequiredDocRule)
        .where(RequiredDocRule.load_type == shipment.load_type,
               or_(RequiredDocRule.claims_fta.is_(None), RequiredDocRule.claims_fta == shipment.claims_fta))
        .order_by(RequiredDocRule.id)
    )
    present = set(db.scalars(select(Document.doc_type).where(Document.shipment_id == shipment.id,
                                                              Document.superseded_by_id.is_(None))))
    return [
        ChecklistItem(rule.doc_type, rule.required_from_status, rule.doc_type in present)
        for rule in rules
        if STATUS_RANK[ShipmentStatus(rule.required_from_status)] <= rank
    ]


def missing_documents(db: Session, shipment: Shipment, at_status: str | None = None) -> list[str]:
    return [item.doc_type for item in checklist_items(db, shipment, at_status) if not item.present]
