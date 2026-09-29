from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CHAR, BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.service import register_audit_fields
from app.events import EventMixin
from app.models_base import Base


class LastMileOrder(Base):
    """Một đơn giao nội địa của lô VIA_WAREHOUSE; `status` là cột cache, dựng lại được từ event."""

    __tablename__ = "last_mile_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    tracking_code: Mapped[str] = mapped_column(CHAR(10), unique=True)
    recipient_name: Mapped[str] = mapped_column(String)
    recipient_phone: Mapped[str] = mapped_column(String)
    address: Mapped[str] = mapped_column(String)
    packages: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"))
    planned_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="CREATED")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LastMileEvent(EventMixin, Base):
    __tablename__ = "last_mile_events"

    order_id: Mapped[int] = mapped_column(ForeignKey("last_mile_orders.id"))
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"))
    photo_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    device_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_request_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), unique=True)


ORDER_FIELDS = ("tracking_code", "recipient_name", "recipient_phone", "address", "packages", "driver_id",
                "planned_date", "status")
EVENT_FIELDS = ("order_id", "kind", "driver_id", "reason", "lat", "lng")
register_audit_fields("last_mile_order", ORDER_FIELDS)
register_audit_fields("last_mile_event", EVENT_FIELDS)
