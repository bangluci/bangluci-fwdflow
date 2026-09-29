"""Báo cáo DEM/DET: phí ước tính theo bậc (từ đồng hồ free time) so với chi phí thực tế đã nhập (Charge).

Phạm vi: lô FCL không huỷ có ít nhất một mốc DISCHARGED hiệu lực; tháng của lô là tháng (giờ VN) của mốc sớm nhất.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.envelope import AppError
from app.finance.models import DEMDET_CATEGORIES, Charge, ChargeDirection
from app.finance.service import compute_amount_vnd

GroupBy = Literal["month", "customer", "carrier", "shipment"]
MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
MAX_MONTHS = 12
FLAG_DEVIATION = 5  # lệch quá 1/5 (20%) ước tính thì gắn cờ

_ROWS = """
SELECT v.shipment_id, v.shipment_code, v.customer_name, v.carrier_name, v.fee_amount, v.fee_currency,
       v.discharged_date, s.customer_id, s.carrier_id
FROM nlq.v_container_freetime v JOIN shipments s ON s.id = v.shipment_id
WHERE v.shipment_status <> 'CANCELLED'
"""


def is_demdet_flagged(estimate_vnd: int, actual_vnd: int) -> bool:
    if estimate_vnd == 0:
        return actual_vnd > 0
    return FLAG_DEVIATION * abs(actual_vnd - estimate_vnd) > estimate_vnd


def _month_index(value: str) -> int:
    match = MONTH_PATTERN.fullmatch(value or "")
    if match is None:
        raise AppError("INVALID_RANGE", "Tháng phải có dạng YYYY-MM", 400)
    return int(match[1]) * 12 + int(match[2]) - 1


def validate_range(from_month: str, to_month: str) -> None:
    start, end = _month_index(from_month), _month_index(to_month)
    if start > end or end - start + 1 > MAX_MONTHS:
        raise AppError("INVALID_RANGE", f"Khoảng tháng không hợp lệ (tối đa {MAX_MONTHS} tháng)", 400)


@dataclass
class _Shipment:
    id: int
    code: str
    customer: tuple[int, str]
    carrier: tuple[int | None, str | None]
    first_discharged: date | None = None
    estimate_vnd: int = 0
    actual_vnd: int = 0
    keys: dict[str, tuple[Any, str]] = field(default_factory=dict)


def _collect(db: Session, fx: Decimal) -> dict[int, _Shipment]:
    shipments: dict[int, _Shipment] = {}
    for row in db.execute(text(_ROWS)).mappings():
        item = shipments.setdefault(row["shipment_id"], _Shipment(
            row["shipment_id"], row["shipment_code"], (row["customer_id"], row["customer_name"]),
            (row["carrier_id"], row["carrier_name"])))
        if row["discharged_date"] and (item.first_discharged is None or row["discharged_date"] < item.first_discharged):
            item.first_discharged = row["discharged_date"]
        amount = row["fee_amount"]
        if amount:
            item.estimate_vnd += amount if row["fee_currency"] == "VND" else compute_amount_vnd(amount, "USD", fx)[0]
    return shipments


def _actuals(db: Session, ids: list[int]) -> dict[int, int]:
    rows = db.execute(select(Charge.shipment_id, func.sum(Charge.amount_vnd)).where(
        Charge.shipment_id.in_(ids), Charge.direction == ChargeDirection.COST,
        Charge.category.in_(DEMDET_CATEGORIES)).group_by(Charge.shipment_id))
    return {shipment_id: int(total) for shipment_id, total in rows}


def _group_key(item: _Shipment, group_by: str) -> tuple[Any, str]:
    if group_by == "month":
        month = item.first_discharged.strftime("%Y-%m")
        return month, month
    if group_by == "customer":
        return item.customer
    if group_by == "carrier":
        return item.carrier[0], item.carrier[1] or "(chưa có hãng tàu)"
    return item.id, item.code


def demdet_report(db: Session, from_month: str, to_month: str, group_by: GroupBy, fx_usd_vnd: int) -> dict[str, Any]:
    validate_range(from_month, to_month)
    shipments = {i: s for i, s in _collect(db, Decimal(fx_usd_vnd)).items()
                 if s.first_discharged and from_month <= s.first_discharged.strftime("%Y-%m") <= to_month}
    for shipment_id, total in _actuals(db, list(shipments)).items():
        shipments[shipment_id].actual_vnd = total
    groups: dict[Any, dict[str, Any]] = defaultdict(lambda: {"shipments": 0, "estimate_vnd": 0, "actual_vnd": 0,
                                                             "flagged_shipments": 0})
    labels: dict[Any, str] = {}
    for item in shipments.values():
        key, label = _group_key(item, group_by)
        labels[key] = label
        group = groups[key]
        group["shipments"] += 1
        group["estimate_vnd"] += item.estimate_vnd
        group["actual_vnd"] += item.actual_vnd
        group["flagged_shipments"] += is_demdet_flagged(item.estimate_vnd, item.actual_vnd)
    rows = [{"key": key, "label": labels[key], **group,
             "deviation_pct": round((group["actual_vnd"] - group["estimate_vnd"]) * 100 / group["estimate_vnd"], 1)
             if group["estimate_vnd"] else None}
            for key, group in sorted(groups.items(), key=lambda kv: labels[kv[0]])]
    totals = {"estimate_vnd": sum(r["estimate_vnd"] for r in rows), "actual_vnd": sum(r["actual_vnd"] for r in rows),
              "flagged_shipments": sum(r["flagged_shipments"] for r in rows)}
    return {"from_month": from_month, "to_month": to_month, "group_by": group_by, "fx_usd_vnd": fx_usd_vnd,
            "rows": rows, "totals": totals}
