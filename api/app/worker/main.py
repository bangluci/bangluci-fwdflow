"""Worker nền (process riêng, cùng codebase, không Redis): nhận job trích xuất bằng SKIP LOCKED, thử lại có backoff."""

import argparse
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
from app.notifications.reminder import send_due_reminders

log = logging.getLogger("fwdflow.worker")

BACKOFF = (timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=5))
STUCK_AFTER = timedelta(minutes=10)
IDLE_SLEEP_SECONDS = 2
REMINDER_POLL_SECONDS = 60


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


def drain_extractions(db: Session, now: datetime) -> None:
    recover_stuck_extractions(db, now)
    while (job := claim_extraction_job(db, now)) is not None:
        process_job(db, job, now)


def _aware_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--now phải có múi giờ, ví dụ 2026-11-25T08:00:00+07:00")
    return parsed


def main(argv: list[str] | None = None, session_factory=SessionLocal) -> int:
    parser = argparse.ArgumentParser(description="Worker nền FwdFlow: trích xuất chứng từ và email nhắc hạn")
    parser.add_argument("--once", action="store_true", help="chạy đúng một vòng rồi thoát")
    parser.add_argument("--now", type=_aware_iso, help="thay giờ hiện tại (chạy tay ngoài giờ, test)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    log.info("Worker khởi động")
    next_reminder = 0.0
    while True:
        now = args.now or datetime.now(UTC)
        try:
            with session_factory() as db:
                drain_extractions(db, now)
                if args.once or time.monotonic() >= next_reminder:
                    send_due_reminders(db, now)
                    next_reminder = time.monotonic() + REMINDER_POLL_SECONDS
        except Exception:
            if args.once:
                raise
            log.exception("Vòng worker lỗi, thử lại ở vòng sau")
        if args.once:
            return 0
        time.sleep(IDLE_SLEEP_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
