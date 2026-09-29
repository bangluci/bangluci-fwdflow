from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require
from app.auth.models import User
from app.db import get_db
from app.envelope import AppError, ok
from app.shipments import containers
from app.shipments.models import Container, ContainerEvent
from app.shipments.queries import container_detail
from app.shipments.schemas import ContainerEventIn, ContainerIn, DischargedIn, RetimeIn

router = APIRouter(tags=["containers"])
Db = Annotated[Session, Depends(get_db)]
Writer = Annotated[User, Depends(require("shipment.write"))]
Milestone = Annotated[User, Depends(require("container.milestone"))]


def _detail(db: Session, container: Container) -> dict:
    events = list(db.scalars(select(ContainerEvent).where(ContainerEvent.container_id == container.id)
                             .order_by(ContainerEvent.id)))
    return container_detail(container, events)


@router.post("/shipments/{shipment_id}/containers", status_code=201)
def add_container(shipment_id: int, body: ContainerIn, db: Db, user: Writer) -> dict:
    container = containers.add_container(db, shipment_id, body, user)
    db.commit()
    return ok(_detail(db, container))


@router.patch("/shipments/{shipment_id}/containers/{container_id}")
def update_container(shipment_id: int, container_id: int, payload: dict, db: Db, user: Writer) -> dict:
    container = containers.update_container(db, shipment_id, container_id, payload, user)
    db.commit()
    return ok(_detail(db, container))


@router.delete("/shipments/{shipment_id}/containers/{container_id}")
def delete_container(shipment_id: int, container_id: int, db: Db, user: Writer) -> dict:
    containers.delete_container(db, shipment_id, container_id, user)
    db.commit()
    return ok()


@router.post("/containers/{container_id}/events", status_code=201)
def add_event(container_id: int, body: ContainerEventIn, db: Db, user: Milestone) -> dict:
    """Chỉ DISCHARGED và RETIME qua API; GATE_OUT_FULL / EMPTY_RETURNED do thao tác tài xế ghi."""
    if isinstance(body, DischargedIn):
        containers.add_container_event(db, container_id, body.kind, body.occurred_at, user)
    elif isinstance(body, RetimeIn):
        containers.retime_container_event(db, container_id, body.adjusts_event_id, body.occurred_at, body.reason, user)
    else:  # pragma: no cover - discriminator đã loại các kind khác
        raise AppError("VALIDATION_ERROR", "Loại sự kiện không hợp lệ", 422)
    db.commit()
    container = db.get(Container, container_id)
    return ok(_detail(db, container))
