"""Đối chiếu chéo các chứng từ đã duyệt: thuần hàm, không đụng DB (spec mục 2 "Ranh giới AI ↔ dữ liệu chuẩn").

LLM chỉ trích xuất; việc so khớp là luật xác định ở đây.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any

BLOCK, WARN = "BLOCK", "WARN"
INSUFFICIENT, MATCH, DISCREPANCY = "INSUFFICIENT", "MATCH", "DISCREPANCY"
CONTAINER_DOCS = ("MBL", "HBL", "PACKING_LIST")
LEGAL_SUFFIXES = frozenset({
    "CO", "LTD", "LIMITED", "JSC", "CORP", "CORPORATION", "INC", "LLC", "PTE", "COMPANY", "CONG", "TY", "CTY",
    "TNHH", "CP", "PHAN", "MTV", "TRACH", "NHIEM", "HUU", "HAN",
})


@dataclass(frozen=True)
class Discrepancy:
    key: str
    kind: str
    level: str
    field: str
    values: dict[str, Any]


@dataclass(frozen=True)
class CrosscheckResult:
    status: str
    discrepancies: list[Discrepancy] = field(default_factory=list)


def normalize_company(name: str | None) -> str:
    """Viết hoa, bỏ dấu (Đ→D), bỏ dấu câu và hậu tố pháp lý (CO LTD, TNHH, CP...)."""
    if not name:
        return ""
    text = name.replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).upper()
    tokens = re.sub(r"[^A-Z0-9]+", " ", text).split()
    return " ".join(token for token in tokens if token not in LEGAL_SUFFIXES)


def token_set_ratio(a: str, b: str) -> float:
    """Độ giống theo tập token (0..1): tên đảo thứ tự hoặc thêm bớt vài từ vẫn giống nhau."""
    set_a, set_b = set(a.split()), set(b.split())
    if not set_a or not set_b:
        return 0.0
    common = " ".join(sorted(set_a & set_b))
    first = " ".join([common, *sorted(set_a - set_b)]).strip()
    second = " ".join([common, *sorted(set_b - set_a)]).strip()

    def ratio(x: str, y: str) -> float:
        return SequenceMatcher(None, x, y).ratio()

    return max(ratio(common, first), ratio(common, second), ratio(first, second))


def _container_no(raw: str | None) -> str | None:
    return re.sub(r"[\s-]+", "", raw).upper() if raw else None


def _containers(doc: dict) -> dict[str, str | None]:
    """{số container: seal} của một chứng từ (bỏ dòng không có số)."""
    rows = {}
    for row in doc.get("containers") or []:
        number = _container_no(row.get("container_no"))
        if number:
            rows[number] = (row.get("seal_no") or "").strip().upper() or None
    return rows


def _decimal(value: Any) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


def _container_discrepancies(docs: dict[str, dict], level: str) -> list[Discrepancy]:
    per_doc = {name: _containers(docs[name]) for name in CONTAINER_DOCS if name in docs and _containers(docs[name])}
    if len(per_doc) < 2:
        return []
    found = []
    for number in sorted(set().union(*per_doc.values())):
        present = {name for name, rows in per_doc.items() if number in rows}
        if present != set(per_doc):
            values = {name: number if name in present else None for name in per_doc}
            found.append(Discrepancy(f"CONTAINER_SET:{number}", "CONTAINER_SET", level, "containers", values))
        else:
            seals = {name: rows[number] for name, rows in per_doc.items() if rows[number]}
            if len(set(seals.values())) > 1:
                found.append(Discrepancy(f"SEAL:{number}", "SEAL", level, f"containers/{number}/seal_no", seals))
    return found


def _packages_discrepancy(docs: dict[str, dict]) -> list[Discrepancy]:
    values = {name: docs[name].get("total_packages") for name in ("MBL", "HBL", "PACKING_LIST")
              if name in docs and docs[name].get("total_packages") is not None}
    if len(set(values.values())) > 1:
        return [Discrepancy("PACKAGES", "PACKAGES", WARN, "total_packages", values)]
    return []


def _weight_discrepancy(docs: dict[str, dict], tolerance: float) -> list[Discrepancy]:
    sources = {"MBL": "gross_weight_kg", "HBL": "gross_weight_kg", "PACKING_LIST": "total_gross_weight_kg"}
    values = {name: _decimal(docs[name].get(key)) for name, key in sources.items() if name in docs}
    values = {name: value for name, value in values.items() if value is not None}
    for (_, a), (_, b) in combinations(values.items(), 2):
        biggest = max(a, b)
        if biggest > 0 and abs(a - b) / biggest > Decimal(str(tolerance)):
            return [Discrepancy("WEIGHT", "WEIGHT", WARN, "gross_weight_kg", {n: str(v) for n, v in values.items()})]
    return []


def _consignee_discrepancy(docs: dict[str, dict], threshold: float) -> list[Discrepancy]:
    if "HBL" not in docs or "INVOICE" not in docs:
        return []
    hbl, buyer = docs["HBL"], docs["INVOICE"].get("buyer")
    receiver = normalize_company(hbl.get("consignee"))
    shown = hbl.get("consignee")
    if receiver.startswith("TO ORDER"):
        receiver, shown = normalize_company(hbl.get("notify_party")), hbl.get("notify_party")
    if not receiver or not buyer:
        return []
    if token_set_ratio(receiver, normalize_company(buyer)) < threshold:
        return [Discrepancy("CONSIGNEE", "CONSIGNEE", WARN, "consignee", {"HBL": shown, "INVOICE": buyer})]
    return []


def crosscheck(approved_by_type: dict[str, dict], is_fcl: bool, weight_tolerance: float = 0.005,
               consignee_threshold: float = 0.85) -> CrosscheckResult:
    """`approved_by_type`: {loại chứng từ: approved_result}. Lô LCL bỏ MBL (MBL là của cả lô consol)."""
    docs = {name: doc for name, doc in approved_by_type.items() if is_fcl or name != "MBL"}
    if len(docs) < 2:
        return CrosscheckResult(INSUFFICIENT)
    level = BLOCK if is_fcl else WARN
    found = [*_container_discrepancies(docs, level), *_packages_discrepancy(docs),
             *_weight_discrepancy(docs, weight_tolerance), *_consignee_discrepancy(docs, consignee_threshold)]
    return CrosscheckResult(DISCREPANCY if found else MATCH, found)
