"""Vòng đời đơn giao nội địa (Python thuần): cạnh hợp lệ, tập trạng thái, suy trạng thái từ event."""

from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from app.envelope import AppError
from app.events import effective_events


class LastMileStatus(StrEnum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RETURNED = "RETURNED"
    CANCELLED = "CANCELLED"


L = LastMileStatus

TRANSITIONS: dict[L, set[L]] = {
    L.CREATED: {L.ASSIGNED, L.CANCELLED},
    L.ASSIGNED: {L.PICKED_UP, L.CANCELLED},
    L.PICKED_UP: {L.DELIVERED, L.FAILED},
    L.FAILED: {L.ASSIGNED, L.RETURNED},
    L.DELIVERED: set(),
    L.RETURNED: set(),
    L.CANCELLED: set(),
}
POOL_EXCLUDED = frozenset({L.RETURNED, L.CANCELLED})  # kiện của các đơn này quay lại quỹ kiện
UNFINISHED = frozenset({L.CREATED, L.ASSIGNED, L.PICKED_UP, L.FAILED})

STATUS_LABEL_VI = {L.CREATED: "Mới tạo", L.ASSIGNED: "Đã phân công", L.PICKED_UP: "Đã lấy hàng",
                   L.DELIVERED: "Đã giao", L.FAILED: "Giao không thành công", L.RETURNED: "Đã hoàn về kho",
                   L.CANCELLED: "Đã huỷ"}


def assert_transition(from_: str, to: str) -> None:
    if L(to) not in TRANSITIONS[L(from_)]:
        raise AppError("INVALID_TRANSITION", f"Đơn giao đang {STATUS_LABEL_VI[L(from_)].lower()}, "
                       f"không chuyển sang {STATUS_LABEL_VI[L(to)].lower()} được", 409)


def derive_status(events: Iterable[Any]) -> L:
    """Trạng thái hiệu lực: bỏ event bị VOID, `REASSIGNED` giữ nguyên, event cuối trong các loại còn lại thắng."""
    status = L.CREATED
    for event in effective_events(events):
        if event.kind in L.__members__:
            status = L(event.kind)
    return status
