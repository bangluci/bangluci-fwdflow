"""Duyệt / từ chối / thử lại một bản trích xuất AI. Hàm không commit; route commit sau khi audit cùng transaction."""

import copy
import re
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.extraction.apply import FieldChoice, apply_extraction, edited_paths
from app.ai.extraction.models import Extraction, ExtractionStatus, assert_extraction_transition
from app.ai.extraction.schemas import SCHEMA_BY_DOC_TYPE
from app.ai.extraction.validate import validate_fields
from app.ai.guard import check_user_rate, require_ai
from app.audit.service import record_audit
from app.auth.models import User
from app.documents.models import Document
from app.envelope import AppError
from app.shipments.service import assert_open, lock_shipment

PATH = re.compile(r"^/(?P<field>[a-z_]+)(?:/(?P<index>\d+))?$")
READ_ONLY_FIELDS = frozenset({"detected_doc_type", "legible", "suspicious_content", "suspicious_note"})
MIN_REASON_LEN = 5


class ApproveIn(BaseModel):
    version: int
    fields: dict[str, FieldChoice] = {}
    manual_check_done: bool = False
    confirm_doc_type_mismatch: bool = False


class RejectIn(BaseModel):
    reason: str


def _lock_extraction(db: Session, extraction_id: int) -> Extraction:
    stmt = select(Extraction).where(Extraction.id == extraction_id).with_for_update()
    extraction = db.scalar(stmt.execution_options(populate_existing=True))
    if extraction is None:
        raise AppError("NOT_FOUND", "Không tìm thấy bản trích xuất", 404)
    return extraction


def _check_path(path: str, data: dict, schema: type[BaseModel]) -> tuple[str, int | None]:
    match = PATH.fullmatch(path)
    name = match["field"] if match else None
    if name not in schema.model_fields or name in READ_ONLY_FIELDS:
        raise AppError("VALIDATION_ERROR", f"Không sửa được trường {path}", 422)
    index = None if match["index"] is None else int(match["index"])
    is_list = isinstance(data.get(name), list)
    if is_list != (index is not None) or (index is not None and index >= len(data[name])):
        raise AppError("VALIDATION_ERROR", f"Đường dẫn không hợp lệ: {path}", 422)
    return name, index


def merge_fields(extraction: Extraction, fields: dict[str, FieldChoice]) -> dict:
    """Giá trị cuối = kết quả AI + các giá trị người duyệt gửi lên, đã kiểm lại bằng schema."""
    schema = SCHEMA_BY_DOC_TYPE[extraction.doc_type]
    data = copy.deepcopy(extraction.result)
    for path, choice in fields.items():
        name, index = _check_path(path, data, schema)
        if index is None:
            data[name] = choice.value
        elif isinstance(choice.value, dict):
            data[name][index] = {**data[name][index], **choice.value}
        else:
            raise AppError("VALIDATION_ERROR", f"Giá trị của {path} phải là một đối tượng", 422)
    try:
        return schema.model_validate(data).model_dump(mode="json")
    except ValidationError as exc:
        paths = sorted({"/" + "/".join(str(part) for part in error["loc"]) for error in exc.errors()})
        raise AppError("FIELD_INVALID", "Giá trị đã sửa không hợp lệ", 422, {"paths": paths}) from exc


def approve_extraction(db: Session, extraction_id: int, body: ApproveIn,
                       actor: User) -> tuple[Extraction, list[dict[str, str]]]:
    peek = db.get(Extraction, extraction_id)
    if peek is None:
        raise AppError("NOT_FOUND", "Không tìm thấy bản trích xuất", 404)
    shipment = lock_shipment(db, peek.shipment_id)  # khoá lô trước, rồi mới khoá bản trích xuất
    extraction = _lock_extraction(db, extraction_id)
    assert_extraction_transition(extraction.status, ExtractionStatus.APPROVED)
    assert_open(shipment)
    if body.version != extraction.version:
        raise AppError("VERSION_CONFLICT", "Bản trích xuất đã thay đổi, tải lại", 409)
    if extraction.suspicious_content and not body.manual_check_done:
        raise AppError("MANUAL_CHECK_REQUIRED", "Chứng từ có dấu hiệu bất thường, cần xác nhận đã tự kiểm tra", 422)
    if extraction.detected_doc_type != extraction.doc_type and not body.confirm_doc_type_mismatch:
        raise AppError("DOC_TYPE_MISMATCH", f"AI nhận diện đây là {extraction.detected_doc_type}, không phải "
                       f"{extraction.doc_type}; cần xác nhận", 422)
    final = merge_fields(extraction, body.fields)
    document = db.get(Document, extraction.document_id)
    blocking = [i for i in validate_fields(extraction.doc_type, final, document.pages) if i.level == "BLOCK"]
    if blocking:
        raise AppError("FIELD_INVALID", "Còn trường không hợp lệ, cần sửa trước khi duyệt", 422,
                       {"paths": [issue.path for issue in blocking]})
    edited = edited_paths(extraction.result, final)
    skipped = apply_extraction(db, extraction, final, body.fields, edited, actor)
    before = {"status": extraction.status}
    extraction.approved_result, extraction.edited_fields = final, sorted(edited)
    extraction.manual_check_done = body.manual_check_done
    extraction.status = ExtractionStatus.APPROVED
    extraction.reviewed_by, extraction.reviewed_at = actor.id, datetime.now(UTC)
    extraction.version += 1
    db.flush()
    record_audit(db, actor.id, "UPDATE", "extraction", extraction.id, before=before,
                 after={"status": extraction.status, "edited_fields": extraction.edited_fields,
                        "manual_check_done": extraction.manual_check_done})
    return extraction, skipped


def reject_extraction(db: Session, extraction_id: int, reason: str, actor: User) -> Extraction:
    reason = reason.strip()
    if len(reason) < MIN_REASON_LEN:
        raise AppError("VALIDATION_ERROR", f"Lý do từ chối phải từ {MIN_REASON_LEN} ký tự", 422)
    extraction = _lock_extraction(db, extraction_id)
    assert_extraction_transition(extraction.status, ExtractionStatus.REJECTED)
    before = {"status": extraction.status}
    extraction.status, extraction.reject_reason = ExtractionStatus.REJECTED, reason
    extraction.reviewed_by, extraction.reviewed_at = actor.id, datetime.now(UTC)
    extraction.version += 1
    db.flush()
    record_audit(db, actor.id, "UPDATE", "extraction", extraction.id, before=before,
                 after={"status": extraction.status, "reject_reason": reason})
    return extraction


def retry_extraction(db: Session, extraction_id: int, actor: User) -> Extraction:
    """FAILED → PENDING: đặt lại lượt gọi; cần AI đang bật và còn hạn mức lượt của user."""
    extraction = _lock_extraction(db, extraction_id)
    assert_extraction_transition(extraction.status, ExtractionStatus.PENDING)
    require_ai(db)
    check_user_rate(actor, "extraction")
    before = {"status": extraction.status}
    extraction.status, extraction.attempts = ExtractionStatus.PENDING, 0
    extraction.next_attempt_at = datetime.now(UTC)
    extraction.error_code = extraction.error_message = extraction.raw_output = None
    extraction.version += 1
    db.flush()
    record_audit(db, actor.id, "UPDATE", "extraction", extraction.id, before=before,
                 after={"status": extraction.status})
    return extraction
