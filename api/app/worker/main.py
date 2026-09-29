"""Worker nền (process riêng, cùng codebase, không Redis): nhận job trích xuất bằng SKIP LOCKED, thử lại có backoff."""

import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.claude import TransientAIError
from app.ai.extraction.extract import fail_extraction, run_extraction
from app.ai.extraction.models import MAX_ATTEMPTS, Extraction, ExtractionStatus, assert_extraction_transition
from app.ai.guard import ai_enabled
from app.db import SessionLocal

log = logging.getLogger("fwdflow.worker")

BACKOFF = (timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=5))
STUCK_AFTER = timedelta(minutes=10)
IDLE_SLEEP_SECONDS = 2


def claim_extraction_job(db: Session, now: datetime) -> Extraction | None:
    """Lấy một job PENDING đã tới hạn; AI đang tắt (cờ hoặc trần token) thì không lấy job nào."""
    if not ai_enabled(db, record=True).enabled:
        db.commit()  # giữ dòng audit "vượt trần" nếu vừa ghi
        return None
    job = db.scalar(
        select(Extraction)
        .where(Extraction.status == ExtractionStatus.PENDING, Extraction.next_attempt_at <= now)
        .order_by(Extraction.next_attempt_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    assert_extraction_transition(job.status, ExtractionStatus.PROCESSING)
    job.status, job.locked_at, job.attempts = ExtractionStatus.PROCESSING, now, job.attempts + 1
    db.commit()
    return job


def _retry_or_fail(job: Extraction, now: datetime, error: TransientAIError) -> None:
    if job.attempts < MAX_ATTEMPTS:
        assert_extraction_transition(job.status, ExtractionStatus.PENDING)
        job.status, job.locked_at = ExtractionStatus.PENDING, None
        job.next_attempt_at = now + BACKOFF[job.attempts - 1]
    else:
        fail_extraction(job, "AI_UNAVAILABLE", error.message)


def process_job(db: Session, job: Extraction, now: datetime) -> None:
    """Chạy một job; lỗi tạm thời được lên lịch lại ngay (không sleep), lỗi lạ thì FAILED chứ không làm chết worker."""
    job_id = job.id
    try:
        run_extraction(db, job_id)
    except TransientAIError as error:
        _retry_or_fail(job, now, error)
    except Exception:
        log.exception("Job trích xuất %s lỗi không lường trước", job_id)
        db.rollback()
        job = db.get(Extraction, job_id)
        fail_extraction(job, "INTERNAL_ERROR", "Lỗi hệ thống khi xử lý chứng từ")
    db.commit()


def recover_stuck_extractions(db: Session, now: datetime) -> int:
    """PROCESSING quá 10 phút (worker chết giữa chừng) quay về PENDING; lượt đã tính lúc claim."""
    stuck = db.scalars(
        select(Extraction)
        .where(Extraction.status == ExtractionStatus.PROCESSING, Extraction.locked_at < now - STUCK_AFTER)
        .with_for_update(skip_locked=True)
    )
    count = 0
    for job in stuck:
        if job.attempts < MAX_ATTEMPTS:
            assert_extraction_transition(job.status, ExtractionStatus.PENDING)
            job.status, job.locked_at, job.next_attempt_at = ExtractionStatus.PENDING, None, now
        else:
            fail_extraction(job, "WORKER_TIMEOUT", "Xử lý quá thời gian, vui lòng thử lại")
        count += 1
    db.commit()
    return count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    log.info("Worker khởi động")
    while True:
        now = datetime.now(UTC)
        with SessionLocal() as db:
            recover_stuck_extractions(db, now)
            job = claim_extraction_job(db, now)
            if job is not None:
                process_job(db, job, now)
                continue
        time.sleep(IDLE_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
