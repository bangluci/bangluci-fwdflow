from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CHAR, BigInteger, Date, FetchedValue, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models_base import Base, TimestampMixin


class ChargeDirection(StrEnum):
    COST = "COST"
    REVENUE = "REVENUE"


class ChargeCategory(StrEnum):
    OCEAN_FREIGHT = "OCEAN_FREIGHT"
    THC = "THC"
    LOCAL_CHARGE = "LOCAL_CHARGE"
    TRUCKING = "TRUCKING"
    DEM = "DEM"
    DET = "DET"
    DND_COMBINED = "DND_COMBINED"
    CUSTOMS = "CUSTOMS"
    LAST_MILE = "LAST_MILE"
    OTHER = "OTHER"


class Currency(StrEnum):
    VND = "VND"
    USD = "USD"


DEMDET_CATEGORIES = (ChargeCategory.DEM, ChargeCategory.DET, ChargeCategory.DND_COMBINED)


class Charge(TimestampMixin, Base):
    """Một khoản thu / chi của lô. Tiền là số nguyên đơn vị nhỏ nhất (VND: đồng, USD: cent); không lưu lợi nhuận."""

    __tablename__ = "charges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    direction: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    amount_vnd: Mapped[int] = mapped_column(BigInteger)
    charge_date: Mapped[date] = mapped_column(Date, server_default=FetchedValue())
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
