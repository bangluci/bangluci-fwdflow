from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import require
from app.auth.models import User
from app.auth.scope import get_scoped_or_404
from app.db import get_db
from app.envelope import ok
from app.shipments import lines, service
from app.shipments.audit_fields import DECLARATION_FIELDS, ITEM_FIELDS
from app.shipments.models import Shipment
from app.shipments.queries import ShipmentFilters, list_shipments, shipment_detail
from app.shipments.schemas import (
    CancelIn,
    DeclarationIn,
    ItemIn,
    ShipmentCreate,
    ShipmentUpdate,
    TransitionIn,
)

router = APIRouter(tags=["shipments"])
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[User, Depends(require("shipment.read"))]
Writer = Annotated[User, Depends(require("shipment.write"))]


def _row(obj, fields: tuple[str, ...]) -> dict:
    return {"id": obj.id, **{f: getattr(obj, f) for f in fields}}


@router.post("/shipments", status_code=201)
def create_shipment(body: ShipmentCreate, db: Db, user: Writer) -> dict:
    shipment = service.create_shipment(db, body, user)
    db.commit()
    return ok(shipment_detail(db, shipment))


@router.get("/shipments")
def search_shipments(
    db: Db,
    user: Reader,
    q: str | None = None,
    status: Annotated[list[str] | None, Query()] = None,
    customer_id: int | None = None,
    carrier_id: int | None = None,
    eta_from: date | None = None,
    eta_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    filters = ShipmentFilters(q, status or [], customer_id, carrier_id, eta_from, eta_to, page, limit)
    rows, total = list_shipments(db, user, filters)
    return ok(rows, meta={"total": total, "page": page, "limit": limit})


@router.get("/shipments/{shipment_id}")
def get_shipment(shipment_id: int, db: Db, user: Reader) -> dict:
    return ok(shipment_detail(db, get_scoped_or_404(db, Shipment, shipment_id, user)))


@router.patch("/shipments/{shipment_id}")
def update_shipment(shipment_id: int, body: ShipmentUpdate, db: Db, user: Writer) -> dict:
    shipment = service.update_shipment(db, shipment_id, body, user)
    db.commit()
    return ok(shipment_detail(db, shipment))


@router.post("/shipments/{shipment_id}/transition")
def transition_shipment(shipment_id: int, body: TransitionIn, db: Db, user: Writer) -> dict:
    shipment = service.transition_shipment(db, shipment_id, body.to_status, user)
    db.commit()
    return ok(shipment_detail(db, shipment))


@router.post("/shipments/{shipment_id}/cancel")
def cancel_shipment(shipment_id: int, body: CancelIn, db: Db, user: Writer) -> dict:
    shipment = service.cancel_shipment(db, shipment_id, body.reason, user)
    db.commit()
    return ok(shipment_detail(db, shipment))


@router.post("/shipments/{shipment_id}/items", status_code=201)
def add_item(shipment_id: int, body: ItemIn, db: Db, user: Writer) -> dict:
    item = lines.add_item(db, shipment_id, body, user)
    db.commit()
    return ok(_row(item, ITEM_FIELDS))


@router.patch("/shipments/{shipment_id}/items/{item_id}")
def update_item(shipment_id: int, item_id: int, payload: dict, db: Db, user: Writer) -> dict:
    item = lines.update_item(db, shipment_id, item_id, payload, user)
    db.commit()
    return ok(_row(item, ITEM_FIELDS))


@router.delete("/shipments/{shipment_id}/items/{item_id}")
def delete_item(shipment_id: int, item_id: int, db: Db, user: Writer) -> dict:
    lines.delete_item(db, shipment_id, item_id, user)
    db.commit()
    return ok()


@router.post("/shipments/{shipment_id}/customs-declarations", status_code=201)
def add_declaration(shipment_id: int, body: DeclarationIn, db: Db, user: Writer) -> dict:
    decl = lines.add_declaration(db, shipment_id, body, user)
    db.commit()
    return ok(_row(decl, DECLARATION_FIELDS))


@router.patch("/shipments/{shipment_id}/customs-declarations/{decl_id}")
def update_declaration(shipment_id: int, decl_id: int, payload: dict, db: Db, user: Writer) -> dict:
    decl = lines.update_declaration(db, shipment_id, decl_id, payload, user)
    db.commit()
    return ok(_row(decl, DECLARATION_FIELDS))


@router.delete("/shipments/{shipment_id}/customs-declarations/{decl_id}")
def delete_declaration(shipment_id: int, decl_id: int, db: Db, user: Writer) -> dict:
    lines.delete_declaration(db, shipment_id, decl_id, user)
    db.commit()
    return ok()

