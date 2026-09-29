from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import require
from app.auth.models import User
from app.db import get_db
from app.envelope import ok
from app.trucking import queries, service
from app.trucking.schemas import AssignIn, CancelIn, OrderCreate, ReassignIn, RetimeIn, VoidIn
from app.trucking.state import TruckingStatus

router = APIRouter(tags=["trucking"])
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[User, Depends(require("transport.read"))]
Writer = Annotated[User, Depends(require("transport.write"))]
Voider = Annotated[User, Depends(require("transport.void_event"))]
Retimer = Annotated[User, Depends(require("container.retime_event"))]


@router.get("/trucking-orders")
def list_orders(db: Db, user: Reader, date_from: date | None = None, date_to: date | None = None,
                kind: Literal["PICKUP_FULL", "RETURN_EMPTY"] | None = None, status: TruckingStatus | None = None,
                shipment_id: int | None = None) -> dict:
    return ok(queries.list_orders(db, date_from, date_to, kind, status, shipment_id))


@router.get("/trucking-orders/{order_id}")
def get_order(order_id: int, db: Db, user: Reader) -> dict:
    return ok(queries.get_order(db, order_id))


@router.post("/trucking-orders", status_code=201)
def create_order(body: OrderCreate, db: Db, user: Writer) -> dict:
    order = service.create_order(db, user, body)
    db.commit()
    return ok(queries.get_order(db, order.id))


@router.post("/trucking-orders/{order_id}/assign")
def assign_order(order_id: int, body: AssignIn, db: Db, user: Writer) -> dict:
    service.assign_order(db, user, order_id, body.truck_id, body.driver_id)
    db.commit()
    return ok(queries.get_order(db, order_id))


@router.post("/trucking-orders/{order_id}/reassign")
def reassign_order(order_id: int, body: ReassignIn, db: Db, user: Writer) -> dict:
    service.reassign_order(db, user, order_id, body.truck_id, body.driver_id, body.reason)
    db.commit()
    return ok(queries.get_order(db, order_id))


@router.post("/trucking-orders/{order_id}/cancel")
def cancel_order(order_id: int, body: CancelIn, db: Db, user: Writer) -> dict:
    service.cancel_order(db, user, order_id, body.reason)
    db.commit()
    return ok(queries.get_order(db, order_id))


@router.post("/trucking-orders/{order_id}/events/{event_id}/void")
def void_event(order_id: int, event_id: int, body: VoidIn, db: Db, user: Voider) -> dict:
    service.void_trucking_event(db, user, order_id, event_id, body.reason)
    db.commit()
    return ok(queries.get_order(db, order_id))


@router.post("/trucking-orders/{order_id}/events/{event_id}/retime")
def retime_event(order_id: int, event_id: int, body: RetimeIn, db: Db, user: Retimer) -> dict:
    service.retime_trucking_event(db, user, order_id, event_id, body.occurred_at, body.reason)
    db.commit()
    return ok(queries.get_order(db, order_id))
