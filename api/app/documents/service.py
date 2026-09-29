"""Upload chứng từ và thay thế bản cũ. Hàm không commit; route commit sau khi audit cùng transaction."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.extraction.models import Extraction
from app.ai.guard import ai_enabled, check_user_rate
from app.audit.service import record_audit, register_audit_fields, snapshot
from app.auth.models import User
from app.documents.models import DEFAULT_VISIBLE_TYPES, DocType, Document
from app.documents.storage import StoredFile, Upload, save_upload
from app.envelope import AppError
from app.shipments.models import Shipment
from app.shipments.service import get_open_shipment

DOCUMENT_FIELDS = ("shipment_id", "doc_type", "file_sha256", "mime", "size_bytes", "pages", "original_name",
                   "superseded_by_id", "visible_to_customer")
register_audit_fields("document", DOCUMENT_FIELDS)

AI_DOC_TYPES = frozenset({"MBL", "HBL", "INVOICE", "PACKING_LIST"})  # loại được AI #1 đọc
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
MAX_NAME_LEN = 200


def clean_filename(raw: str | None) -> str | None:
    """Chỉ giữ tên file: bỏ đường dẫn (cả / lẫn \\), ký tự điều khiển, cắt còn 200 ký tự."""
    if not raw:
        return None
    name = _CONTROL_CHARS.sub("", re.split(r"[\\/]", raw)[-1]).strip()
    return name[:MAX_NAME_LEN] or None


def _assert_new_file(db: Session, shipment_id: int, stored: StoredFile) -> None:
    exists = db.scalar(select(Document.id).where(Document.shipment_id == shipment_id,
                                                 Document.file_sha256 == stored.sha256))
    if exists is not None:
        raise AppError("DUPLICATE_FILE", "File này đã được tải lên cho lô", 409)


def _new_document(shipment: Shipment, doc_type: str, stored: StoredFile, original_name: str | None,
                  actor: User) -> Document:
    return Document(shipment_id=shipment.id, doc_type=doc_type, file_sha256=stored.sha256, mime=stored.mime,
                    size_bytes=stored.size, pages=stored.pages, original_name=clean_filename(original_name),
                    visible_to_customer=DocType(doc_type) in DEFAULT_VISIBLE_TYPES, uploaded_by=actor.id)


def _queue_extraction(db: Session, document: Document, actor: User) -> Extraction | None:
    """Chứng từ đọc được bằng AI thì xếp hàng trích xuất trong cùng transaction (worker sẽ nhận khi AI bật)."""
    if document.doc_type not in AI_DOC_TYPES:
        return None
    extraction = Extraction(document_id=document.id, shipment_id=document.shipment_id, doc_type=document.doc_type)
    db.add(extraction)
    db.flush()
    record_audit(db, actor.id, "CREATE", "extraction", extraction.id,
                 after={"status": extraction.status, "doc_type": extraction.doc_type})
    return extraction


def _check_ai_quota(db: Session, doc_type: str, actor: User) -> None:
    """AI đang bật thì tính một lượt của user; AI tắt vẫn cho lưu file (job chờ tới khi bật lại)."""
    if doc_type in AI_DOC_TYPES and ai_enabled(db, record=True).enabled:
        check_user_rate(actor, "extraction")


def upload_document(db: Session, shipment_id: int, upload: Upload, original_name: str | None, doc_type: str,
                    keep_both: bool, actor: User) -> tuple[Document, Extraction | None]:
    shipment = get_open_shipment(db, shipment_id)
    _check_ai_quota(db, doc_type, actor)
    stored = save_upload(upload)
    _assert_new_file(db, shipment_id, stored)
    same_type = db.scalar(select(Document.id).where(Document.shipment_id == shipment_id,
                                                    Document.doc_type == doc_type,
                                                    Document.superseded_by_id.is_(None)))
    if same_type is not None and not keep_both:
        raise AppError("SAME_TYPE_EXISTS", "Lô đã có chứng từ loại này", 409)
    document = _new_document(shipment, doc_type, stored, original_name, actor)
    db.add(document)
    db.flush()
    record_audit(db, actor.id, "CREATE", "document", document.id, after=snapshot(document, DOCUMENT_FIELDS))
    return document, _queue_extraction(db, document, actor)


def supersede_document(db: Session, document_id: int, upload: Upload, original_name: str | None,
                       actor: User) -> tuple[Document, Extraction | None]:
    old = db.get(Document, document_id)
    if old is None:
        raise AppError("NOT_FOUND", "Không tìm thấy chứng từ", 404)
    shipment = get_open_shipment(db, old.shipment_id)
    if old.superseded_by_id is not None:
        raise AppError("ALREADY_SUPERSEDED", "Chứng từ này đã được thay thế bằng bản khác", 409)
    _check_ai_quota(db, old.doc_type, actor)
    stored = save_upload(upload)
    _assert_new_file(db, shipment.id, stored)
    new = _new_document(shipment, old.doc_type, stored, original_name, actor)
    db.add(new)
    db.flush()
    before = snapshot(old, DOCUMENT_FIELDS)
    old.superseded_by_id = new.id
    db.flush()
    record_audit(db, actor.id, "CREATE", "document", new.id, after=snapshot(new, DOCUMENT_FIELDS))
    record_audit(db, actor.id, "UPDATE", "document", old.id, before=before, after=snapshot(old, DOCUMENT_FIELDS))
    return new, _queue_extraction(db, new, actor)
