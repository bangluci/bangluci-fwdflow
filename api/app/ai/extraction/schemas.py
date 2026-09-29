"""Schema trích xuất (đầu ra có cấu trúc của Claude). Trường nghiệp vụ nào cũng nullable: không thấy thì null."""

from datetime import date as Date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ContainerType = Literal["20GP", "40GP", "40HC", "45HC", "20RF", "40RF", "40RH"]
DocTypeGuess = Literal["MBL", "HBL", "INVOICE", "PACKING_LIST", "UNKNOWN"]
PROMPT_DIR = Path(__file__).parent / "prompts"


class _Extract(BaseModel):
    detected_doc_type: DocTypeGuess
    legible: bool
    suspicious_content: bool
    suspicious_note: str | None


class BLContainer(BaseModel):
    container_no: str | None
    seal_no: str | None
    container_type_raw: str | None
    container_type: ContainerType | None
    packages: int | None
    gross_weight_kg: Decimal | None


class BLExtract(_Extract):
    bl_no: str | None
    carrier_name: str | None
    shipper: str | None
    consignee: str | None
    notify_party: str | None
    vessel: str | None
    voyage: str | None
    pol: str | None
    pod: str | None
    onboard_date: Date | None
    total_packages: int | None
    package_unit: str | None
    gross_weight_kg: Decimal | None
    containers: list[BLContainer]


class InvoiceLine(BaseModel):
    description: str | None
    quantity: Decimal | None
    unit: str | None
    unit_price: Decimal | None
    amount: Decimal | None


class InvoiceExtract(_Extract):
    invoice_no: str | None
    invoice_date: Date | None
    seller: str | None
    buyer: str | None
    currency: str | None
    incoterm: str | None
    total_amount: Decimal | None
    lines: list[InvoiceLine]


class PackingLine(BaseModel):
    description: str | None
    packages: int | None
    quantity: Decimal | None
    unit: str | None
    gross_weight_kg: Decimal | None
    net_weight_kg: Decimal | None


class PackingContainer(BaseModel):
    container_no: str | None
    seal_no: str | None


class PackingListExtract(_Extract):
    packing_list_no: str | None
    date: Date | None
    total_packages: int | None
    total_gross_weight_kg: Decimal | None
    total_net_weight_kg: Decimal | None
    lines: list[PackingLine]
    containers: list[PackingContainer]


SCHEMA_BY_DOC_TYPE: dict[str, type[_Extract]] = {
    "MBL": BLExtract, "HBL": BLExtract, "INVOICE": InvoiceExtract, "PACKING_LIST": PackingListExtract,
}
PROMPT_BY_DOC_TYPE = {"MBL": "bl_v1", "HBL": "bl_v1", "INVOICE": "invoice_v1", "PACKING_LIST": "packing_list_v1"}


def prompt_version(doc_type: str) -> str:
    return PROMPT_BY_DOC_TYPE[doc_type]


def load_prompt(doc_type: str) -> str:
    return (PROMPT_DIR / f"{prompt_version(doc_type)}.md").read_text(encoding="utf-8")
