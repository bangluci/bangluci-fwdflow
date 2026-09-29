from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CHAR, BigInteger, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.events import EventMixin
from app.models_base import Base


class TruckingOrder(Base):
    """Một chuyến xe cho một container. `status` / `truck_id` / `driver_id` là cột cache, dựng lại được từ event."""

    __tablename__ = "trucking_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"))
    kind: Mapped[str] = mapped_column(String)
    trucker_id: Mapped[int] = mapped_column(ForeignKey("truckers.id"))
    truck_id: Mapped[int | None] = mapped_column(ForeignKey("trucks.id"))
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"))
    pickup_location: Mapped[str] = mapped_column(String)
    drop_location: Mapped[str] = mapped_column(String)
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="PLANNED")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TruckingOrderEvent(EventMixin, Base):
    __tablename__ = "trucking_order_events"

    order_id: Mapped[int] = mapped_column(ForeignKey("trucking_orders.id"))
    truck_id: Mapped[int | None] = mapped_column(ForeignKey("trucks.id"))
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"))
    photo_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    signer_name: Mapped[str | None] = mapped_column(String)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    device_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_request_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), unique=True)
