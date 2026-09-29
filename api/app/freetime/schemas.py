from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.freetime.models import CONTAINER_TYPES

FeeTypeName = Literal["DEM", "DET", "COMBINED"]
ContainerTypeName = Literal[*CONTAINER_TYPES]
LevelName = Literal["GREEN", "YELLOW", "RED", "NO_RULE", "MISSING_DATA"]
StatusName = Literal["NOT_STARTED", "OPEN", "CLOSED", "NO_RULE", "MISSING_DATA"]


class TierBody(BaseModel):
    from_day: int
    to_day: int | None = None
    rate_amount: int
    currency: str


class RuleBody(BaseModel):
    fee_type: FeeTypeName
    free_days: int = Field(ge=0, le=365)
    tiers: list[TierBody]


class RuleVersionIn(BaseModel):
    carrier_id: int
    port_id: int
    container_type: ContainerTypeName
    effective_from: date
    rules: list[RuleBody] = Field(min_length=1)


class OverrideIn(BaseModel):
    fee_type: FeeTypeName
    free_days: int = Field(ge=0, le=365)
    source: Literal["ARRIVAL_NOTICE", "DO", "CONTRACT"]
    document_id: int | None = None
