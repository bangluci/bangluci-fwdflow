from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models_base import Base, TimestampMixin

CONTAINER_TYPES = ("20GP", "40GP", "40HC", "45HC", "20RF", "40RF", "40RH")


class FeeType(StrEnum):
    DEM = "DEM"
    DET = "DET"
    COMBINED = "COMBINED"


class OverrideSource(StrEnum):
    ARRIVAL_NOTICE = "ARRIVAL_NOTICE"
    DO = "DO"
    CONTRACT = "CONTRACT"


class FreeTimeRule(Base):
    """Một phiên bản quy tắc: hãng tàu × cảng dỡ × loại container × loại phí, hiệu lực từ `effective_from`."""

    __tablename__ = "free_time_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    carrier_id: Mapped[int] = mapped_column(ForeignKey("carriers.id", ondelete="RESTRICT"))
    port_id: Mapped[int] = mapped_column(ForeignKey("ports.id", ondelete="RESTRICT"))
    container_type: Mapped[str] = mapped_column(String)
    fee_type: Mapped[str] = mapped_column(String)
    free_days: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[date] = mapped_column(Date)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tiers: Mapped[list["FreeTimeTier"]] = relationship(order_by="FreeTimeTier.from_day", viewonly=True)


class FreeTimeTier(Base):
    """Bậc phí theo số ngày tuyệt đối từ ngày 1; `to_day` null là bậc cuối (trở đi)."""

    __tablename__ = "free_time_tiers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("free_time_rules.id", ondelete="CASCADE"))
    from_day: Mapped[int] = mapped_column(Integer)
    to_day: Mapped[int | None] = mapped_column(Integer)
    rate_amount: Mapped[int] = mapped_column(BigInteger)  # đơn giá mỗi ngày, đơn vị nhỏ nhất (USD cent, VND đồng)
    currency: Mapped[str] = mapped_column(String(3))


class ShipmentFreeTimeOverride(TimestampMixin, Base):
    """Số ngày free ghi trên thông báo hàng đến / D/O / hợp đồng, thắng quy tắc chung của lô đó."""

    __tablename__ = "shipment_free_time_overrides"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="RESTRICT"))
    fee_type: Mapped[str] = mapped_column(String)
    free_days: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
