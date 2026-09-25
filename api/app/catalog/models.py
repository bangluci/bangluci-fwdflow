from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models_base import Base, TimestampMixin


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    tax_code: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    address: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Carrier(TimestampMixin, Base):
    __tablename__ = "carriers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Port(TimestampMixin, Base):
    __tablename__ = "ports"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Warehouse(TimestampMixin, Base):
    __tablename__ = "warehouses"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    address: Mapped[str] = mapped_column(String)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Trucker(TimestampMixin, Base):
    __tablename__ = "truckers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Truck(TimestampMixin, Base):
    __tablename__ = "trucks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trucker_id: Mapped[int] = mapped_column(ForeignKey("truckers.id"))
    plate_no: Mapped[str] = mapped_column(String, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Driver(TimestampMixin, Base):
    __tablename__ = "drivers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trucker_id: Mapped[int] = mapped_column(ForeignKey("truckers.id"))
    full_name: Mapped[str] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
