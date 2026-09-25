from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.audit.models import AuditLog
from app.auth.deps import require
from app.auth.models import User
from app.db import get_db
from app.envelope import ok

router = APIRouter()
VN = ZoneInfo("Asia/Ho_Chi_Minh")


@router.get("/audit")
def list_audit(entity: str | None = None, entity_id: str | None = None, actor_id: int | None = None,
               date_from: date | None = None, date_to: date | None = None, limit: int = 200,
               db: DbSession = Depends(get_db), _: User = Depends(require("audit.read"))) -> dict:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(date_from, time.min, VN))
    if date_to:
        stmt = stmt.where(AuditLog.created_at < datetime.combine(date_to + timedelta(days=1), time.min, VN))
    rows = [
        {"id": a.id, "actor_id": a.actor_id, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
         "before": a.before, "after": a.after, "ip": a.ip, "created_at": a.created_at.isoformat()}
        for a in db.scalars(stmt)
    ]
    return ok(rows)
