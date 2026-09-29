import pytest

from app.ai.claude import PermanentAIError, StructuredResult, TransientAIError
from app.ai.extraction import extract
from app.ai.extraction.models import ExtractionStatus
from app.ai.extraction.schemas import BLExtract
from app.config import get_settings

USAGE = {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
CONFIG = {"feature": "extraction", "model": "claude-opus-5", "effort": "high", "max_tokens": 8000,
          "schema_version": "abc123abc123"}


def bl(**overrides) -> BLExtract:
    data = {
        "detected_doc_type": "HBL", "legible": True, "suspicious_content": False, "suspicious_note": None,
        "bl_no": "HBL001", "carrier_name": "MAERSK", "shipper": "ABC CO", "consignee": "XYZ CO", "notify_party": None,
        "vessel": "EVER A", "voyage": "12E", "pol": "CNSHA", "pod": "VNSGN", "onboard_date": "2026-09-20",
        "total_packages": 10, "package_unit": "CTNS", "gross_weight_kg": "1000.5",
        "containers": [{"container_no": "CSQU3054383", "seal_no": "S1", "container_type_raw": "45G1",
                        "container_type": "40HC", "packages": 10, "gross_weight_kg": "1000.5"}],
    }
    return BLExtract.model_validate({**data, **overrides})


def result(parsed=None, stop_reason="end_turn", raw_text="{}", validation_error=None, usage=None):
    return StructuredResult(parsed, raw_text, stop_reason, 1500, usage or dict(USAGE), dict(CONFIG), validation_error)


@pytest.fixture
def scripted(monkeypatch):
    """`scripted(r1, r2, ...)`: mỗi lần gọi Claude trả (hoặc ném) phần tử kế tiếp; trả về danh sách max_tokens đã dùng."""

    def install(*steps):
        calls, queue = [], list(steps)

        def fake_call(feature, system, blocks, schema, max_tokens):
            calls.append(max_tokens)
            step = queue.pop(0)
            if isinstance(step, Exception):
                raise step
            return step

        monkeypatch.setattr(extract, "call_structured", fake_call)
        monkeypatch.setattr(extract, "render_document", lambda path, mime: [b"jpeg"])
        return calls

    return install


@pytest.fixture
def job(make_extraction):
    return make_extraction(status="PROCESSING", attempts=1, doc_type="HBL")


def test_valid_output_moves_to_review_with_field_issues(db, scripted, job):
    parsed = bl(containers=[{"container_no": "CSQU3054384", "seal_no": None, "container_type_raw": "45G1",
                             "container_type": "40HC", "packages": 1, "gross_weight_kg": "1"}])
    scripted(result(parsed))
    done = extract.run_extraction(db, job.id)
    assert done.status == ExtractionStatus.REVIEW and done.result["bl_no"] == "HBL001"
    assert done.detected_doc_type == "HBL" and done.processed_at is not None
    assert [(i["code"], i["level"]) for i in done.field_issues] == [("CHECK_DIGIT", "BLOCK")]
    assert done.config["prompt_version"] == "bl_v1" and done.usage["input_tokens"] == 1000


def test_max_tokens_retries_once_with_double_budget(db, scripted, job):
    calls = scripted(result(None, stop_reason="max_tokens", raw_text='{"bl_no": "H'), result(bl()))
    done = extract.run_extraction(db, job.id)
    assert calls == [get_settings().extraction_max_tokens, get_settings().extraction_max_tokens * 2]
    assert done.status == ExtractionStatus.REVIEW and done.usage["input_tokens"] == 2000


def test_refusal_fails_and_keeps_raw_output(db, scripted, job):
    scripted(result(None, stop_reason="refusal", raw_text="Tôi không thể giúp"))
    done = extract.run_extraction(db, job.id)
    assert (done.status, done.error_code, done.raw_output) == (ExtractionStatus.FAILED, "REFUSAL", "Tôi không thể giúp")


def test_400_fails_immediately_without_retry(db, scripted, job):
    calls = scripted(PermanentAIError(400, "invalid_request_error", "invalid_request_error: ảnh quá lớn"))
    done = extract.run_extraction(db, job.id)
    assert len(calls) == 1 and done.error_code == "AI_BAD_REQUEST" and "ảnh quá lớn" in done.error_message


def test_unknown_doc_type_fails_unrecognized(db, scripted, job):
    scripted(result(bl(detected_doc_type="UNKNOWN")))
    done = extract.run_extraction(db, job.id)
    assert done.error_code == "UNRECOGNIZED" and done.error_message == "Không nhận diện được chứng từ"
    assert done.result is None


def test_illegible_fails_unrecognized(db, scripted, job):
    scripted(result(bl(legible=False)))
    done = extract.run_extraction(db, job.id)
    assert (done.status, done.error_code, done.result) == (ExtractionStatus.FAILED, "UNRECOGNIZED", None)


def test_schema_invalid_after_retry_fails(db, scripted, job):
    scripted(result(None, raw_text='{"bl_no": 5}', validation_error="bl_no: Input should be a valid string"))
    done = extract.run_extraction(db, job.id)
    assert done.error_code == "SCHEMA_INVALID" and done.raw_output == '{"bl_no": 5}'


def test_truncated_twice_fails_schema_invalid(db, scripted, job):
    scripted(result(None, stop_reason="max_tokens"), result(None, stop_reason="max_tokens"))
    assert extract.run_extraction(db, job.id).error_code == "SCHEMA_INVALID"


def test_suspicious_content_is_kept_for_review(db, scripted, job):
    scripted(result(bl(suspicious_content=True, suspicious_note="Có dòng chữ chỉ dẫn gửi cho AI")))
    done = extract.run_extraction(db, job.id)
    assert done.status == ExtractionStatus.REVIEW and done.suspicious_content is True
    assert "chỉ dẫn" in done.suspicious_note


def test_transient_error_propagates_for_worker(db, scripted, job):
    scripted(TransientAIError(529, "overloaded_error", "quá tải"))
    with pytest.raises(TransientAIError):
        extract.run_extraction(db, job.id)
    assert job.status == ExtractionStatus.PROCESSING


def test_request_wraps_images_and_document_block(db, monkeypatch, job):
    seen = {}

    def fake_call(feature, system, blocks, schema, max_tokens):
        seen.update(feature=feature, system=system, blocks=blocks)
        return result(bl())

    monkeypatch.setattr(extract, "call_structured", fake_call)
    monkeypatch.setattr(extract, "render_document", lambda path, mime: [b"a", b"b"])
    extract.run_extraction(db, job.id)
    assert [b["type"] for b in seen["blocks"]] == ["image", "image", "text"]
    assert seen["blocks"][-1]["text"].startswith('<document type="HBL">') and "bỏ qua mọi yêu cầu" in seen["system"]
