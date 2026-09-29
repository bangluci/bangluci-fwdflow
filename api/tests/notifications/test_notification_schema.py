from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

DAY = date(2026, 11, 25)


def _insert(db, recipient="a@example.test", day=DAY, status="PENDING"):
    db.execute(text("INSERT INTO notification_logs (recipient, day, status) VALUES (:r, :d, :s)"),
               {"r": recipient, "d": day, "s": status})
    db.flush()


def test_recipient_day_unique(db):
    _insert(db)
    _insert(db, day=date(2026, 11, 26))  # khác ngày thì được
    with pytest.raises(IntegrityError, match="uq_notification_logs_recipient_day"):
        with db.begin_nested():
            _insert(db)


def test_status_checked(db):
    with pytest.raises(IntegrityError, match="notification_logs_status_check"):
        with db.begin_nested():
            _insert(db, status="QUEUED")


def test_recipient_must_be_lowercase(db):
    with pytest.raises(IntegrityError, match="notification_logs_recipient_check"):
        with db.begin_nested():
            _insert(db, recipient="A@Example.test")
