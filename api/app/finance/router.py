from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require
from app.auth.models import User
from app.db import get_db
from app.envelope import AppError, ok
from app.finance import service
from app.finance.models import Charge, ChargeCategory, ChargeDirection
from app.shipments.models import Shipment

router = APIRouter(tags=["finance"])
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[User, Depends(require("finance.read"))]
Writer = Annotated[User, Depends(require("finance.write"))]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class ChargeIn(BaseModel):
    direction: ChargeDirection
    category: ChargeCategory
    amount: int
    currency: str
    fx_rate: Decimal | None = None
    charge_date: date | None = None
    note: Note | None = None


class ChargePatch(BaseModel):
    direction: ChargeDirection | None = None
    category: ChargeCategory | None = None
    amount: int | None = None
    currency: str | None = None
    fx_rate: Decimal | None = None
    charge_date: date | None = None
    note: Note | None = None


def _out(charge: Charge) -> dict:
    return {"id": charge.id, "shipment_id": charge.shipment_id, "direction": charge.direction,
            "category": charge.category, "amount": charge.amount, "currency": charge.currency,
            "fx_rate": str(charge.fx_rate.quantize(Decimal("0.0001"))), "amount_vnd": charge.amount_vnd,
            "charge_date": charge.charge_date, "note": charge.note}


def _shipment_or_404(db: Session, shipment_id: int) -> None:
    if db.get(Shipment, shipment_id) is None:
        raise AppError("NOT_FOUND", "Không tìm thấy lô hàng", 404)


def _charge_or_404(db: Session, shipment_id: int, charge_id: int) -> Charge:
    charge = db.get(Charge, charge_id)
    if charge is None or charge.shipment_id != shipment_id:
        raise AppError("NOT_FOUND", "Không tìm thấy khoản thu chi", 404)
    return charge


@router.get("/shipments/{shipment_id}/charges")
def list_charges(shipment_id: int, db: Db, user: Reader) -> dict:
    _shipment_or_404(db, shipment_id)
    items = db.scalars(select(Charge).where(Charge.shipment_id == shipment_id)
                       .order_by(Charge.charge_date, Charge.id)).all()
    profit = service.shipment_profit(db, shipment_id)
    return ok({"items": [_out(c) for c in items],
               "profit": {"revenue_vnd": profit.revenue_vnd, "cost_vnd": profit.cost_vnd,
                          "profit_vnd": profit.profit_vnd}})


@router.post("/shipments/{shipment_id}/charges", status_code=201)
def create_charge(shipment_id: int, body: ChargeIn, db: Db, user: Writer) -> dict:
    _shipment_or_404(db, shipment_id)
    charge = service.create_charge(db, shipment_id, body.model_dump(exclude_unset=True), user)
    db.commit()
    return ok(_out(charge))


@router.patch("/shipments/{shipment_id}/charges/{charge_id}")
def update_charge(shipment_id: int, charge_id: int, body: ChargePatch, db: Db, user: Writer) -> dict:
    charge = _charge_or_404(db, shipment_id, charge_id)
    service.update_charge(db, charge, body.model_dump(exclude_unset=True), user)
    db.commit()
    return ok(_out(charge))


@router.delete("/shipments/{shipment_id}/charges/{charge_id}")
def delete_charge(shipment_id: int, charge_id: int, db: Db, user: Writer) -> dict:
    service.delete_charge(db, _charge_or_404(db, shipment_id, charge_id), user)
    db.commit()
    return ok()
