from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy import String, cast, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.audit.service import record_audit, register_audit_fields, snapshot
from app.auth.deps import current_user
from app.auth.models import User
from app.auth.permissions import can
from app.catalog import schemas
from app.catalog.models import Carrier, Customer, Driver, Port, Truck, Trucker, Warehouse
from app.db import get_db
from app.envelope import AppError, ok
from app.ratelimit import client_ip

router = APIRouter()


@dataclass(frozen=True)
class Kind:
    model: type
    schema: type[BaseModel]
    write_action: str
    search: tuple[str, ...]


KINDS: dict[str, Kind] = {
    "customers": Kind(Customer, schemas.CustomerIn, "catalog.commercial.write", ("name", "tax_code", "email")),
    "carriers": Kind(Carrier, schemas.CarrierIn, "catalog.commercial.write", ("code", "name")),
    "ports": Kind(Port, schemas.PortIn, "catalog.commercial.write", ("code", "name")),
    "warehouses": Kind(Warehouse, schemas.WarehouseIn, "catalog.transport.write", ("name", "address")),
    "truckers": Kind(Trucker, schemas.TruckerIn, "catalog.transport.write", ("name", "phone")),
    "trucks": Kind(Truck, schemas.TruckIn, "catalog.transport.write", ("plate_no",)),
    "drivers": Kind(Driver, schemas.DriverIn, "catalog.transport.write", ("full_name", "phone")),
}
for _name, _kind in KINDS.items():
    register_audit_fields(_name, _kind.schema.model_fields.keys())


def _kind(kind: str) -> Kind:
    if kind not in KINDS:
        raise AppError("NOT_FOUND", "Loại danh mục không tồn tại", 404)
    return KINDS[kind]


def _fields(k: Kind) -> list[str]:
    return list(k.schema.model_fields.keys())


def _out(k: Kind, obj) -> dict:
    return {"id": obj.id, **snapshot(obj, _fields(k))}


def _authorize(user: User, action: str) -> None:
    if not can(user.role, action):
        raise AppError("FORBIDDEN", "Bạn không có quyền thực hiện thao tác này", 403)


def _validate(k: Kind, data: dict) -> dict:
    try:
        return k.schema.model_validate(data).model_dump()
    except ValidationError as exc:
        details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        raise AppError("VALIDATION_ERROR", "Dữ liệu danh mục không hợp lệ", 422, details) from exc


@router.get("/catalog/{kind}")
def list_items(kind: str, q: str | None = None, active: bool | None = None,
               db: DbSession = Depends(get_db), user: User = Depends(current_user)) -> dict:
    _authorize(user, "catalog.read")
    k = _kind(kind)
    stmt = select(k.model).order_by(k.model.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(*[cast(getattr(k.model, c), String).ilike(like) for c in k.search]))
    if active is not None:
        stmt = stmt.where(k.model.active.is_(active))
    return ok([_out(k, o) for o in db.scalars(stmt.limit(500))])


def _commit_or_conflict(db: DbSession, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("CONFLICT", message, 409) from exc


@router.post("/catalog/{kind}", status_code=201)
def create_item(kind: str, payload: dict, request: Request, db: DbSession = Depends(get_db),
                user: User = Depends(current_user)) -> dict:
    k = _kind(kind)
    _authorize(user, k.write_action)
    obj = k.model(**_validate(k, payload))
    db.add(obj)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("CONFLICT", "Trùng mã hoặc liên kết không hợp lệ", 409) from exc
    record_audit(db, user.id, "CREATE", kind, obj.id, after=snapshot(obj, _fields(k)), ip=client_ip(request))
    _commit_or_conflict(db, "Trùng mã hoặc liên kết không hợp lệ")
    return ok(_out(k, obj))


@router.patch("/catalog/{kind}/{item_id}")
def update_item(kind: str, item_id: int, payload: dict, request: Request, db: DbSession = Depends(get_db),
                user: User = Depends(current_user)) -> dict:
    k = _kind(kind)
    _authorize(user, k.write_action)
    obj = db.get(k.model, item_id)
    if obj is None:
        raise AppError("NOT_FOUND", "Không tìm thấy bản ghi", 404)
    before = snapshot(obj, _fields(k))
    data = _validate(k, {**before, **payload})
    for key in payload.keys() & data.keys():
        setattr(obj, key, data[key])
    record_audit(db, user.id, "UPDATE", kind, obj.id, before=before, after=snapshot(obj, _fields(k)),
                 ip=client_ip(request))
    _commit_or_conflict(db, "Trùng mã hoặc liên kết không hợp lệ")
    return ok(_out(k, obj))


@router.delete("/catalog/{kind}/{item_id}")
def delete_item(kind: str, item_id: int, request: Request, db: DbSession = Depends(get_db),
                user: User = Depends(current_user)) -> dict:
    k = _kind(kind)
    _authorize(user, k.write_action)
    obj = db.get(k.model, item_id)
    if obj is None:
        raise AppError("NOT_FOUND", "Không tìm thấy bản ghi", 404)
    before = snapshot(obj, _fields(k))
    db.delete(obj)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("IN_USE", "Bản ghi đang được sử dụng, chỉ có thể ngừng dùng", 409) from exc
    record_audit(db, user.id, "DELETE", kind, item_id, before=before, ip=client_ip(request))
    db.commit()
    return ok()
