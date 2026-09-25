import re

from pydantic import BaseModel, Field, field_validator


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    tax_code: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=500)
    active: bool = True


class CarrierIn(BaseModel):
    code: str = Field(min_length=2, max_length=10)
    name: str = Field(min_length=1, max_length=200)
    active: bool = True

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class PortIn(BaseModel):
    code: str
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    active: bool = True

    @field_validator("code")
    @classmethod
    def _unlocode(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.fullmatch(r"[A-Z]{5}", v):
            raise ValueError("Mã cảng phải là UN/LOCODE 5 chữ cái, ví dụ VNSGN")
        return v

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, v: list[str]) -> list[str]:
        return sorted({a.strip().upper() for a in v if a.strip()})


class WarehouseIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=500)
    customer_id: int | None = None
    active: bool = True


class TruckerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    active: bool = True


class TruckIn(BaseModel):
    trucker_id: int
    plate_no: str = Field(min_length=4, max_length=20)
    active: bool = True

    @field_validator("plate_no")
    @classmethod
    def _plate(cls, v: str) -> str:
        return v.strip().upper()


class DriverIn(BaseModel):
    trucker_id: int
    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    active: bool = True
