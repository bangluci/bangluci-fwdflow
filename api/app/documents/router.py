import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require
from app.auth.models import User
from app.auth.scope import get_scoped_or_404
from app.db import get_db
from app.documents import service
from app.documents.checklist import checklist_items
from app.documents.models import DOC_TYPE_LABELS, DocType, Document
from app.documents.storage import path_for
from app.envelope import AppError, ok
from app.shipments.models import Shipment

log = logging.getLogger("fwdflow.documents")
router = APIRouter(tags=["documents"])
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[User, Depends(require("document.read"))]
Writer = Annotated[User, Depends(require("document.write"))]

OUT_FIELDS = ("shipment_id", "doc_type", "file_sha256", "mime", "size_bytes", "pages", "original_name",
              "superseded_by_id", "visible_to_customer", "uploaded_by", "uploaded_at")


def _out(document: Document) -> dict:
    return {"id": document.id, **{f: getattr(document, f) for f in OUT_FIELDS}}


@router.post("/shipments/{shipment_id}/documents", status_code=201)
def upload_document(shipment_id: int, db: Db, user: Writer, file: Annotated[UploadFile, File()],
                    doc_type: Annotated[DocType, Form()], keep_both: Annotated[bool, Form()] = False) -> dict:
    document, extraction = service.upload_document(db, shipment_id, file, file.filename, doc_type, keep_both, user)
    db.commit()
    return ok({**_out(document), "extraction_id": extraction.id if extraction else None})


@router.get("/shipments/{shipment_id}/documents")
def list_documents(shipment_id: int, db: Db, user: Reader, active_only: bool = False) -> dict:
    get_scoped_or_404(db, Shipment, shipment_id, user)
    stmt = select(Document).where(Document.shipment_id == shipment_id).order_by(Document.uploaded_at.desc(),
                                                                                 Document.id.desc())
    if active_only:
        stmt = stmt.where(Document.superseded_by_id.is_(None))
    return ok([_out(d) for d in db.scalars(stmt)])


@router.get("/documents/{document_id}/file")
def download_document(document_id: int, db: Db, user: Reader) -> FileResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise AppError("NOT_FOUND", "Không tìm thấy chứng từ", 404)
    get_scoped_or_404(db, Shipment, document.shipment_id, user)
    path = path_for(document.file_sha256)
    if not path.is_file():
        log.error("Thiếu file trên đĩa cho chứng từ %s (%s)", document.id, document.file_sha256)
        raise AppError("NOT_FOUND", "Không tìm thấy file chứng từ", 404)
    return FileResponse(path, media_type=document.mime, filename=document.original_name or f"chung-tu-{document.id}",
                        content_disposition_type="inline",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.post("/documents/{document_id}/supersede", status_code=201)
def supersede_document(document_id: int, db: Db, user: Writer, file: Annotated[UploadFile, File()]) -> dict:
    document, extraction = service.supersede_document(db, document_id, file, file.filename, user)
    db.commit()
    return ok({**_out(document), "extraction_id": extraction.id if extraction else None})


@router.get("/shipments/{shipment_id}/doc-checklist")
def doc_checklist(shipment_id: int, db: Db, user: Reader) -> dict:
    shipment = get_scoped_or_404(db, Shipment, shipment_id, user)
    items = [{"doc_type": i.doc_type, "label": DOC_TYPE_LABELS[DocType(i.doc_type)],
              "required_from_status": i.required_from_status, "present": i.present}
             for i in checklist_items(db, shipment)]
    return ok({"status": shipment.status, "items": items,
               "missing": [i["doc_type"] for i in items if not i["present"]]})
