"""Đối chiếu chứng từ theo lô: lấy bản đã duyệt mới nhất của mỗi loại (chưa bị thay thế) và gắn xác nhận "đã biết"."""

from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.extraction.crosscheck import BLOCK, crosscheck
from app.ai.extraction.models import DiscrepancyAck, Extraction, ExtractionStatus
from app.config import get_settings
from app.documents.models import Document
from app.shipments.models import Shipment


def approved_by_type(db: Session, shipment_id: int) -> tuple[dict[str, dict], dict[str, int]]:
    """({loại: approved_result}, {loại: extraction_id}); mỗi loại lấy bản duyệt mới nhất của chứng từ còn hiệu lực."""
    rows = db.execute(
        select(Extraction)
        .join(Document, Document.id == Extraction.document_id)
        .where(Extraction.shipment_id == shipment_id, Extraction.status == ExtractionStatus.APPROVED,
               Document.superseded_by_id.is_(None))
        .order_by(Extraction.reviewed_at.desc(), Extraction.id.desc())
    ).scalars()
    results: dict[str, dict] = {}
    ids: dict[str, int] = {}
    for extraction in rows:
        if extraction.doc_type not in results:
            results[extraction.doc_type] = extraction.approved_result
            ids[extraction.doc_type] = extraction.id
    return results, ids


def shipment_crosscheck(db: Session, shipment: Shipment) -> dict[str, Any]:
    settings = get_settings()
    results, ids = approved_by_type(db, shipment.id)
    outcome = crosscheck(results, shipment.load_type == "FCL", settings.crosscheck_weight_tolerance,
                         settings.consignee_similarity_threshold)
    acks = {a.discrepancy_key: a for a in db.scalars(select(DiscrepancyAck)
                                                     .where(DiscrepancyAck.shipment_id == shipment.id))}
    items = []
    for discrepancy in outcome.discrepancies:
        ack = acks.get(discrepancy.key)
        items.append({**asdict(discrepancy),
                      "ack": None if ack is None else {"reason": ack.reason, "acked_by": ack.acked_by,
                                                       "acked_at": ack.acked_at}})
    return {"status": outcome.status, "discrepancies": items, "documents": ids}


def unresolved_blocking_keys(db: Session, shipment: Shipment) -> list[str]:
    """Sai lệch mức chặn chưa có xác nhận; `INSUFFICIENT` không bao giờ chặn."""
    report = shipment_crosscheck(db, shipment)
    return [d["key"] for d in report["discrepancies"] if d["level"] == BLOCK and d["ack"] is None]
