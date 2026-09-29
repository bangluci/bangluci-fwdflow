from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from app.auth.deps import require
from app.auth.models import User
from app.auth.permissions import can
from app.config import get_settings
from app.db import get_db
from app.envelope import ok
from app.finance.models import Charge, ChargeDirection
from app.notifications.reminder import do_expiring_shipments
from app.reports.demdet import GroupBy, demdet_report
from app.shipments.models import Shipment
from app.shipments.state import ShipmentStatus

router = APIRouter(tags=["reports"])
Db = Annotated[Session, Depends(get_db)]
FinanceReader = Annotated[User, Depends(require("finance.read"))]
DashboardReader = Annotated[User, Depends(require("dashboard.read"))]

_LEVEL_COUNTS = """
SELECT count(DISTINCT container_id) FILTER (WHERE container_level = 'YELLOW'),
       count(DISTINCT container_id) FILTER (WHERE container_level = 'RED')
FROM nlq.v_container_freetime WHERE shipment_status NOT IN ('CANCELLED', 'COMPLETED')
"""


def _today(db: Session) -> date:
    return db.scalar(text("SELECT nlq_today()"))


@router.get("/reports/demdet")
def demdet(db: Db, user: FinanceReader, from_month: str | None = None, to_month: str | None = None,
           group_by: GroupBy = "shipment") -> dict:
    this_month = _today(db).strftime("%Y-%m")
    return ok(demdet_report(db, from_month or this_month, to_month or from_month or this_month, group_by,
                            get_settings().fx_usd_vnd))


def _month_finance(db: Session, today: date) -> dict:
    start = today.replace(day=1)
    end = date(start.year + start.month // 12, start.month % 12 + 1, 1)

    def total(direction: ChargeDirection):
        return func.coalesce(func.sum(case((Charge.direction == direction, Charge.amount_vnd), else_=0)), 0)

    revenue, cost = db.execute(select(total(ChargeDirection.REVENUE), total(ChargeDirection.COST)).where(
        Charge.charge_date >= start, Charge.charge_date < end)).one()
    return {"month_revenue_vnd": int(revenue), "month_profit_vnd": int(revenue) - int(cost)}


@router.get("/reports/dashboard")
def dashboard(db: Db, user: DashboardReader) -> dict:
    today = _today(db)
    active = db.scalar(select(func.count()).select_from(Shipment).where(
        Shipment.status.notin_((ShipmentStatus.COMPLETED, ShipmentStatus.CANCELLED))))
    yellow, red = db.execute(text(_LEVEL_COUNTS)).one()
    data = {"as_of": today, "active_shipments": active, "containers_yellow": yellow, "containers_red": red,
            "do_expiring": [{"shipment_id": s.id, "code": s.code, "do_valid_until": s.do_valid_until}
                            for s in do_expiring_shipments(db, today)]}
    if can(user.role, "finance.read"):
        data |= _month_finance(db, today)
    return ok(data)
