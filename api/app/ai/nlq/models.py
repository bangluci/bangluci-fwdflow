from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.service import register_audit_fields
from app.models_base import Base

register_audit_fields("nl_query", ("nlq_role", "validation_result", "user_rating"))


class NlQueryLog(Base):
    """Mỗi câu hỏi tới trợ lý một dòng: SQL sinh ra / chạy thật, kết quả kiểm, token đã dùng và điểm người dùng chấm."""

    __tablename__ = "nl_query_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    nlq_role: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    sql_generated: Mapped[str | None] = mapped_column(Text)
    sql_final: Mapped[str | None] = mapped_column(Text)
    validation_result: Mapped[str] = mapped_column(Text)  # OK | REJECTED | NO_PERMISSION
    error_code: Mapped[str | None] = mapped_column(Text)
    repaired: Mapped[bool] = mapped_column(Boolean, default=False)
    row_count: Mapped[int | None] = mapped_column(Integer)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    answer_checked: Mapped[bool | None] = mapped_column(Boolean)
    user_rating: Mapped[bool | None] = mapped_column(Boolean)
    usage: Mapped[dict | None] = mapped_column(JSONB)
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
