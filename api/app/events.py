"""Event append-only dùng chung: cột chuẩn của mọi bảng `*_events` và cách suy ra event còn hiệu lực."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class EventMixin:
    """`kind` là loại mốc nghiệp vụ, hoặc `RETIME` / `VOID` (điều chỉnh, không phải cạnh của state machine)."""

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reason: Mapped[str | None] = mapped_column(String)

    @declared_attr
    def actor_id(cls) -> Mapped[int | None]:  # noqa: N805
        return mapped_column(ForeignKey("users.id"))

    @declared_attr
    def adjusts_event_id(cls) -> Mapped[int | None]:  # noqa: N805
        return mapped_column(ForeignKey(f"{cls.__tablename__}.id"))  # type: ignore[attr-defined]


@dataclass(frozen=True)
class EffectiveEvent:
    id: int
    kind: str
    occurred_at: datetime  # sau khi áp RETIME
    original_occurred_at: datetime
    recorded_at: datetime
    actor_id: int | None


def effective_events(events: Iterable[Any]) -> list[EffectiveEvent]:
    """Bỏ event bị VOID (và chính các VOID), áp RETIME còn lại theo `recorded_at` (bản sau thắng)."""
    ordered = sorted(events, key=lambda e: (e.recorded_at, e.id))
    voided = {e.adjusts_event_id for e in ordered if e.kind == "VOID"}
    retimed: dict[int, datetime] = {}
    for e in ordered:
        if e.kind == "RETIME" and e.id not in voided:
            retimed[e.adjusts_event_id] = e.occurred_at
    return [
        EffectiveEvent(e.id, e.kind, retimed.get(e.id, e.occurred_at), e.occurred_at, e.recorded_at, e.actor_id)
        for e in ordered
        if e.kind not in ("RETIME", "VOID") and e.id not in voided
    ]
