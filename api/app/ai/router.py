from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.guard import ai_enabled, tokens_today
from app.auth.deps import require
from app.auth.models import Role, User
from app.config import get_settings
from app.db import get_db
from app.envelope import ok

router = APIRouter(tags=["ai"])
Db = Annotated[Session, Depends(get_db)]
Internal = Annotated[User, Depends(require("dashboard.read"))]


@router.get("/ai/status")
def ai_status(db: Db, user: Internal) -> dict:
    """Mọi vai trò nội bộ xem được AI bật hay tắt; số token và trần chỉ Admin thấy."""
    status = ai_enabled(db)
    is_admin = user.role == Role.ADMIN
    return ok({"enabled": status.enabled, "reason": status.reason,
               "tokens_today": tokens_today(db) if is_admin else None,
               "budget": get_settings().ai_daily_token_budget if is_admin else None})
