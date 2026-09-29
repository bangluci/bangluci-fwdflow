from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.service import register_audit_fields
from app.models_base import Base

EMBEDDING_DIM = 1024

register_audit_fields("hs_suggestion", ("shipment_item_id", "chosen_code", "status"))


class HsCode(Base):
    """Mã HS 8 số của Danh mục TT 31/2022. Không có cột thuế suất; `tsv_*` là cột sinh sẵn nên không khai ở đây."""

    __tablename__ = "hs_codes"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    chapter: Mapped[int] = mapped_column(SmallInteger)
    description_vi: Mapped[str] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    nomenclature: Mapped[str] = mapped_column(Text, server_default="TT31/2022")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class HsSuggestionLog(Base):
    __tablename__ = "hs_suggestion_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    shipment_item_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("shipment_items.id"))
    description: Mapped[str] = mapped_column(Text)
    search_degraded: Mapped[bool] = mapped_column(Boolean)
    top1_cosine: Mapped[float | None] = mapped_column(Float)
    candidates: Mapped[list] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    top3: Mapped[list] = mapped_column(JSONB)
    chosen_code: Mapped[str | None] = mapped_column(String(8), ForeignKey("hs_codes.code"))
    chosen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    llm: Mapped[dict | None] = mapped_column(JSONB)
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
