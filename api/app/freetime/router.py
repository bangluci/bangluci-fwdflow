from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import require
from app.auth.models import User
from app.auth.scope import get_scoped_or_404
from app.db import get_db
from app.envelope import ok
from app.freetime import service
from app.freetime.schemas import (
    ContainerTypeName,
    FeeTypeName,
    LevelName,
    OverrideIn,
    RuleVersionIn,
    StatusName,
)
from app.shipments.models import Shipment

router = APIRouter(tags=["freetime"])
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[User, Depends(require("freetime.read"))]
Writer = Annotated[User, Depends(require("freetime.write"))]


@router.get("/freetime/rules")
def list_rules(db: Db, user: Reader, carrier_id: int | None = None, port_id: int | None = None,
               container_type: ContainerTypeName | None = None) -> dict:
    return ok(service.list_rule_versions(db, carrier_id, port_id, container_type))


@router.post("/freetime/rules", status_code=201)
def create_rules(body: RuleVersionIn, db: Db, user: Writer) -> dict:
    service.create_rule_version(db, body, user)
    db.commit()
    versions = service.list_rule_versions(db, body.carrier_id, body.port_id, body.container_type)
    return ok(next(v for v in versions if v["effective_from"] == body.effective_from))


@router.delete("/freetime/rules/{rule_id}")
def delete_rules(rule_id: int, db: Db, user: Writer) -> dict:
    service.delete_rule_version(db, rule_id, user)
    db.commit()
    return ok()


@router.get("/freetime/containers")
def list_containers(
    db: Db,
    user: Reader,
    level: Annotated[list[LevelName] | None, Query()] = None,
    status: Annotated[list[StatusName] | None, Query()] = None,
    fee_type: Annotated[list[FeeTypeName] | None, Query()] = None,
    shipment_id: int | None = None,
    customer_id: int | None = None,
    carrier_id: int | None = None,
    q: str | None = None,
    include_cancelled: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    filters = service.ClockFilters(list(level or []), list(status or []), list(fee_type or []), shipment_id,
                                   customer_id, carrier_id, q, include_cancelled, page, limit)
    rows, total = service.list_freetime_containers(db, filters)
    return ok(rows, meta={"total": total, "page": page, "limit": limit})


@router.get("/shipments/{shipment_id}/freetime-overrides")
def get_overrides(shipment_id: int, db: Db, user: Reader) -> dict:
    get_scoped_or_404(db, Shipment, shipment_id, user)
    return ok(service.list_overrides(db, shipment_id))


@router.put("/shipments/{shipment_id}/freetime-overrides")
def put_override(shipment_id: int, body: OverrideIn, db: Db, user: Writer) -> dict:
    row = service.put_override(db, shipment_id, body, user)
    db.commit()
    return ok({"fee_type": row.fee_type, "free_days": row.free_days, "source": row.source,
               "document_id": row.document_id, "updated_at": row.updated_at})


@router.delete("/shipments/{shipment_id}/freetime-overrides/{fee_type}")
def delete_override(shipment_id: int, fee_type: FeeTypeName, db: Db, user: Writer) -> dict:
    service.delete_override(db, shipment_id, fee_type, user)
    db.commit()
    return ok()
