"""Vòng đời lệnh xe (Python thuần, không đụng DB): cạnh hợp lệ, điều kiện đổi xe, suy trạng thái từ event."""

from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from app.envelope import AppError
from app.events import effective_events


class TruckingStatus(StrEnum):
    PLANNED = "PLANNED"
    ASSIGNED = "ASSIGNED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


T = TruckingStatus

TRANSITIONS: dict[T, set[T]] = {
    T.PLANNED: {T.ASSIGNED, T.CANCELLED},
    T.ASSIGNED: {T.STARTED, T.CANCELLED},
    T.STARTED: {T.COMPLETED},
    T.COMPLETED: set(),
    T.CANCELLED: set(),
}
REASSIGNABLE = {T.ASSIGNED, T.STARTED}

STATUS_LABEL_VI = {T.PLANNED: "Đã lên kế hoạch", T.ASSIGNED: "Đã phân công", T.STARTED: "Đang chạy",
                   T.COMPLETED: "Hoàn tất", T.CANCELLED: "Đã huỷ"}


def assert_transition(from_: str, to: str) -> None:
    if T(to) not in TRANSITIONS[T(from_)]:
        raise AppError("INVALID_TRANSITION", f"Lệnh xe đang {STATUS_LABEL_VI[T(from_)].lower()}, "
                       f"không chuyển sang {STATUS_LABEL_VI[T(to)].lower()} được", 409)


def assert_can_reassign(status: str) -> None:
    if T(status) not in REASSIGNABLE:
        raise AppError("INVALID_TRANSITION", "Chỉ đổi xe / tài xế khi lệnh đã phân công hoặc đang chạy", 409)


def derive_status(events: Iterable[Any]) -> T:
    """Trạng thái hiệu lực: bỏ event bị VOID, `REASSIGNED` giữ nguyên, event cuối trong bốn loại còn lại thắng."""
    status = T.PLANNED
    for event in effective_events(events):
        if event.kind in T.__members__:
            status = T(event.kind)
    return status
