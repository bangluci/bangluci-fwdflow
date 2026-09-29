"""Cờ tắt AI, giới hạn lượt theo user và trần token theo ngày cho cả 3 tính năng AI."""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.audit.service import record_audit, register_audit_fields
from app.auth.models import User
from app.config import get_settings
from app.envelope import AppError
from app.ratelimit import FixedWindowLimiter

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
AI_RATE_LIMITS = {"extraction": 30, "hs": 60, "nlq": 30}  # lượt mỗi giờ mỗi user
_limiters = {feature: FixedWindowLimiter(limit, 3600) for feature, limit in AI_RATE_LIMITS.items()}
HS_USAGE = "llm->'usage'"  # cột jsonb của hs_suggestion_logs
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")

register_audit_fields("ai", ("date", "tokens", "budget"))


@dataclass(frozen=True)
class AiStatus:
    enabled: bool
    reason: str | None  # None | DISABLED_BY_CONFIG | DAILY_BUDGET_EXCEEDED


def reset_rate_limits() -> None:
    for limiter in _limiters.values():
        limiter.reset()


def check_user_rate(user: User, feature: str) -> None:
    if not _limiters[feature].hit(str(user.id)):
        raise AppError("RATE_LIMITED", "Bạn đã dùng AI quá số lần cho phép, thử lại sau", 429)


def ai_today(db: Session) -> date:
    """Ngày tham chiếu: GUC `app.as_of` (test / e2e) nếu có, không thì ngày hiện tại giờ Việt Nam."""
    as_of = db.scalar(text("SELECT nullif(current_setting('app.as_of', true), '')"))
    return date.fromisoformat(as_of) if as_of else datetime.now(VN_TZ).date()


def _token_sum(usage: str) -> str:
    return " + ".join(f"coalesce(({usage}->>'{key}')::bigint, 0)" for key in TOKEN_KEYS)


def tokens_today(db: Session) -> int:
    """Token đã dùng hôm nay (đọc chứng từ + gợi ý mã HS + hỏi đáp). # ponytail: token của một extraction tính vào
    ngày gọi cuối cùng; cần chính xác theo từng lần gọi thì thêm bảng ai_call_logs."""
    today = {"today": ai_today(db)}
    extraction = db.scalar(text(
        f"SELECT coalesce(sum({_token_sum('usage')}), 0) FROM extractions WHERE processed_at IS NOT NULL "  # noqa: S608
        "AND (processed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date = :today"), today)
    hs = db.scalar(text(
        f"SELECT coalesce(sum({_token_sum(HS_USAGE)}), 0) FROM hs_suggestion_logs "  # noqa: S608
        "WHERE llm IS NOT NULL AND (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date = :today"), today)
    nlq = db.scalar(text(
        f"SELECT coalesce(sum({_token_sum('usage')}), 0) FROM nl_query_logs "  # noqa: S608
        "WHERE usage IS NOT NULL AND (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date = :today"), today)
    return int(extraction) + int(hs) + int(nlq)


def check_daily_budget(db: Session) -> bool:
    """True nếu hôm nay còn trong trần `AI_DAILY_TOKEN_BUDGET`."""
    return tokens_today(db) < get_settings().ai_daily_token_budget


def _record_budget_exceeded(db: Session) -> None:
    today = ai_today(db).isoformat()
    exists = db.scalar(select(AuditLog.id).where(AuditLog.action == "AI_BUDGET_EXCEEDED", AuditLog.entity == "ai",
                                                 AuditLog.entity_id == today))
    if exists is None:
        record_audit(db, None, "AI_BUDGET_EXCEEDED", "ai", today,
                     after={"date": today, "tokens": tokens_today(db), "budget": get_settings().ai_daily_token_budget})
        db.flush()


def ai_enabled(db: Session, record: bool = False) -> AiStatus:
    """`record=True` (worker, upload) ghi một dòng audit mỗi ngày khi vượt trần; route GET dùng `record=False`."""
    if not get_settings().ai_external_enabled:
        return AiStatus(False, "DISABLED_BY_CONFIG")
    if not check_daily_budget(db):
        if record:
            _record_budget_exceeded(db)
        return AiStatus(False, "DAILY_BUDGET_EXCEEDED")
    return AiStatus(True, None)


def require_ai(db: Session) -> None:
    if not ai_enabled(db, record=True).enabled:
        raise AppError("AI_DISABLED", "Tính năng AI đang tắt, vui lòng nhập tay", 503)
