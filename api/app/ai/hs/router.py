from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.guard import check_user_rate, require_ai
from app.ai.hs.models import HsSuggestionLog
from app.ai.hs.suggest import HsItem, suggest_hs
from app.audit.service import record_audit, snapshot
from app.auth.deps import require
from app.auth.models import User
from app.db import get_db
from app.envelope import AppError, ok

router = APIRouter(tags=["hs"])
Db = Annotated[Session, Depends(get_db)]
Suggester = Annotated[User, Depends(require("hs.suggest"))]
LOG_AUDIT_FIELDS = ("shipment_item_id", "chosen_code", "status")


class SuggestIn(BaseModel):
    description: str = Field(max_length=5000)  # server cắt còn 500 ký tự trước khi tìm
    shipment_item_id: int | None = None


class ChoiceIn(BaseModel):
    code: str = Field(pattern=r"^[0-9]{8}$")


def _item_out(item: HsItem) -> dict:
    return {"code": item.code, "description_vi": item.description_vi, "description_en": item.description_en,
            "rank": item.rank, "rrf_score": item.rrf_score, "cosine": item.cosine,
            "explanation": item.explanation, "needs_review": item.needs_review}


@router.post("/hs/suggest")
def hs_suggest(body: SuggestIn, db: Db, user: Suggester) -> dict:
    """Thứ tự kiểm: quyền → cờ AI và trần token ngày (`AI_DISABLED`) → lượt mỗi giờ (`RATE_LIMITED`) → gợi ý."""
    require_ai(db)
    check_user_rate(user, "hs")
    result = suggest_hs(db, user, body.description, body.shipment_item_id)
    db.commit()
    return ok({"log_id": result.log_id, "status": result.status, "degraded": result.degraded, "hint": result.hint,
               "items": [_item_out(item) for item in result.items]})


@router.post("/hs/suggestions/{log_id}/choice")
def hs_choice(log_id: int, body: ChoiceIn, db: Db, user: Suggester) -> dict:
    """Ghi mã người dùng đã chọn (để đo tỷ lệ chấp nhận); chỉ nhận mã nằm trong ứng viên của lần gợi ý đó."""
    log = db.get(HsSuggestionLog, log_id)
    if log is None or log.user_id != user.id:  # log của người khác coi như không tồn tại
        raise AppError("NOT_FOUND", "Không tìm thấy lần gợi ý", 404)
    if body.code not in {candidate["code"] for candidate in log.candidates}:
        raise AppError("CODE_NOT_IN_SUGGESTION", "Mã này không nằm trong danh sách gợi ý", 400)
    before = snapshot(log, LOG_AUDIT_FIELDS)
    log.chosen_code, log.chosen_at = body.code, datetime.now(UTC)
    db.flush()
    record_audit(db, user.id, "UPDATE", "hs_suggestion", log.id, before=before, after=snapshot(log, LOG_AUDIT_FIELDS))
    db.commit()
    return ok({"log_id": log.id, "chosen_code": log.chosen_code})
