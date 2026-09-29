from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.service import register_audit_fields
from app.models_base import Base


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class NotificationLog(Base):
    """Một email nhắc hạn cho một người nhận trong một ngày (giờ VN); unique (recipient, day) chống gửi trùng."""

    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    recipient: Mapped[str] = mapped_column(String)
    day: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default=NotificationStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    items: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Không có `recipient`: email là dữ liệu cá nhân, không ghi vào audit
register_audit_fields("notification_log", {"day", "status", "attempts", "error"})
