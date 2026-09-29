from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.audit.models import AuditLog
from app.audit.service import AUDIT_FIELDS
from app.auth.deps import require
from app.auth.models import User
from app.db import get_db
from app.envelope import ok

router = APIRouter()
VN = ZoneInfo("Asia/Ho_Chi_Minh")
Admin = Annotated[User, Depends(require("audit.read"))]


@router.get("/audit/entities")
def list_entities(_: Admin) -> dict:
    return ok(sorted(AUDIT_FIELDS))


@router.get("/audit")
def list_audit(_: Admin, db: Annotated[DbSession, Depends(get_db)], entity: str | None = None,
               entity_id: str | None = None, actor_id: int | None = None, date_from: date | None = None,
               date_to: date | None = None, page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=100)] = 50) -> dict:
    """Nhật ký thay đổi, mới nhất lên đầu; `before` / `after` trả nguyên như đã lưu (PII đã che)."""
    conditions = []
    if entity:
        conditions.append(AuditLog.entity == entity)
    if entity_id:
        conditions.append(AuditLog.entity_id == entity_id)
    if actor_id:
        conditions.append(AuditLog.actor_id == actor_id)
    if date_from:
        conditions.append(AuditLog.created_at >= datetime.combine(date_from, time.min, VN))
    if date_to:
        conditions.append(AuditLog.created_at < datetime.combine(date_to + timedelta(days=1), time.min, VN))
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
    rows = db.execute(
        select(AuditLog, User.full_name).outerjoin(User, User.id == AuditLog.actor_id).where(*conditions)
        .order_by(AuditLog.id.desc()).limit(page_size).offset((page - 1) * page_size))
    data = [{"id": a.id, "at": a.created_at, "actor_id": a.actor_id, "actor_name": name, "action": a.action,
             "entity": a.entity, "entity_id": a.entity_id, "before": a.before, "after": a.after}
            for a, name in rows]
    return ok(data, meta={"total": total, "page": page, "limit": page_size})
