"""Bản đồ trường trích xuất ↔ bảng nghiệp vụ, và giá trị hiện có của lô để màn duyệt so cũ / mới.

Chỉ vận đơn (MBL / HBL) và hoá đơn ghi vào bảng nghiệp vụ; packing list chỉ dùng để đối chiếu.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.extraction.models import Extraction
from app.catalog.models import Carrier, Port
from app.shipments.iso6346 import normalize_container_no
from app.shipments.models import Container, Shipment

FIELD_TARGETS = {
    "HBL": {"/bl_no": "shipments.hbl_no", "/carrier_name": "shipments.carrier_id", "/pol": "shipments.pol_port_id",
            "/pod": "shipments.pod_port_id", "/vessel": "shipments.vessel", "/voyage": "shipments.voyage",
            "/total_packages": "shipments.total_packages", "/containers/*": "containers"},
    "INVOICE": {"/lines/*": "shipment_items"},
    "PACKING_LIST": {},
}
FIELD_TARGETS["MBL"] = {**FIELD_TARGETS["HBL"], "/bl_no": "shipments.mbl_no"}


def resolve_carrier(db: Session, name: str | None) -> Carrier | None:
    """Khớp tên (hoặc mã) hãng tàu không phân biệt hoa thường; không khớp thì None."""
    if not name or not name.strip():
        return None
    key = name.strip().lower()
    return db.scalar(select(Carrier).where(func.lower(Carrier.name) == key).limit(1)) or \
        db.scalar(select(Carrier).where(func.lower(Carrier.code) == key).limit(1))


def resolve_port(db: Session, text: str | None) -> Port | None:
    """Khớp cảng theo mã UN/LOCODE, alias hoặc tên (không phân biệt hoa thường); không khớp thì None."""
    if not text or not text.strip():
        return None
    key = text.strip().upper()
    by_code = db.scalar(select(Port).where(Port.code == key).limit(1))
    if by_code is not None:
        return by_code
    by_alias = db.scalar(select(Port).where(Port.aliases.any(key)).limit(1))
    return by_alias or db.scalar(select(Port).where(func.upper(Port.name) == key).limit(1))


def _container_value(container: Container) -> dict[str, Any]:
    return {"container_no": container.container_no, "seal_no": container.seal_no,
            "container_type": container.container_type,
            "gross_weight_kg": None if container.gross_weight_kg is None else str(container.gross_weight_kg)}


def _bl_values(db: Session, extraction: Extraction, shipment: Shipment) -> dict[str, Any]:
    carrier = db.get(Carrier, shipment.carrier_id) if shipment.carrier_id else None
    ports = {p.id: p for p in db.scalars(select(Port).where(Port.id.in_(
        [i for i in (shipment.pol_port_id, shipment.pod_port_id) if i])))}
    bl_no = shipment.mbl_no if extraction.doc_type == "MBL" else shipment.hbl_no
    values: dict[str, Any] = {
        "/bl_no": bl_no, "/carrier_name": carrier.name if carrier else None,
        "/pol": ports[shipment.pol_port_id].code if shipment.pol_port_id else None,
        "/pod": ports[shipment.pod_port_id].code if shipment.pod_port_id else None,
        "/vessel": shipment.vessel, "/voyage": shipment.voyage, "/total_packages": shipment.total_packages,
    }
    if shipment.load_type == "FCL":
        rows = db.scalars(select(Container).where(Container.shipment_id == shipment.id))
        existing = {c.container_no: c for c in rows}
        for index, row in enumerate((extraction.result or {}).get("containers") or []):
            number = normalize_container_no(row.get("container_no") or "")
            values[f"/containers/{index}"] = _container_value(existing[number]) if number in existing else None
    return values


def current_values(db: Session, extraction: Extraction) -> dict[str, Any]:
    """Giá trị lô đang có theo cùng path với `result`; chưa có thì null. Hoá đơn luôn tạo dòng hàng mới."""
    shipment = db.get(Shipment, extraction.shipment_id)
    if extraction.doc_type in ("MBL", "HBL"):
        return _bl_values(db, extraction, shipment)
    return {}
