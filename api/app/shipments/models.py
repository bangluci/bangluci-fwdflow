from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, FetchedValue, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.events import EventMixin
from app.models_base import Base, TimestampMixin


class Shipment(TimestampMixin, Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String, server_default=FetchedValue())  # DB sinh: FF + YY + 5 số
    load_type: Mapped[str] = mapped_column(String)
    delivery_mode: Mapped[str] = mapped_column(String)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    carrier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id"))
    pol_port_id: Mapped[int | None] = mapped_column(ForeignKey("ports.id"))
    pod_port_id: Mapped[int | None] = mapped_column(ForeignKey("ports.id"))
    dest_warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"))
    mbl_no: Mapped[str | None] = mapped_column(String)
    hbl_no: Mapped[str | None] = mapped_column(String)
    vessel: Mapped[str | None] = mapped_column(String)
    voyage: Mapped[str | None] = mapped_column(String)
    etd: Mapped[date | None] = mapped_column(Date)
    eta: Mapped[date | None] = mapped_column(Date)
    claims_fta: Mapped[bool] = mapped_column(Boolean, default=False)
    do_no: Mapped[str | None] = mapped_column(String)
    do_valid_until: Mapped[date | None] = mapped_column(Date)
    total_packages: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="CREATED")


class ShipmentItem(TimestampMixin, Base):
    __tablename__ = "shipment_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit: Mapped[str | None] = mapped_column(String)
    packages: Mapped[int | None] = mapped_column(Integer)
    gross_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    value_amount: Mapped[int | None] = mapped_column(BigInteger)
    value_currency: Mapped[str | None] = mapped_column(String(3))
    hs_code: Mapped[str | None] = mapped_column(String(8))
    hs_source: Mapped[str | None] = mapped_column(String)


class CustomsDeclaration(TimestampMixin, Base):
    __tablename__ = "customs_declarations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    declaration_no: Mapped[str] = mapped_column(String(12))
    type_code: Mapped[str] = mapped_column(String)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lane: Mapped[str | None] = mapped_column(String)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Container(TimestampMixin, Base):
    __tablename__ = "containers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    container_no: Mapped[str] = mapped_column(String(11))
    container_type: Mapped[str] = mapped_column(String)
    seal_no: Mapped[str | None] = mapped_column(String)
    gross_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    status: Mapped[str | None] = mapped_column(String)  # cache mốc hiệu lực cuối, dựng lại được từ event



class ShipmentEvent(EventMixin, Base):
    __tablename__ = "shipment_events"

    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    from_status: Mapped[str | None] = mapped_column(String)
    to_status: Mapped[str | None] = mapped_column(String)


class ContainerEvent(EventMixin, Base):
    __tablename__ = "container_events"

    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"))
