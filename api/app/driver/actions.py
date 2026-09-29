"""Bảng thao tác của tài xế và các kiểu dùng chung giữa khung xử lý và handler từng thao tác."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.auth.models import User
from app.shipments.models import Shipment

PHOTO, SIGNER, REASON = "photo", "signer_name", "reason"


@dataclass(frozen=True)
class DriverAction:
    code: str
    label: str
    order_kind: str
    from_status: str
    to_status: str
    required_evidence: frozenset[str] = frozenset()
    c2d_evidence: frozenset[str] = frozenset()  # cần thêm khi lô giao thẳng tới cửa (CONTAINER_TO_DOOR)


ACTION_LIST = (
    DriverAction("TRUCK_START", "Đã lấy cont", "PICKUP_FULL", "ASSIGNED", "STARTED", frozenset({PHOTO})),
    DriverAction("TRUCK_COMPLETE", "Đã tới kho đích", "PICKUP_FULL", "STARTED", "COMPLETED",
                 c2d_evidence=frozenset({PHOTO, SIGNER})),
    DriverAction("RETURN_START", "Đã nhận vỏ rỗng tại kho", "RETURN_EMPTY", "ASSIGNED", "STARTED"),
    DriverAction("RETURN_COMPLETE", "Đã trả vỏ rỗng", "RETURN_EMPTY", "STARTED", "COMPLETED", frozenset({PHOTO})),
)
ACTIONS: dict[str, DriverAction] = {a.code: a for a in ACTION_LIST}


def requires_for(action: DriverAction, shipment: Shipment) -> list[str]:
    needed = set(action.required_evidence)
    if shipment.delivery_mode == "CONTAINER_TO_DOOR":
        needed |= action.c2d_evidence
    return sorted(needed)


@dataclass(frozen=True)
class DriverCall:
    """Mọi thứ handler cần: đã khoá lô, đã kiểm trạng thái và bằng chứng."""

    user: User
    action: DriverAction
    order: Any  # TruckingOrder (hoặc đơn giao ở Tuần 10)
    shipment: Shipment
    client_request_id: UUID
    occurred_at: datetime  # giờ server, tính một lần
    device_time: datetime | None
    lat: Decimal | None
    lng: Decimal | None
    photo_sha256: str | None
    signer_name: str | None
    reason: str | None


@dataclass(frozen=True)
class DriverResult:
    event_id: int
    target_kind: str
    target_id: int
    status: str
    occurred_at: datetime
    replayed: bool = False


def driver_event_fields(call: DriverCall) -> dict:
    """Các cột chung của event tài xế (`device_time` chỉ để tham khảo, không dùng làm mốc nghiệp vụ)."""
    return {"kind": call.action.to_status, "occurred_at": call.occurred_at, "actor_id": call.user.id,
            "device_time": call.device_time, "lat": call.lat, "lng": call.lng, "photo_sha256": call.photo_sha256,
            "signer_name": call.signer_name, "reason": call.reason, "client_request_id": call.client_request_id}


Handler = Callable[[Any, DriverCall], DriverResult]
HANDLERS: dict[str, Handler] = {}
