from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.ai.extraction.models import Extraction
from app.ai.extraction.render import MAX_PAGES, render_page
from app.ai.extraction.targets import current_values
from app.auth.deps import require
from app.auth.models import User
from app.auth.scope import get_scoped_or_404
from app.db import get_db
from app.documents.models import Document
from app.documents.storage import path_for
from app.envelope import AppError, ok
from app.shipments.models import Shipment

router = APIRouter(tags=["extractions"])
Db = Annotated[Session, Depends(get_db)]
Reviewer = Annotated[User, Depends(require("extraction.review"))]

OUT_FIELDS = ("shipment_id", "status", "doc_type", "detected_doc_type", "attempts", "next_attempt_at", "error_code",
              "error_message", "result", "field_issues", "suspicious_content", "suspicious_note",
              "manual_check_done", "version")


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
        "id": extraction.id, **{f: getattr(extraction, f) for f in OUT_FIELDS},
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
