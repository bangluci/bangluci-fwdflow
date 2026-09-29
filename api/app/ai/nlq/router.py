from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.nlq.models import NlQueryLog
from app.ai.nlq.service import MAX_QUESTION, answer_question
from app.audit.service import record_audit, snapshot
from app.auth.deps import require
from app.auth.models import User
from app.db import get_db
from app.envelope import AppError, ok

router = APIRouter(tags=["assistant"])
Db = Annotated[Session, Depends(get_db)]
Asker = Annotated[User, Depends(require("assistant.ask"))]
LOG_AUDIT_FIELDS = ("nlq_role", "validation_result", "user_rating")


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=MAX_QUESTION)


class RatingIn(BaseModel):
    correct: bool


@router.post("/assistant/ask")
def ask(body: AskIn, db: Db, user: Asker) -> dict:
    """Thứ tự kiểm: quyền → độ dài câu hỏi → cờ AI và trần token (`AI_DISABLED`) → lượt mỗi giờ (`RATE_LIMITED`)."""
    result = answer_question(db, user, body.question)
    db.commit()
    return ok(result)


@router.post("/assistant/{log_id}/rating")
def rate(log_id: int, body: RatingIn, db: Db, user: Asker) -> dict:
    """Người hỏi chấm câu trả lời đúng / sai; log của người khác coi như không tồn tại."""
    log = db.get(NlQueryLog, log_id)
    if log is None or log.user_id != user.id:
        raise AppError("NOT_FOUND", "Không tìm thấy lần hỏi", 404)
    before = snapshot(log, LOG_AUDIT_FIELDS)
    log.user_rating = body.correct
    db.flush()
    record_audit(db, user.id, "UPDATE", "nl_query", log.id, before=before, after=snapshot(log, LOG_AUDIT_FIELDS))
    db.commit()
    return ok({"log_id": log.id, "correct": log.user_rating})
