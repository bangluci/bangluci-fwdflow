from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from app.ai.extraction import review
from app.ai.extraction.discrepancies import shipment_crosscheck
from app.ai.extraction.models import DiscrepancyAck, Extraction
from app.ai.extraction.render import MAX_PAGES, render_page
from app.ai.extraction.review import ApproveIn, RejectIn
from app.ai.extraction.targets import current_values
from app.audit.service import record_audit
from app.auth.deps import require
from app.auth.models import User
from app.auth.scope import get_scoped_or_404
from app.db import get_db
from app.documents.models import Document
from app.documents.storage import path_for
from app.envelope import AppError, ok
from app.shipments.models import Shipment

router = APIRouter(tags=["extractions"])
Internal = Annotated[User, Depends(require("shipment.read"))]
Db = Annotated[Session, Depends(get_db)]
Reviewer = Annotated[User, Depends(require("extraction.review"))]

OUT_FIELDS = ("shipment_id", "status", "doc_type", "detected_doc_type", "attempts", "next_attempt_at", "error_code",
              "error_message", "result", "field_issues", "suspicious_content", "suspicious_note",
              "manual_check_done", "version")


def _summary(extraction: Extraction) -> dict:
    return {"id": extraction.id, **{f: getattr(extraction, f) for f in OUT_FIELDS}}


def load_extraction(db: Session, extraction_id: int, user: User) -> Extraction:
    extraction = db.get(Extraction, extraction_id)
    if extraction is None:
        raise AppError("NOT_FOUND", "Không tìm thấy bản trích xuất", 404)
    get_scoped_or_404(db, Shipment, extraction.shipment_id, user)
    return extraction


@router.get("/extractions/{extraction_id}")
def get_extraction(extraction_id: int, db: Db, user: Reviewer) -> dict:
    extraction = load_extraction(db, extraction_id, user)
    document = db.get(Document, extraction.document_id)
    return ok({
        **_summary(extraction),
        "document": {"id": document.id, "mime": document.mime, "pages": document.pages,
                     "page_count_rendered": min(document.pages, MAX_PAGES), "original_name": document.original_name},
        "current": current_values(db, extraction),
    })


@router.get("/extractions/{extraction_id}/pages/{page}")
def get_page_image(extraction_id: int, page: int, db: Db, user: Reviewer) -> Response:
    """Đúng ảnh AI đã thấy. # ponytail: render lại mỗi request; chậm thì cache file theo sha256."""
    extraction = load_extraction(db, extraction_id, user)
    document = db.get(Document, extraction.document_id)
    image = render_page(path_for(document.file_sha256), document.mime, page)
    if image is None:
        raise AppError("NOT_FOUND", "Không có trang này", 404)
    return Response(image, media_type="image/jpeg",
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/extractions/{extraction_id}/approve")
def approve(extraction_id: int, body: ApproveIn, db: Db, user: Reviewer) -> dict:
    load_extraction(db, extraction_id, user)
    extraction, skipped = review.approve_extraction(db, extraction_id, body, user)
    db.commit()
    return ok({**_summary(extraction), "skipped": skipped})


@router.post("/extractions/{extraction_id}/reject")
def reject(extraction_id: int, body: RejectIn, db: Db, user: Reviewer) -> dict:
    load_extraction(db, extraction_id, user)
    extraction = review.reject_extraction(db, extraction_id, body.reason, user)
    db.commit()
    return ok(_summary(extraction))


@router.post("/extractions/{extraction_id}/retry")
def retry(extraction_id: int, db: Db, user: Reviewer) -> dict:
    load_extraction(db, extraction_id, user)
    extraction = review.retry_extraction(db, extraction_id, user)
    db.commit()
    return ok(_summary(extraction))


class AckIn(BaseModel):
    discrepancy_key: str
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]


@router.get("/shipments/{shipment_id}/crosscheck")
def get_crosscheck(shipment_id: int, db: Db, user: Internal) -> dict:
    shipment = get_scoped_or_404(db, Shipment, shipment_id, user)
    return ok(shipment_crosscheck(db, shipment))


@router.post("/shipments/{shipment_id}/discrepancy-acks", status_code=201)
def ack_discrepancy(shipment_id: int, body: AckIn, db: Db, user: Reviewer) -> dict:
    shipment = get_scoped_or_404(db, Shipment, shipment_id, user)
    report = shipment_crosscheck(db, shipment)
    match = next((d for d in report["discrepancies"] if d["key"] == body.discrepancy_key), None)
    if match is None:
        raise AppError("UNKNOWN_DISCREPANCY", "Không có sai lệch này trong kết quả đối chiếu hiện tại", 422)
    if match["ack"] is not None:
        raise AppError("ALREADY_ACKED", "Sai lệch này đã được xác nhận", 409)
    ack = DiscrepancyAck(shipment_id=shipment.id, discrepancy_key=body.discrepancy_key, reason=body.reason,
                         acked_by=user.id)
    db.add(ack)
    db.flush()
    record_audit(db, user.id, "CREATE", "discrepancy_ack", ack.id,
                 after={"discrepancy_key": ack.discrepancy_key, "reason": ack.reason})
    db.commit()
    return ok({"id": ack.id, "discrepancy_key": ack.discrepancy_key, "reason": ack.reason, "acked_by": ack.acked_by,
               "acked_at": ack.acked_at})
