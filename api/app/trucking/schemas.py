from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, StringConstraints

Location = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("planned_at phải có múi giờ, ví dụ 2026-11-26T08:00:00+07:00")
    return value


class OrderCreate(BaseModel):
    container_id: int
    kind: Literal["PICKUP_FULL", "RETURN_EMPTY"]
    trucker_id: int
    pickup_location: Location
    drop_location: Location
    planned_at: Annotated[datetime, AfterValidator(_aware)]


class AssignIn(BaseModel):
    truck_id: int
    driver_id: int


class ReassignIn(AssignIn):
    reason: str


class CancelIn(BaseModel):
    reason: str


AdjustReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]


class VoidIn(BaseModel):
    reason: AdjustReason


class RetimeIn(BaseModel):
    occurred_at: datetime
    reason: AdjustReason
