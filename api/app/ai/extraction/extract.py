"""Chạy một lượt trích xuất: render trang → gọi Claude → kiểm tra → REVIEW hoặc FAILED (spec mục 4, AI #1)."""

import base64
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ai.claude import PermanentAIError, StructuredResult, call_structured
from app.ai.extraction.models import Extraction, ExtractionStatus, assert_extraction_transition
from app.ai.extraction.render import render_document
from app.ai.extraction.schemas import SCHEMA_BY_DOC_TYPE, load_prompt, prompt_version
from app.ai.extraction.validate import validate_fields
from app.config import get_settings
from app.documents.models import Document
from app.documents.storage import path_for
from app.envelope import AppError

TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
UNRECOGNIZED_MESSAGE = "Không nhận diện được chứng từ"


def _blocks(doc_type: str, pages: list[bytes]) -> list[dict]:
    images = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.standard_b64encode(page).decode()}} for page in pages]
    return [*images, {"type": "text", "text": f'<document type="{doc_type}">Các ảnh trên là chứng từ cần trích xuất'
                                              "</document>"}]


def _accumulate(extraction: Extraction, result: StructuredResult) -> None:
    total = {key: (extraction.usage or {}).get(key, 0) + result.usage.get(key, 0) for key in TOKEN_KEYS}
    extraction.usage = total
    extraction.latency_ms = (extraction.latency_ms or 0) + result.latency_ms
    extraction.stop_reason = result.stop_reason
    extraction.config = {**result.config, "prompt_version": prompt_version(extraction.doc_type)}


def _move(extraction: Extraction, to_status: ExtractionStatus) -> None:
    assert_extraction_transition(extraction.status, to_status)
    extraction.status = to_status


def fail_extraction(extraction: Extraction, code: str, message: str, raw_output: str | None = None) -> None:
    _move(extraction, ExtractionStatus.FAILED)
    extraction.error_code, extraction.error_message = code, message
    extraction.raw_output = raw_output
    extraction.locked_at = None
    extraction.processed_at = datetime.now(UTC)


def _call_with_length_retry(extraction: Extraction, system: str, blocks: list[dict],
                            schema: type) -> StructuredResult:
    """`max_tokens` thì gọi lại đúng một lần với gấp đôi hạn mức; mọi lần gọi cộng dồn vào `usage`."""
    max_tokens = get_settings().extraction_max_tokens
    result = call_structured("extraction", system, blocks, schema, max_tokens)
    _accumulate(extraction, result)
    if result.stop_reason == "max_tokens":
        result = call_structured("extraction", system, blocks, schema, max_tokens * 2)
        _accumulate(extraction, result)
    return result


def _apply_result(extraction: Extraction, result: StructuredResult, document: Document) -> None:
    parsed = result.parsed
    if parsed is None:
        if result.stop_reason == "refusal":
            return fail_extraction(extraction, "REFUSAL", "AI từ chối đọc chứng từ này", result.raw_text)
        reason = result.validation_error or "Kết quả AI bị cắt do quá dài"
        return fail_extraction(extraction, "SCHEMA_INVALID", f"Kết quả AI không đúng cấu trúc: {reason}",
                               result.raw_text)
    if parsed.detected_doc_type == "UNKNOWN" or not parsed.legible:
        return fail_extraction(extraction, "UNRECOGNIZED", UNRECOGNIZED_MESSAGE)
    data = parsed.model_dump(mode="json")
    _move(extraction, ExtractionStatus.REVIEW)
    extraction.result = data
    extraction.field_issues = [issue.as_dict() for issue in validate_fields(extraction.doc_type, data, document.pages)]
    extraction.detected_doc_type = parsed.detected_doc_type
    extraction.suspicious_content = parsed.suspicious_content
    extraction.suspicious_note = parsed.suspicious_note
    extraction.locked_at = None
    extraction.processed_at = datetime.now(UTC)
    return None


def run_extraction(db: Session, extraction_id: int) -> Extraction:
    """`extraction` phải đang PROCESSING (worker đã claim). Lỗi tạm thời (`TransientAIError`) ném lên cho worker."""
    extraction = db.get(Extraction, extraction_id)
    if extraction is None:
        raise AppError("NOT_FOUND", "Không tìm thấy bản trích xuất", 404)
    document = db.get(Document, extraction.document_id)
    pages = render_document(path_for(document.file_sha256), document.mime)
    try:
        result = _call_with_length_retry(extraction, load_prompt(extraction.doc_type),
                                         _blocks(extraction.doc_type, pages), SCHEMA_BY_DOC_TYPE[extraction.doc_type])
    except PermanentAIError as exc:
        fail_extraction(extraction, "AI_BAD_REQUEST", exc.message)
        db.flush()
        return extraction
    _apply_result(extraction, result, document)
    db.flush()
    return extraction
