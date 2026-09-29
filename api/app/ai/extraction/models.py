from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.service import register_audit_fields
from app.envelope import AppError
from app.models_base import Base, TimestampMixin


class ExtractionStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


S = ExtractionStatus
EXTRACTION_TRANSITIONS = {
    S.PENDING: {S.PROCESSING, S.CANCELLED},
    S.PROCESSING: {S.REVIEW, S.PENDING, S.FAILED},
    S.REVIEW: {S.APPROVED, S.REJECTED},
    S.FAILED: {S.PENDING},
}
MAX_ATTEMPTS = 4


def assert_extraction_transition(from_status: str, to_status: str) -> None:
    if S(to_status) not in EXTRACTION_TRANSITIONS.get(S(from_status), set()):
        raise AppError("INVALID_TRANSITION", f"Không chuyển trích xuất từ {from_status} sang {to_status}", 409)


class Extraction(TimestampMixin, Base):
    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), unique=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    doc_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default=ExtractionStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    stop_reason: Mapped[str | None] = mapped_column(String)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_output: Mapped[str | None] = mapped_column(Text)
    field_issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    detected_doc_type: Mapped[str | None] = mapped_column(String)
    suspicious_content: Mapped[bool] = mapped_column(Boolean, default=False)
    suspicious_note: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)
    approved_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    edited_fields: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    manual_check_done: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)


class DiscrepancyAck(Base):
    __tablename__ = "discrepancy_acks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    discrepancy_key: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(Text)
    acked_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    acked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


register_audit_fields("extraction", ("status", "doc_type", "edited_fields", "manual_check_done", "reject_reason"))
register_audit_fields("discrepancy_ack", ("discrepancy_key", "reason"))
