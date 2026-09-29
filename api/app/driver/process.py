"""Khung xử lý mọi thao tác của tài xế: idempotent theo `client_request_id`, khoá lô, kiểm trạng thái + bằng chứng."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.scope import scope_last_mile, scope_trucking
from app.documents.storage import save_photo
from app.driver.actions import (
    ACTIONS,
    HANDLERS,
    PHOTO,
    REASON,
    SIGNER,
    DriverAction,
    DriverCall,
    DriverResult,
    requires_for,
)
from app.envelope import AppError
from app.lastmile.models import LastMileEvent, LastMileOrder
from app.shipments.models import Shipment
from app.shipments.service import lock_shipment
from app.trucking.models import TruckingOrder, TruckingOrderEvent

MAX_SIGNER, MAX_REASON = 100, 500
EVIDENCE_LABELS = {PHOTO: "ảnh", SIGNER: "tên người ký nhận", REASON: "lý do"}


@dataclass(frozen=True)
class ActionForm:
    client_request_id: UUID
    action: str
    target_id: int
    lat: Decimal | None = None
    lng: Decimal | None = None
    device_time: datetime | None = None
    signer_name: str | None = None
    reason: str | None = None


def _invalid(message: str) -> AppError:
    return AppError("VALIDATION_ERROR", message, 422)


def _text(value: str | None, limit: int, label: str) -> str | None:
    value = (value or "").strip()
    if len(value) > limit:
        raise _invalid(f"{label} tối đa {limit} ký tự")
    return value or None


def _coordinate(value: str | None, low: int, high: int, label: str) -> Decimal | None:
    if not (value or "").strip():
        return None
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        raise _invalid(f"{label} không phải số") from None
    if not (low <= number <= high):
        raise _invalid(f"{label} phải nằm trong [{low}, {high}]")
    return number


def parse_form(client_request_id: str, action: str, target_id: str, lat: str | None = None, lng: str | None = None,
               device_time: str | None = None, signer_name: str | None = None, reason: str | None = None
               ) -> ActionForm:
    try:
        request_id = UUID(client_request_id)
    except ValueError:
        raise _invalid("client_request_id phải là UUID") from None
    if action not in ACTIONS:
        raise AppError("UNKNOWN_ACTION", f"Không có thao tác {action}", 400)
    try:
        target = int(target_id)
    except ValueError:
        raise _invalid("target_id phải là số nguyên") from None
    lat_value, lng_value = _coordinate(lat, -90, 90, "lat"), _coordinate(lng, -180, 180, "lng")
    if (lat_value is None) != (lng_value is None):
        raise _invalid("Phải gửi cả lat và lng, hoặc không gửi cả hai")
    when = None
    if (device_time or "").strip():
        try:
            when = datetime.fromisoformat(device_time.strip())
        except ValueError:
            raise _invalid("device_time không đúng định dạng ISO 8601") from None
        if when.tzinfo is None:
            raise _invalid("device_time phải có múi giờ")
    return ActionForm(request_id, action, target, lat_value, lng_value, when,
                      _text(signer_name, MAX_SIGNER, "signer_name"), _text(reason, MAX_REASON, "reason"))


Replay = tuple[str, int, int, str, datetime, int | None]


def find_replay(db: Session, client_request_id: UUID) -> Replay | None:
    """Event đã ghi cho mã này: (loại đích, id đích, id event, trạng thái, giờ, actor_id)."""
    for target, model in (("TRUCKING", TruckingOrderEvent), ("LAST_MILE", LastMileEvent)):
        event = db.scalar(select(model).where(model.client_request_id == client_request_id))
        if event is not None:
            return target, event.order_id, event.id, event.kind, event.occurred_at, event.actor_id
    return None


def _replayed(found: Replay, user: User, form: ActionForm) -> DriverResult:
    kind, target_id, event_id, status, occurred_at, actor_id = found
    if actor_id != user.id or target_id != form.target_id or kind != ACTIONS[form.action].target:
        raise AppError("DUPLICATE_REQUEST_ID", "Mã yêu cầu đã dùng cho thao tác khác", 409)
    return DriverResult(event_id, kind, target_id, status, occurred_at, replayed=True)


def _missing(required: list[str], form: ActionForm, has_photo: bool) -> list[str]:
    have = {PHOTO: has_photo, SIGNER: bool(form.signer_name), REASON: bool(form.reason)}
    return [item for item in required if not have[item]]


def _load_target(db: Session, user: User, action: DriverAction, target_id: int):
    """Lệnh xe hoặc đơn giao của chính tài xế (không thuộc về mình coi như không tồn tại)."""
    if action.target == "LAST_MILE":
        return db.scalar(scope_last_mile(select(LastMileOrder).where(LastMileOrder.id == target_id), user))
    return db.scalar(scope_trucking(select(TruckingOrder).where(TruckingOrder.id == target_id), user))


def process_driver_action(db: Session, user: User, form: ActionForm, photo) -> DriverResult:
    if (found := find_replay(db, form.client_request_id)) is not None:
        return _replayed(found, user, form)
    action = ACTIONS[form.action]
    order = _load_target(db, user, action, form.target_id)
    if order is None:
        raise AppError("NOT_FOUND", "Không tìm thấy việc này", 404)
    if action.target == "TRUCKING" and action.order_kind != order.kind:
        raise AppError("WRONG_ORDER_KIND", "Thao tác không dùng được cho loại lệnh này", 400)
    shipment: Shipment = lock_shipment(db, order.shipment_id)
    db.refresh(order)
    if (found := find_replay(db, form.client_request_id)) is not None:
        return _replayed(found, user, form)
    if order.status != action.from_status:
        raise AppError("INVALID_TRANSITION", "Không thực hiện được thao tác này ở trạng thái hiện tại", 409)
    has_photo = photo is not None and photo.size != 0
    if missing := _missing(requires_for(action, shipment), form, has_photo):
        names = ", ".join(EVIDENCE_LABELS[m] for m in missing)
        raise AppError("EVIDENCE_REQUIRED", f"Còn thiếu: {names}", 400, details={"missing": missing})
    handler = HANDLERS.get(action.code)
    if handler is None:
        raise AppError("ACTION_NOT_AVAILABLE", "Thao tác này chưa khả dụng", 501)
    occurred_at = datetime.now(UTC)
    stored = save_photo(photo) if has_photo else None
    call = DriverCall(user, action, order, shipment, form.client_request_id, occurred_at, form.device_time, form.lat,
                      form.lng, stored.sha256 if stored else None, form.signer_name, form.reason)
    return handler(db, call)
