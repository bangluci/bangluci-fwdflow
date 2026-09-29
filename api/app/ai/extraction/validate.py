"""Kiểm tra trường sau khi Claude trích xuất: sai kiểm tra chặn duyệt (BLOCK), nghi vấn chỉ cảnh báo (WARN)."""

import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.ai.extraction.render import MAX_PAGES
from app.shipments.iso6346 import is_valid_container_no

CONTAINER_TYPE_MAP = {
    "22G1": "20GP", "42G1": "40GP", "45G1": "40HC", "L5G1": "45HC", "22R1": "20RF", "42R1": "40RF", "45R1": "40RH",
    "20DC": "20GP", "20GP": "20GP", "40DC": "40GP", "40GP": "40GP", "40HQ": "40HC", "40HC": "40HC",
    "45HQ": "45HC", "45HC": "45HC", "20RF": "20RF", "20RH": "20RF", "40RF": "40RF", "40RH": "40RH", "40RQ": "40RH",
}
MIN_YEARS_BACK = 3
MAX_DAYS_AHEAD = 366
NEGATIVE_SCALARS = {
    "HBL": ("total_packages", "gross_weight_kg"), "MBL": ("total_packages", "gross_weight_kg"),
    "INVOICE": ("total_amount",),
    "PACKING_LIST": ("total_packages", "total_gross_weight_kg", "total_net_weight_kg"),
}
NEGATIVE_LINE_FIELDS = {
    "containers": ("packages", "gross_weight_kg"),
    "lines": {"INVOICE": ("quantity", "unit_price", "amount"),
              "PACKING_LIST": ("packages", "quantity", "gross_weight_kg", "net_weight_kg")},
}
DATE_FIELDS = {"HBL": "onboard_date", "MBL": "onboard_date", "INVOICE": "invoice_date", "PACKING_LIST": "date"}


@dataclass(frozen=True)
class FieldIssue:
    path: str
    code: str
    level: str  # BLOCK | WARN
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _number(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _raw_key(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", raw.upper())


def _line_fields(doc_type: str) -> list[tuple[str, tuple[str, ...]]]:
    lines = NEGATIVE_LINE_FIELDS["lines"].get(doc_type)
    pairs = [("containers", NEGATIVE_LINE_FIELDS["containers"])] if doc_type in ("HBL", "MBL") else []
    return pairs + ([("lines", lines)] if lines else [])


def _negatives(doc_type: str, data: dict) -> list[FieldIssue]:
    issues = []
    for field in NEGATIVE_SCALARS[doc_type]:
        value = _number(data.get(field))
        if value is not None and value < 0:
            issues.append(FieldIssue(f"/{field}", "NEGATIVE", "BLOCK", "Giá trị không được âm"))
    for collection, fields in _line_fields(doc_type):
        for index, row in enumerate(data.get(collection) or []):
            for field in fields:
                value = _number(row.get(field))
                if value is not None and value < 0:
                    issues.append(FieldIssue(f"/{collection}/{index}/{field}", "NEGATIVE", "BLOCK",
                                             "Giá trị không được âm"))
    return issues


def _container_issues(data: dict) -> list[FieldIssue]:
    issues = []
    for index, row in enumerate(data.get("containers") or []):
        number = row.get("container_no")
        if number and not is_valid_container_no(number):
            issues.append(FieldIssue(f"/containers/{index}/container_no", "CHECK_DIGIT", "BLOCK",
                                     "Số container sai check digit ISO 6346"))
        raw, mapped = row.get("container_type_raw"), row.get("container_type")
        if not raw:
            continue
        expected = CONTAINER_TYPE_MAP.get(_raw_key(raw))
        path = f"/containers/{index}/container_type"
        if expected is None or mapped is None:
            issues.append(FieldIssue(path, "CONTAINER_TYPE_UNMAPPED", "BLOCK",
                                     f"Không quy được loại container '{raw}' về loại chuẩn"))
        elif expected != mapped:
            issues.append(FieldIssue(path, "CONTAINER_TYPE_MISMATCH", "BLOCK",
                                     f"Mã '{raw}' tương ứng {expected}, không phải {mapped}"))
    return issues


def _date_issues(doc_type: str, data: dict, today: date) -> list[FieldIssue]:
    field = DATE_FIELDS[doc_type]
    raw = data.get(field)
    if not raw:
        return []
    value = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
    earliest, latest = today.replace(year=today.year - MIN_YEARS_BACK), today + timedelta(days=MAX_DAYS_AHEAD)
    if not earliest <= value <= latest:
        return [FieldIssue(f"/{field}", "DATE_OUT_OF_RANGE", "BLOCK", "Ngày nằm ngoài khoảng hợp lý")]
    return []


def validate_fields(doc_type: str, data: dict, pages: int, today: date | None = None) -> list[FieldIssue]:
    """`data` là kết quả đã dump từ schema; `pages` là số trang của file gốc."""
    today = today or date.today()
    issues = [*_container_issues(data), *_negatives(doc_type, data), *_date_issues(doc_type, data, today)]
    if pages > MAX_PAGES:
        issues.append(FieldIssue("/pages", "PAGES_TRUNCATED", "WARN",
                                 f"Chứng từ có {pages} trang, AI chỉ đọc {MAX_PAGES} trang đầu"))
    return issues
