"""Ghi kết quả AI đã duyệt vào lô: chỉ trường người duyệt chọn (hoặc chỗ đang trống), audit kèm nguồn AI.

Mỗi thực thể bị ghi có `after._source = {path: "ai_accepted" | "ai_edited"}` để truy được trường nào do AI, trường nào
do người sửa.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.extraction.models import Extraction
from app.ai.extraction.targets import resolve_carrier, resolve_port
from app.audit.service import record_audit, snapshot
from app.auth.models import User
from app.shipments.audit_fields import CONTAINER_FIELDS, ITEM_FIELDS, SHIPMENT_FIELDS
from app.shipments.iso6346 import normalize_container_no
from app.shipments.models import Container, Shipment, ShipmentItem

NO_DECIMAL_CURRENCIES = frozenset({"VND", "JPY", "KRW"})
NUMERIC_KEYS = frozenset({"gross_weight_kg", "net_weight_kg", "total_gross_weight_kg", "total_net_weight_kg",
                          "quantity", "unit_price", "amount", "total_amount", "packages", "total_packages"})
CONTAINER_KEYS = ("container_no", "seal_no", "container_type", "gross_weight_kg")


class FieldChoice(BaseModel):
    value: Any = None
    use: Literal["old", "new"] | None = None


@dataclass
class Outcome:
    skipped: list[dict[str, str]] = field(default_factory=list)
    shipment_sources: dict[str, str] = field(default_factory=dict)
    children_written: bool = False


def leaves(data: Any, prefix: str = "") -> dict[str, Any]:
    """Phẳng hoá JSON thành {đường dẫn kiểu JSON pointer: giá trị lá}."""
    if isinstance(data, dict):
        return {path: value for key, item in data.items() for path, value in leaves(item, f"{prefix}/{key}").items()}
    if isinstance(data, list):
        return {path: value for i, item in enumerate(data) for path, value in leaves(item, f"{prefix}/{i}").items()}
    return {prefix: data}


def same(path: str, a: Any, b: Any) -> bool:
    """So hai giá trị lá; trường số so theo giá trị (100 = 100.00), còn lại so nguyên văn."""
    if a is None or b is None:
        return a is b
    if path.rsplit("/", 1)[-1] in NUMERIC_KEYS:
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except InvalidOperation:
            return False
    return a == b


def edited_paths(original: dict, final: dict) -> set[str]:
    before, after = leaves(original), leaves(final)
    return {path for path in before.keys() | after.keys() if not same(path, before.get(path), after.get(path))}


def _decimal(value: Any) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


def to_minor_units(amount: Decimal, currency: str) -> int:
    """VND / JPY / KRW nguyên đơn vị, các tiền tệ khác theo phần trăm (cent), làm tròn half-up."""
    scale = Decimal(1) if currency.upper() in NO_DECIMAL_CURRENCIES else Decimal(100)
    return int((amount * scale).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _source(paths: list[str], edited: set[str]) -> dict[str, str]:
    return {path: "ai_edited" if path in edited else "ai_accepted" for path in paths}


def _should_write(choice: FieldChoice | None, has_current: bool) -> bool:
    """`use=new` luôn ghi, `use=old` không ghi; không chọn thì chỉ điền chỗ đang trống."""
    if choice is not None and choice.use is not None:
        return choice.use == "new"
    return not has_current


def _write_scalar(shipment: Shipment, attr: str, path: str, new: Any, choice: FieldChoice | None, edited: set[str],
                  out: Outcome) -> None:
    current = getattr(shipment, attr)
    if new is None or not _should_write(choice, current is not None) or new == current:
        return
    setattr(shipment, attr, new)
    out.shipment_sources[path] = "ai_edited" if path in edited else "ai_accepted"


def _apply_shipment_fields(db: Session, shipment: Shipment, doc_type: str, final: dict, fields: dict,
                           edited: set[str], out: Outcome) -> None:
    text_targets = {"/bl_no": ("mbl_no" if doc_type == "MBL" else "hbl_no", 35), "/vessel": ("vessel", 100),
                    "/voyage": ("voyage", 100)}
    for path, (attr, limit) in text_targets.items():
        raw = final.get(path[1:])
        value = raw.strip()[:limit] if isinstance(raw, str) and raw.strip() else None
        _write_scalar(shipment, attr, path, value.upper() if path == "/bl_no" and value else value,
                      fields.get(path), edited, out)
    _write_scalar(shipment, "total_packages", "/total_packages", final.get("total_packages"),
                  fields.get("/total_packages"), edited, out)
    references = (("/carrier_name", "carrier_id", resolve_carrier, "hãng tàu"),
                  ("/pol", "pol_port_id", resolve_port, "cảng"), ("/pod", "pod_port_id", resolve_port, "cảng"))
    for path, attr, resolver, label in references:
        text = final.get(path[1:])
        if text is None:
            continue
        ref = resolver(db, text)
        if ref is None:
            out.skipped.append({"path": path, "reason": f"Không tìm thấy {label} '{text}' trong danh mục"})
            continue
        _write_scalar(shipment, attr, path, ref.id, fields.get(path), edited, out)


def _apply_containers(db: Session, shipment: Shipment, final: dict, fields: dict, edited: set[str], actor: User,
                      out: Outcome) -> None:
    rows = final.get("containers") or []
    if shipment.load_type != "FCL":
        if rows:
            out.skipped.append({"path": "/containers", "reason": "Lô LCL không có container"})
        return
    existing = {c.container_no: c for c in db.scalars(select(Container).where(Container.shipment_id == shipment.id))}
    for index, row in enumerate(rows):
        path, number = f"/containers/{index}", normalize_container_no(row.get("container_no") or "")
        current = existing.get(number)
        if not number or not _should_write(fields.get(path), current is not None):
            continue
        if row.get("container_type") is None:
            out.skipped.append({"path": path, "reason": "Chưa xác định loại container"})
            continue
        values = {"container_type": row["container_type"], "seal_no": row.get("seal_no"),
                  "gross_weight_kg": _decimal(row.get("gross_weight_kg"))}
        sources = _source([f"{path}/{key}" for key in CONTAINER_KEYS], edited)
        if current is None:
            container = Container(shipment_id=shipment.id, container_no=number, **values)
            db.add(container)
            db.flush()
            record_audit(db, actor.id, "CREATE", "container", container.id,
                         after={**snapshot(container, CONTAINER_FIELDS), "_source": sources})
        else:
            before = snapshot(current, CONTAINER_FIELDS)
            for key, value in values.items():
                setattr(current, key, value)
            db.flush()
            record_audit(db, actor.id, "UPDATE", "container", current.id, before=before,
                         after={**snapshot(current, CONTAINER_FIELDS), "_source": sources})
        out.children_written = True


def _apply_invoice_lines(db: Session, shipment: Shipment, final: dict, fields: dict, edited: set[str], actor: User,
                         out: Outcome) -> None:
    currency = (final.get("currency") or "").strip().upper() or None
    next_line = (db.scalar(select(func.max(ShipmentItem.line_no)).where(ShipmentItem.shipment_id == shipment.id))
                 or 0) + 1
    for index, line in enumerate(final.get("lines") or []):
        path, choice = f"/lines/{index}", fields.get(f"/lines/{index}")
        if choice is not None and choice.use == "old":
            continue
        quantity, description = _decimal(line.get("quantity")), (line.get("description") or "").strip()
        if not description or quantity is None or quantity <= 0:
            out.skipped.append({"path": path, "reason": "Dòng thiếu mô tả hoặc số lượng"})
            continue
        amount = _decimal(line.get("amount"))
        value_amount = to_minor_units(amount, currency) if amount is not None and currency else None
        item = ShipmentItem(shipment_id=shipment.id, line_no=next_line, description=description[:500],
                            quantity=quantity, unit=line.get("unit"), value_amount=value_amount,
                            value_currency=currency if value_amount is not None else None)
        db.add(item)
        db.flush()
        sources = _source([f"{path}/{key}" for key in ("description", "quantity", "unit", "amount")], edited)
        record_audit(db, actor.id, "CREATE", "shipment_item", item.id,
                     after={**snapshot(item, ITEM_FIELDS), "_source": sources})
        next_line += 1
        out.children_written = True


def apply_extraction(db: Session, extraction: Extraction, final: dict, fields: dict[str, FieldChoice],
                     edited: set[str], actor: User) -> list[dict[str, str]]:
    """Ghi vào lô (caller đã `lock_shipment`); trả về các trường bị bỏ qua kèm lý do."""
    shipment = db.get(Shipment, extraction.shipment_id)
    before = snapshot(shipment, SHIPMENT_FIELDS)
    out = Outcome()
    if extraction.doc_type in ("MBL", "HBL"):
        _apply_shipment_fields(db, shipment, extraction.doc_type, final, fields, edited, out)
        _apply_containers(db, shipment, final, fields, edited, actor, out)
    elif extraction.doc_type == "INVOICE":
        _apply_invoice_lines(db, shipment, final, fields, edited, actor, out)
    if out.shipment_sources or out.children_written:
        shipment.version += 1
        db.flush()
        record_audit(db, actor.id, "UPDATE", "shipment", shipment.id, before=before,
                     after={**snapshot(shipment, SHIPMENT_FIELDS), "_source": out.shipment_sources})
    return out.skipped
