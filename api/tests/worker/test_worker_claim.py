from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ai.claude import TransientAIError
from app.ai.extraction.models import Extraction, ExtractionStatus
from app.auth.models import User
from app.catalog.models import Customer
from app.config import get_settings
from app.documents.models import Document
from app.shipments.models import Shipment
from app.worker import main as worker

NOW = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)


def _fail_transient(monkeypatch):
    def boom(db, extraction_id):
        raise TransientAIError(529, "overloaded_error", "quá tải")

    monkeypatch.setattr(worker, "run_extraction", boom)


def test_claim_marks_processing_and_counts_attempt(db, make_extraction):
    job = make_extraction()
    claimed = worker.claim_extraction_job(db, NOW)
    assert claimed.id == job.id and claimed.status == ExtractionStatus.PROCESSING
    assert (claimed.attempts, claimed.locked_at) == (1, NOW)
    assert worker.claim_extraction_job(db, NOW) is None


def test_claim_skips_jobs_not_due_yet(db, make_extraction):
    make_extraction(next_attempt_at=NOW + timedelta(seconds=1))
    assert worker.claim_extraction_job(db, NOW) is None


def test_claim_takes_earliest_due_job_first(db, make_extraction):
    later = make_extraction(next_attempt_at=NOW - timedelta(minutes=1))
    earlier = make_extraction(next_attempt_at=NOW - timedelta(minutes=5))
    assert worker.claim_extraction_job(db, NOW).id == earlier.id
    assert worker.claim_extraction_job(db, NOW).id == later.id


def test_transient_error_schedules_30s_then_2m_then_5m(db, make_extraction, monkeypatch):
    _fail_transient(monkeypatch)
    job = make_extraction()
    for attempt, delay in enumerate([timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=5)], start=1):
        claimed = worker.claim_extraction_job(db, NOW)
        worker.process_job(db, claimed, NOW)
        assert (job.status, job.attempts, job.locked_at) == (ExtractionStatus.PENDING, attempt, None)
        assert job.next_attempt_at == NOW + delay
        job.next_attempt_at = NOW  # tới hạn để lần claim kế tiếp lấy được


def test_fourth_transient_failure_marks_failed(db, make_extraction, monkeypatch):
    _fail_transient(monkeypatch)
    job = make_extraction()
    for _ in range(4):
        worker.process_job(db, worker.claim_extraction_job(db, NOW), NOW)
        job.next_attempt_at = NOW
    assert (job.status, job.attempts, job.error_code) == (ExtractionStatus.FAILED, 4, "AI_UNAVAILABLE")
    assert "quá tải" in job.error_message


def test_unexpected_error_marks_failed_instead_of_crashing(db, make_extraction, monkeypatch):
    def broken(db, extraction_id):
        raise RuntimeError("file mất")

    monkeypatch.setattr(worker, "run_extraction", broken)
    job = make_extraction()
    worker.process_job(db, worker.claim_extraction_job(db, NOW), NOW)
    assert (job.status, job.error_code) == (ExtractionStatus.FAILED, "INTERNAL_ERROR")


def test_stuck_processing_over_10_minutes_returns_pending(db, make_extraction):
    job = make_extraction(status="PROCESSING", attempts=1, locked_at=NOW - timedelta(minutes=11))
    fresh = make_extraction(status="PROCESSING", attempts=1, locked_at=NOW - timedelta(minutes=5))
    assert worker.recover_stuck_extractions(db, NOW) == 1
    assert (job.status, job.locked_at) == (ExtractionStatus.PENDING, None) and fresh.status == "PROCESSING"


def test_stuck_job_counts_attempt(db, make_extraction):
    job = make_extraction(status="PROCESSING", attempts=2, locked_at=NOW - timedelta(minutes=30))
    worker.recover_stuck_extractions(db, NOW)
    assert job.attempts == 2 and job.status == ExtractionStatus.PENDING


def test_stuck_job_out_of_attempts_fails_with_timeout(db, make_extraction):
    job = make_extraction(status="PROCESSING", attempts=4, locked_at=NOW - timedelta(minutes=30))
    worker.recover_stuck_extractions(db, NOW)
    assert (job.status, job.error_code) == (ExtractionStatus.FAILED, "WORKER_TIMEOUT")


def test_no_claim_when_ai_disabled(db, make_extraction, monkeypatch):
    job = make_extraction()
    monkeypatch.setattr(get_settings(), "ai_external_enabled", False)
    assert worker.claim_extraction_job(db, NOW) is None and job.status == ExtractionStatus.PENDING
    monkeypatch.setattr(get_settings(), "ai_external_enabled", True)
    assert worker.claim_extraction_job(db, NOW).id == job.id


def test_two_sessions_claim_different_jobs(engine):
    """Hai worker thật (hai kết nối, dữ liệu đã commit): job đang bị khoá thì bên kia bỏ qua, không chờ."""
    with Session(engine) as setup:
        staff = User(email="skip-locked@test.local", full_name="SL", role="DOCS", password_hash="x")
        customer = Customer(name="SL")
        setup.add_all([staff, customer])
        setup.flush()
        shipment = Shipment(load_type="FCL", delivery_mode="VIA_WAREHOUSE", customer_id=customer.id, staff_id=staff.id)
        setup.add(shipment)
        setup.flush()
        ids = []
        for n in range(2):
            document = Document(shipment_id=shipment.id, doc_type="HBL", file_sha256=f"{n}" * 64, mime="application/pdf",
                                size_bytes=1, pages=1, visible_to_customer=True, uploaded_by=staff.id)
            setup.add(document)
            setup.flush()
            extraction = Extraction(document_id=document.id, shipment_id=shipment.id, doc_type="HBL",
                                    next_attempt_at=NOW - timedelta(minutes=n))
            setup.add(extraction)
            setup.flush()
            ids.append(extraction.id)
        setup.commit()
        chain = (staff.id, customer.id, shipment.id)
    holder, claimer = Session(engine), Session(engine)
    try:
        claimer.execute(text("SET lock_timeout = '2s'"))
        first = holder.scalar(select(Extraction).where(Extraction.id.in_(ids)).order_by(Extraction.next_attempt_at)
                              .with_for_update(skip_locked=True).limit(1))  # giữ khoá, chưa commit
        second = worker.claim_extraction_job(claimer, NOW)
        assert second is not None and second.id != first.id and {first.id, second.id} == set(ids)
    finally:
        holder.rollback()
        holder.close()
        claimer.close()
        with Session(engine) as cleanup:
            cleanup.execute(text("DELETE FROM extractions WHERE id = ANY(:ids)"), {"ids": ids})
            cleanup.execute(text("DELETE FROM documents WHERE shipment_id = :s"), {"s": chain[2]})
            cleanup.execute(text("DELETE FROM shipments WHERE id = :s"), {"s": chain[2]})
            cleanup.execute(text("DELETE FROM customers WHERE id = :c"), {"c": chain[1]})
            cleanup.execute(text("DELETE FROM users WHERE id = :u"), {"u": chain[0]})
            cleanup.commit()
