"""Dòng hàng và tờ khai hải quan của lô. Hàm không commit; route commit sau khi audit cùng transaction."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import record_audit, snapshot
from app.auth.models import User
from app.envelope import AppError
from app.shipments.audit_fields import DECLARATION_FIELDS, ITEM_FIELDS
from app.shipments.models import CustomsDeclaration, ShipmentItem
from app.shipments.schemas import DeclarationIn, ItemIn
from app.shipments.service import get_open_shipment
from app.shipments.state import STATUS_RANK, ShipmentStatus
from app.shipments.validation import validate_patch

ITEM_INPUT_FIELDS = tuple(ItemIn.model_fields)
DECLARATION_INPUT_FIELDS = tuple(DeclarationIn.model_fields)


def _hs_source(hs_code: str | None) -> str | None:
    """Mã HS nhập tay luôn có nguồn `manual`; mã do AI chọn được ghi ở `hs.suggest` (`ai_accepted`)."""
    return "manual" if hs_code else None


def _get_item(db: Session, shipment_id: int, item_id: int) -> ShipmentItem:
    item = db.get(ShipmentItem, item_id)
    if item is None or item.shipment_id != shipment_id:
        raise AppError("NOT_FOUND", "Không tìm thấy dòng hàng", 404)
    return item


def add_item(db: Session, shipment_id: int, data: ItemIn, actor: User) -> ShipmentItem:
    get_open_shipment(db, shipment_id)
    line_no = (db.scalar(select(func.max(ShipmentItem.line_no)).where(ShipmentItem.shipment_id == shipment_id))
               or 0) + 1
    item = ShipmentItem(shipment_id=shipment_id, line_no=line_no, hs_source=_hs_source(data.hs_code),
                        **data.model_dump())
    db.add(item)
    db.flush()
    record_audit(db, actor.id, "CREATE", "shipment_item", item.id, after=snapshot(item, ITEM_FIELDS))
    return item


def update_item(db: Session, shipment_id: int, item_id: int, payload: dict, actor: User) -> ShipmentItem:
    get_open_shipment(db, shipment_id)
    item = _get_item(db, shipment_id, item_id)
    values = validate_patch(ItemIn, snapshot(item, ITEM_INPUT_FIELDS), payload)
    before = snapshot(item, ITEM_FIELDS)
    for key in payload.keys() & values.keys():
        setattr(item, key, values[key])
    if "hs_code" in payload:
        item.hs_source = _hs_source(item.hs_code)
    db.flush()
    record_audit(db, actor.id, "UPDATE", "shipment_item", item.id, before=before, after=snapshot(item, ITEM_FIELDS))
    return item


def delete_item(db: Session, shipment_id: int, item_id: int, actor: User) -> None:
    get_open_shipment(db, shipment_id)
    item = _get_item(db, shipment_id, item_id)
    before = snapshot(item, ITEM_FIELDS)
    db.delete(item)
    db.flush()
    record_audit(db, actor.id, "DELETE", "shipment_item", item_id, before=before)


def _get_declaration(db: Session, shipment_id: int, decl_id: int) -> CustomsDeclaration:
    decl = db.get(CustomsDeclaration, decl_id)
    if decl is None or decl.shipment_id != shipment_id:
        raise AppError("NOT_FOUND", "Không tìm thấy tờ khai", 404)
    return decl


def _open_for_declarations(db: Session, shipment_id: int) -> None:
    shipment = get_open_shipment(db, shipment_id)
    if STATUS_RANK[ShipmentStatus(shipment.status)] >= STATUS_RANK[ShipmentStatus.CLEARED]:
        raise AppError("DECLARATION_LOCKED", "Lô đã thông quan, không sửa tờ khai", 409)


def _assert_declaration_no_free(db: Session, declaration_no: str, except_id: int | None = None) -> None:
    stmt = select(CustomsDeclaration.id).where(CustomsDeclaration.declaration_no == declaration_no)
    existing = db.scalar(stmt)
    if existing is not None and existing != except_id:
        raise AppError("DUPLICATE_DECLARATION", "Số tờ khai đã tồn tại", 409)


def add_declaration(db: Session, shipment_id: int, data: DeclarationIn, actor: User) -> CustomsDeclaration:
    _open_for_declarations(db, shipment_id)
    _assert_declaration_no_free(db, data.declaration_no)
    decl = CustomsDeclaration(shipment_id=shipment_id, **data.model_dump())
    db.add(decl)
    db.flush()
    record_audit(db, actor.id, "CREATE", "customs_declaration", decl.id, after=snapshot(decl, DECLARATION_FIELDS))
    return decl


def update_declaration(db: Session, shipment_id: int, decl_id: int, payload: dict, actor: User) -> CustomsDeclaration:
    _open_for_declarations(db, shipment_id)
    decl = _get_declaration(db, shipment_id, decl_id)
    values = validate_patch(DeclarationIn, snapshot(decl, DECLARATION_INPUT_FIELDS), payload)
    _assert_declaration_no_free(db, values["declaration_no"], except_id=decl.id)
    before = snapshot(decl, DECLARATION_FIELDS)
    for key in payload.keys() & values.keys():
        setattr(decl, key, values[key])
    db.flush()
    record_audit(db, actor.id, "UPDATE", "customs_declaration", decl.id, before=before,
                 after=snapshot(decl, DECLARATION_FIELDS))
    return decl


def delete_declaration(db: Session, shipment_id: int, decl_id: int, actor: User) -> None:
    _open_for_declarations(db, shipment_id)
    decl = _get_declaration(db, shipment_id, decl_id)
    before = snapshot(decl, DECLARATION_FIELDS)
    db.delete(decl)
    db.flush()
    record_audit(db, actor.id, "DELETE", "customs_declaration", decl_id, before=before)
