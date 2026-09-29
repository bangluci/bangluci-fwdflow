"""Tra cứu công khai theo mã vận đơn (không đăng nhập): chỉ trả trạng thái, ngày cập nhật và tên đã che."""

from datetime import date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.envelope import AppError, ok
from app.events import effective_events
from app.lastmile.models import LastMileEvent, LastMileOrder
from app.lastmile.state import LastMileStatus
from app.lastmile.tracking_code import format_code, normalize_code
from app.ratelimit import FixedWindowLimiter, client_ip, rate_key

TRACK_LIMIT_PER_IP = 30
NOT_FOUND_GLOBAL_LIMIT = 300
WINDOW_SECONDS = 60
TRACK_TTL_DAYS = 30
VN = ZoneInfo("Asia/Ho_Chi_Minh")
STATUS_LABELS = {
    "CREATED": "Chờ giao", "ASSIGNED": "Chờ giao", "PICKED_UP": "Đang giao", "DELIVERED": "Đã giao",
    "FAILED": "Giao không thành công, sẽ giao lại", "RETURNED": "Đã hoàn về kho", "CANCELLED": "Đã huỷ",
}
ENDED = (LastMileStatus.DELIVERED, LastMileStatus.RETURNED, LastMileStatus.CANCELLED)

ip_limiter = FixedWindowLimiter(TRACK_LIMIT_PER_IP, WINDOW_SECONDS)
not_found_limiter = FixedWindowLimiter(NOT_FOUND_GLOBAL_LIMIT, WINDOW_SECONDS)

router = APIRouter(tags=["public"])
Db = Annotated[Session, Depends(get_db)]


def mask_name(name: str) -> str:
    """"Nguyễn Văn An" → "N*** V*** A***"."""
    return " ".join(f"{word[0]}***" for word in name.split())


def _vn_date(moment: datetime) -> date:
    return moment.astimezone(VN).date()


def _find(db: Session, code: str | None, today: date) -> tuple[LastMileOrder, date] | None:
    """Đơn còn tra cứu được và ngày cập nhật gần nhất; hết hạn (30 ngày sau khi kết thúc) coi như không có."""
    if code is None:
        return None
    order = db.scalar(select(LastMileOrder).where(LastMileOrder.tracking_code == code))
    if order is None:
        return None
    events = effective_events(db.scalars(select(LastMileEvent).where(LastMileEvent.order_id == order.id)).all())
    if not events:
        return None
    updated = _vn_date(events[-1].occurred_at)
    ended = next((e for e in reversed(events) if e.kind == order.status), None)
    if order.status in ENDED and ended and _vn_date(ended.occurred_at) + timedelta(days=TRACK_TTL_DAYS) < today:
        return None
    return order, updated


@router.get("/public/track/{code}")
def track(code: str, request: Request, db: Db) -> dict:
    if not ip_limiter.hit(rate_key(client_ip(request))):
        raise AppError("RATE_LIMITED", "Bạn tra cứu quá nhiều lần, thử lại sau 1 phút", 429)
    found = _find(db, normalize_code(code), db.scalar(text("SELECT nlq_today()")))
    if found is None:
        if not not_found_limiter.hit("global"):
            raise AppError("RATE_LIMITED", "Bạn tra cứu quá nhiều lần, thử lại sau 1 phút", 429)
        raise AppError("NOT_FOUND", "Không tìm thấy vận đơn", 404)
    order, updated = found
    return ok({"tracking_code": format_code(order.tracking_code), "status": order.status,
               "status_label": STATUS_LABELS[order.status], "updated_date": updated,
               "recipient_masked": mask_name(order.recipient_name)})
