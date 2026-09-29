"""Khoản thu / chi của lô: quy đổi VND, thêm / sửa / xoá và lợi nhuận của lô. Hàm không tự commit."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from app.audit.service import record_audit, register_audit_fields, snapshot
from app.auth.models import User
from app.envelope import AppError
from app.finance.models import Charge, ChargeDirection, Currency

CHARGE_FIELDS = ("shipment_id", "direction", "category", "amount", "currency", "fx_rate", "amount_vnd",
                 "charge_date", "note")
register_audit_fields("charge", CHARGE_FIELDS)

CENTS_PER_USD = 100


def compute_amount_vnd(amount: int, currency: str, fx_rate: Decimal | None) -> tuple[int, Decimal]:
    """(amount_vnd, fx_rate lưu). VND bỏ qua tỷ giá gửi lên; USD là cent × tỷ giá / 100, làm tròn nửa lên."""
    if amount <= 0:
        raise AppError("INVALID_AMOUNT", "Số tiền phải lớn hơn 0", 400)
    if currency == Currency.VND:
        return amount, Decimal(1)
    if currency != Currency.USD:
        raise AppError("UNSUPPORTED_CURRENCY", "Chỉ hỗ trợ VND và USD", 400)
    if fx_rate is None or fx_rate <= 0:
        raise AppError("FX_RATE_REQUIRED", "Khoản USD cần tỷ giá lớn hơn 0", 400)
    vnd = (Decimal(amount) * fx_rate / CENTS_PER_USD).quantize(Decimal(1), ROUND_HALF_UP)
    return int(vnd), fx_rate


def _today(db: Session) -> date:
    return db.scalar(text("SELECT nlq_today()"))


def create_charge(db: Session, shipment_id: int, data: dict[str, Any], actor: User) -> Charge:
    amount_vnd, fx_rate = compute_amount_vnd(data["amount"], data["currency"], data.get("fx_rate"))
    charge = Charge(shipment_id=shipment_id, direction=data["direction"], category=data["category"],
                    amount=data["amount"], currency=data["currency"], fx_rate=fx_rate, amount_vnd=amount_vnd,
                    charge_date=data.get("charge_date") or _today(db), note=data.get("note"), created_by=actor.id)
    db.add(charge)
    db.flush()
    record_audit(db, actor.id, "CREATE", "charge", charge.id, after=snapshot(charge, CHARGE_FIELDS))
    return charge


def update_charge(db: Session, charge: Charge, data: dict[str, Any], actor: User) -> Charge:
    """Chỉ các trường có trong `data` đổi; `amount_vnd` tính lại mỗi lần lưu."""
    before = snapshot(charge, CHARGE_FIELDS)
    for field in ("direction", "category", "amount", "currency", "charge_date", "note"):
        if field in data:
            setattr(charge, field, data[field])
    fx_rate = data["fx_rate"] if "fx_rate" in data else (charge.fx_rate if charge.currency == Currency.USD else None)
    charge.amount_vnd, charge.fx_rate = compute_amount_vnd(charge.amount, charge.currency, fx_rate)
    db.flush()
    record_audit(db, actor.id, "UPDATE", "charge", charge.id, before=before, after=snapshot(charge, CHARGE_FIELDS))
    return charge


def delete_charge(db: Session, charge: Charge, actor: User) -> None:
    before = snapshot(charge, CHARGE_FIELDS)
    db.delete(charge)
    db.flush()
    record_audit(db, actor.id, "DELETE", "charge", charge.id, before=before)


@dataclass(frozen=True)
class ShipmentProfit:
    revenue_vnd: int
    cost_vnd: int

    @property
    def profit_vnd(self) -> int:
        return self.revenue_vnd - self.cost_vnd


def shipment_profit(db: Session, shipment_id: int) -> ShipmentProfit:
    """Lợi nhuận tính lúc đọc, không lưu: tổng `amount_vnd` doanh thu trừ chi phí của lô."""
    def total(direction: ChargeDirection):
        return func.coalesce(func.sum(case((Charge.direction == direction, Charge.amount_vnd), else_=0)), 0)

    revenue, cost = db.execute(select(total(ChargeDirection.REVENUE), total(ChargeDirection.COST)).where(
        Charge.shipment_id == shipment_id)).one()
    return ShipmentProfit(int(revenue), int(cost))
