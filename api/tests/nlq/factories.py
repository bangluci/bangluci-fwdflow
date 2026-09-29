from decimal import Decimal

from app.finance.models import Charge
from app.finance.service import compute_amount_vnd


def make_charge(db, shipment, *, currency: str = "VND", amount: int = 1_000_000, fx_rate: str | None = None,
                direction: str = "REVENUE", category: str = "OTHER") -> Charge:
    """Khoản thu / chi dựng thẳng bằng ORM; số tiền theo đơn vị nhỏ nhất (USD là cent)."""
    rate = Decimal(fx_rate) if fx_rate else None
    amount_vnd, stored_rate = compute_amount_vnd(amount, currency, rate)
    charge = Charge(shipment_id=shipment.id, direction=direction, category=category, amount=amount, currency=currency,
                    fx_rate=stored_rate, amount_vnd=amount_vnd)
    db.add(charge)
    db.flush()
    return charge
