from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text

from app.ai.guard import (
    ai_enabled,
    ai_today,
    check_user_rate,
    require_ai,
    tokens_today,
)
from app.audit.models import AuditLog
from app.config import get_settings
from app.envelope import AppError

USAGE = {"input_tokens": 900, "output_tokens": 100, "cache_read_input_tokens": 50, "cache_creation_input_tokens": 50}


def _as_of(db, day: str):
    db.execute(text("SELECT set_config('app.as_of', :day, true)"), {"day": day})


def test_rate_limit_31st_extraction_call_in_hour_is_429(make_user):
    user = make_user("DOCS")
    for _ in range(30):
        check_user_rate(user, "extraction")
    with pytest.raises(AppError) as err:
        check_user_rate(user, "extraction")
    assert err.value.status == 429 and err.value.code == "RATE_LIMITED"


def test_rate_limit_is_per_user(make_user):
    first, second = make_user("DOCS"), make_user("DOCS")
    for _ in range(30):
        check_user_rate(first, "extraction")
    check_user_rate(second, "extraction")


def test_ai_disabled_by_config_raises_ai_disabled(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_external_enabled", False)
    status = ai_enabled(db)
    assert (status.enabled, status.reason) == (False, "DISABLED_BY_CONFIG")
    with pytest.raises(AppError) as err:
        require_ai(db)
    assert err.value.code == "AI_DISABLED" and err.value.status == 503


def test_ai_enabled_when_within_budget(db):
    status = ai_enabled(db)
    assert (status.enabled, status.reason) == (True, None)


def test_ai_today_uses_as_of_guc(db):
    _as_of(db, "2026-10-04")
    assert str(ai_today(db)) == "2026-10-04"


def test_budget_exceeded_disables_ai(db, make_extraction, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_daily_token_budget", 1000)
    make_extraction(status="REVIEW", usage=USAGE, processed_at=datetime.now(UTC))
    assert tokens_today(db) == 1100
    status = ai_enabled(db)
    assert (status.enabled, status.reason) == (False, "DAILY_BUDGET_EXCEEDED")


def test_budget_exceeded_writes_one_audit_row_per_day(db, make_extraction, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_daily_token_budget", 1000)
    make_extraction(status="REVIEW", usage=USAGE, processed_at=datetime.now(UTC))
    ai_enabled(db, record=True)
    ai_enabled(db, record=True)
    ai_enabled(db)  # record=False không ghi thêm
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "AI_BUDGET_EXCEEDED")) == 1


def test_budget_resets_next_day(db, make_extraction, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_daily_token_budget", 1000)
    make_extraction(status="REVIEW", usage=USAGE, processed_at=datetime(2026, 10, 4, 3, 0, tzinfo=UTC))
    _as_of(db, "2026-10-04")
    assert ai_enabled(db).enabled is False
    _as_of(db, "2026-10-05")
    assert ai_enabled(db).enabled is True


def test_processed_after_midnight_vn_counts_for_next_vn_day(db, make_extraction, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_daily_token_budget", 1000)
    make_extraction(status="REVIEW", usage=USAGE, processed_at=datetime(2026, 10, 4, 18, 0, tzinfo=UTC))  # 01:00 ngày 5 VN
    _as_of(db, "2026-10-04")
    assert tokens_today(db) == 0
    _as_of(db, "2026-10-05")
    assert tokens_today(db) == 1100
