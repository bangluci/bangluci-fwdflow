from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.deps import require
from app.auth.models import User
from app.config import get_settings
from app.db import get_db
from app.envelope import AppError, ok
from app.lastmile import queries, service
from app.lastmile.label_pdf import render_label_pdf
from app.lastmile.models import LastMileOrder
from app.lastmile.schemas import AssignIn, ReasonIn, ReassignIn, SplitIn
from app.lastmile.state import LastMileStatus
from app.lastmile.tracking_code import normalize_code
from app.shipments.models import Shipment

router = APIRouter(tags=["last-mile"])
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[User, Depends(require("transport.read"))]
Manager = Annotated[User, Depends(require("transport.write"))]
Voider = Annotated[User, Depends(require("transport.void_event"))]


@router.get("/last-mile-orders")
def list_orders(db: Db, user: Reader, shipment_id: int | None = None, status: LastMileStatus | None = None,
                driver_id: int | None = None, planned_date: date | None = None, tracking_code: str | None = None
                ) -> dict:
    code = normalize_code(tracking_code) if tracking_code else None
    if tracking_code and code is None:
        return ok([])
    rows, meta = queries.list_orders(db, shipment_id, status, driver_id, planned_date, code)
    return ok(rows, meta=meta or None)


@router.get("/last-mile-orders/{order_id}")
def get_order(order_id: int, db: Db, user: Reader) -> dict:
    return ok(queries.get_order(db, order_id))


@router.post("/shipments/{shipment_id}/last-mile-orders", status_code=201)
def split_orders(shipment_id: int, body: SplitIn, db: Db, user: Manager) -> dict:
    made = service.create_orders(db, user, shipment_id, body.orders)
    db.commit()
    return ok([queries.get_order(db, order.id) for order in made])


@router.post("/last-mile-orders/{order_id}/assign")
def assign_order(order_id: int, body: AssignIn, db: Db, user: Manager) -> dict:
    service.assign_order(db, user, order_id, body.driver_id, body.planned_date)
    db.commit()
    return ok(queries.get_order(db, order_id))


@router.post("/last-mile-orders/{order_id}/reassign")
def reassign_order(order_id: int, body: ReassignIn, db: Db, user: Manager) -> dict:
    service.reassign_order(db, user, order_id, body.driver_id, body.planned_date, body.reason)
    db.commit()
    return ok(queries.get_order(db, order_id))


@router.post("/last-mile-orders/{order_id}/cancel")
def cancel_order(order_id: int, body: ReasonIn, db: Db, user: Manager) -> dict:
    service.cancel_order(db, user, order_id, body.reason)
    db.commit()
    return ok(queries.get_order(db, order_id))


@router.post("/last-mile-orders/{order_id}/return")
def return_order(order_id: int, body: ReasonIn, db: Db, user: Manager) -> dict:
    service.return_order(db, user, order_id, body.reason)
    db.commit()
    return ok(queries.get_order(db, order_id))


@router.post("/last-mile-orders/{order_id}/events/{event_id}/void")
def void_event(order_id: int, event_id: int, body: ReasonIn, db: Db, user: Voider) -> dict:
    service.void_event(db, user, order_id, event_id, body.reason)
    db.commit()
    return ok(queries.get_order(db, order_id))


@router.get("/last-mile-orders/{order_id}/label.pdf")
def label_pdf(order_id: int, db: Db, user: Manager) -> Response:
    order = db.get(LastMileOrder, order_id)
    if order is None:
        raise AppError("NOT_FOUND", "Không tìm thấy đơn giao", 404)
    pdf = render_label_pdf(order, db.get(Shipment, order.shipment_id).code, get_settings().public_base_url)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="nhan-{order.tracking_code}.pdf"',
                             "Cache-Control": "private, no-store"})
