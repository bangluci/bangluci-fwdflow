import re
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

PHONE = re.compile(r"^(0|\+84)\d{9,10}$")
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]


def _phone(value: str) -> str:
    cleaned = re.sub(r"[\s.]", "", value)
    if not PHONE.fullmatch(cleaned):
        raise ValueError("Số điện thoại không hợp lệ (0xxxxxxxxx hoặc +84xxxxxxxxx)")
    return cleaned


class OrderIn(BaseModel):
    recipient_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    recipient_phone: Annotated[str, AfterValidator(_phone)]
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]
    packages: int = Field(ge=1)
    weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    planned_date: date
    driver_id: int | None = None


class SplitIn(BaseModel):
    orders: list[OrderIn] = Field(min_length=1, max_length=50)


class AssignIn(BaseModel):
    driver_id: int
    planned_date: date


class ReassignIn(BaseModel):
    driver_id: int
    planned_date: date | None = None
    reason: Reason


class ReasonIn(BaseModel):
    reason: Reason
