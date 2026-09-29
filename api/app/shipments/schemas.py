from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.shipments.state import ShipmentStatus

LoadType = Literal["FCL", "LCL"]
DeliveryMode = Literal["VIA_WAREHOUSE", "CONTAINER_TO_DOOR"]
ContainerType = Literal["20GP", "40GP", "40HC", "45HC", "20RF", "40RF", "40RH"]
Lane = Literal["GREEN", "YELLOW", "RED"]

# Số B/L: bỏ khoảng trắng hai đầu, viết hoa, tối đa 35 ký tự; chuỗi rỗng coi như không có.
BlNo = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, max_length=35),
                 AfterValidator(lambda v: v or None)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


class _ShipmentFields(BaseModel):
    carrier_id: int | None = None
    pol_port_id: int | None = None
    pod_port_id: int | None = None
    dest_warehouse_id: int | None = None
    mbl_no: BlNo | None = None
    hbl_no: BlNo | None = None
    vessel: ShortText | None = None
    voyage: ShortText | None = None
    etd: date | None = None
    eta: date | None = None
    claims_fta: bool | None = None
    do_no: ShortText | None = None
    do_valid_until: date | None = None
    total_packages: int | None = Field(default=None, ge=0)
    staff_id: int | None = None

    @model_validator(mode="after")
    def _etd_not_after_eta(self):
        if self.etd and self.eta and self.etd > self.eta:
            raise ValueError("ETD không được sau ETA")
        return self


class ShipmentCreate(_ShipmentFields):
    load_type: LoadType
    delivery_mode: DeliveryMode
    customer_id: int
    claims_fta: bool = False

    @model_validator(mode="after")
    def _lcl_only_via_warehouse(self):
        if self.load_type == "LCL" and self.delivery_mode != "VIA_WAREHOUSE":
            raise ValueError("Lô LCL chỉ giao qua kho (VIA_WAREHOUSE)")
        return self


class ShipmentUpdate(_ShipmentFields):
    """Chỉ cập nhật các trường có trong `model_fields_set`; gửi `null` nghĩa là xoá giá trị."""

    model_config = ConfigDict(extra="forbid")
    version: int
    customer_id: int | None = Field(default=None)


class TransitionIn(BaseModel):
    to_status: ShipmentStatus


class CancelIn(BaseModel):
    reason: Reason


class ItemIn(BaseModel):
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit: ShortText | None = None
    packages: int | None = Field(default=None, ge=0)
    gross_weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    value_amount: int | None = Field(default=None, ge=0)
    value_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    hs_code: str | None = Field(default=None, pattern=r"^[0-9]{8}$")


class DeclarationIn(BaseModel):
    declaration_no: str = Field(pattern=r"^[0-9]{12}$")
    type_code: str = Field(pattern=r"^[A-Z][0-9]{2}$")
    registered_at: AwareDatetime
    lane: Lane | None = None
    cleared_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _cleared_after_registered(self):
        if self.cleared_at and self.cleared_at < self.registered_at:
            raise ValueError("Ngày thông quan không được trước ngày đăng ký tờ khai")
        return self


class ContainerIn(BaseModel):
    container_no: str = Field(min_length=1, max_length=30)
    container_type: ContainerType
    seal_no: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, max_length=30)] | None = None
    gross_weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)


class DischargedIn(BaseModel):
    kind: Literal["DISCHARGED"]
    occurred_at: AwareDatetime | None = None


class RetimeIn(BaseModel):
    kind: Literal["RETIME"]
    adjusts_event_id: int
    occurred_at: AwareDatetime
    reason: Reason


ContainerEventIn = Annotated[DischargedIn | RetimeIn, Field(discriminator="kind")]
