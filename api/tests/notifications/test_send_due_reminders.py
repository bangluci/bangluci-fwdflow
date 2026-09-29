from contextlib import nullcontext
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.notifications import reminder
from app.notifications.mailer import MailerError
from app.notifications.models import NotificationLog
from app.worker import main as worker
from tests.notifications.conftest import at

DAY = "2026-11-25"


def _logs(db, day: str | None = None):
    db.expire_all()
    stmt = select(NotificationLog).order_by(NotificationLog.recipient, NotificationLog.day)
    if day:
        stmt = stmt.where(NotificationLog.day == date.fromisoformat(day))
    return db.scalars(stmt).all()


def _run(db, when):
    return reminder.send_due_reminders(db, when)


class FlakySmtp:
    """`send_email` giả: đếm số lần gọi, ném MailerError khi `down`, không thì gửi thật qua Mailpit."""

    def __init__(self, monkeypatch, down=True):
        self.calls, self.down, self.real = 0, down, reminder.send_email
        monkeypatch.setattr(reminder, "send_email", self)

    def __call__(self, to, subject, html):
        self.calls += 1
        if self.down:
            raise MailerError("SMTP down")
        return self.real(to, subject, html)


def test_before_0700_vn_sends_nothing(db, mailpit, reminder_world):
    _run(db, at(DAY, 6, 59))
    assert mailpit.count() == 0 and _logs(db) == []


def test_after_0700_sends_one_email_per_recipient_and_marks_sent(db, mailpit, reminder_world):
    now = at(DAY, 7, 5)
    summary = _run(db, now)
    assert (summary.sent, summary.failed) == (3, 0) and mailpit.count() == 3
    for address in ("staff@example.test", "a@example.test", "b@example.test"):
        (message,) = mailpit.to(address)
        assert [a["Address"] for a in message["To"]] == [address]
    logs = _logs(db)
    assert [(row.status, row.attempts, row.sent_at) for row in logs] == [("SENT", 1, now)] * 3
    a_log = next(row for row in logs if row.recipient == "a@example.test")
    assert [(i["container_no"], i["level"]) for i in a_log.items] == [(reminder_world.container_a.container_no, "RED")]
    assert set(a_log.items[0]) == {"shipment_code", "container_no", "level"}


def test_worker_once_runs_single_pass_and_exits(db, mailpit, reminder_world):
    code = worker.main(["--once", "--now", "2026-11-25T08:00:00+07:00"], session_factory=lambda: nullcontext(db))
    assert code == 0 and mailpit.count() == 3
    assert {row.day for row in _logs(db)} == {date(2026, 11, 25)}


def test_worker_rejects_now_without_timezone():
    with pytest.raises(SystemExit):
        worker.main(["--once", "--now", "2026-11-25T08:00:00"])


def test_restart_same_day_does_not_resend(db, mailpit, reminder_world):
    _run(db, at(DAY, 7, 5))
    restarted = Session(bind=db.get_bind(), join_transaction_mode="create_savepoint", expire_on_commit=False)
    for hour, minute in ((7, 10), (9, 0)):
        _run(restarted, at(DAY, hour, minute))
    assert mailpit.count() == 3 and [row.attempts for row in _logs(db)] == [1, 1, 1]


def test_smtp_failure_marks_failed_and_retries_every_15_min(db, mailpit, reminder_world, monkeypatch):
    smtp = FlakySmtp(monkeypatch)
    _run(db, at(DAY, 7, 5))
    assert [(r.status, r.attempts, r.error) for r in _logs(db)] == [("FAILED", 1, "SMTP down")] * 3
    _run(db, at(DAY, 7, 19))
    assert smtp.calls == 3
    _run(db, at(DAY, 7, 20))
    assert smtp.calls == 6 and [(r.status, r.attempts) for r in _logs(db)] == [("FAILED", 2)] * 3
    smtp.down = False
    _run(db, at(DAY, 7, 35))
    assert [(r.status, r.attempts) for r in _logs(db)] == [("SENT", 3)] * 3 and mailpit.count() == 3


def test_failed_log_is_not_retried_after_midnight(db, mailpit, reminder_world, monkeypatch):
    smtp = FlakySmtp(monkeypatch)
    _run(db, at(DAY, 23, 44))
    _run(db, at(DAY, 23, 59))
    assert [(r.status, r.attempts) for r in _logs(db, DAY)] == [("FAILED", 2)] * 3
    calls = smtp.calls
    _run(db, at("2026-11-26", 0, 14))
    assert smtp.calls == calls
    smtp.down = False
    _run(db, at("2026-11-26", 7, 5))
    assert [(r.status, r.attempts) for r in _logs(db, DAY)] == [("FAILED", 2)] * 3
    assert [(r.status, r.attempts) for r in _logs(db, "2026-11-26")] == [("SENT", 1)] * 3


def test_stuck_pending_alerts_admin_once_and_never_resends(db, mailpit, reminder_world, monkeypatch):
    reminder_world.b.email, reminder_world.staff.email, reminder_world.staff.phone = None, None, "0900000002"
    stuck = NotificationLog(recipient="a@example.test", day=date(2026, 11, 25), status="PENDING", attempts=1,
                            last_attempt_at=at(DAY, 7, 5))
    db.add(stuck)
    db.flush()
    smtp = FlakySmtp(monkeypatch, down=False)

    def alerts():
        return db.scalars(select(AuditLog).where(AuditLog.action == "REMINDER_STUCK")).all()

    _run(db, at(DAY, 7, 14))
    assert alerts() == []
    for hour, minute in ((7, 16), (7, 30), (8, 0)):
        _run(db, at(DAY, hour, minute))
    (alert,) = alerts()
    assert alert.entity == "notification_log" and alert.entity_id == str(stuck.id)
    assert smtp.calls == 0 and _logs(db)[0].status == "PENDING" and mailpit.count() == 0


def test_nothing_to_remind_sends_nothing(db, ft, mailpit, make_user):
    ft.standard_rules()
    staff = make_user("DOCS", email="staff@example.test")
    ft.container(staff_id=staff.id, milestones={"DISCHARGED": "2026-11-24"})  # GREEN
    ft.container(staff_id=staff.id, milestones={"DISCHARGED": "2026-11-17", "GATE_OUT_FULL": "2026-11-18",
                                                 "EMPTY_RETURNED": "2026-11-19"})  # CLOSED
    ft.container(status="IN_TRANSIT", eta="2026-12-15", staff_id=staff.id)  # NOT_STARTED
    for minute in (5, 30):
        _run(db, at(DAY, 7, minute))
    assert mailpit.count() == 0 and _logs(db) == []


def test_two_customers_same_staff_each_email_only_own_containers(db, mailpit, reminder_world):
    _run(db, at(DAY, 7, 5))
    no_a, no_b = reminder_world.container_a.container_no, reminder_world.container_b.container_no
    for address, own, other in (("a@example.test", no_a, no_b), ("b@example.test", no_b, no_a)):
        (message,) = mailpit.to(address)
        assert own in message["HTML"] and other not in message["HTML"]
        assert len(message["To"]) == 1 and message["Cc"] == [] and message["Bcc"] == []
    (staff_message,) = mailpit.to("staff@example.test")
    assert no_a in staff_message["HTML"] and no_b in staff_message["HTML"]


def test_worker_down_at_7_sends_when_back_same_day(db, mailpit, reminder_world):
    assert _logs(db) == []
    _run(db, at(DAY, 15, 30))
    assert mailpit.count() == 3 and {row.last_attempt_at for row in _logs(db)} == {at(DAY, 15, 30)}
    _run(db, at(DAY, 15, 45))
    assert mailpit.count() == 3


def test_now_without_timezone_is_rejected(db):
    with pytest.raises(ValueError, match="múi giờ"):
        reminder.send_due_reminders(db, at(DAY, 8).replace(tzinfo=None))
