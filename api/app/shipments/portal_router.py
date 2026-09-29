"""Cổng khách hàng: khách chỉ đọc lô của mình, chỉ các trường được phép, chứng từ đánh dấu cho khách xem."""

import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require
from app.auth.models import User
from app.auth.scope import get_scoped_or_404, scope_shipments
from app.catalog.models import Port
from app.db import get_db
from app.documents.models import Document
from app.documents.storage import path_for
from app.envelope import AppError, ok
from app.events import effective_events
from app.shipments.models import Container, Shipment, ShipmentEvent

router = APIRouter(prefix="/portal", tags=["portal"])
Db = Annotated[Session, Depends(get_db)]
Customer = Annotated[User, Depends(require("portal.read"))]
LIST_FIELDS = ("code", "load_type", "status", "hbl_no", "vessel", "voyage", "etd", "eta", "total_packages")


def _summary(shipment: Shipment, ports: dict[int, Port]) -> dict:
    pol, pod = ports.get(shipment.pol_port_id), ports.get(shipment.pod_port_id)
    return {"id": shipment.id, **{f: getattr(shipment, f) for f in LIST_FIELDS},
            "pol": pol.code if pol else None, "pod": pod.code if pod else None}


def _ports(db: Session, shipments: list[Shipment]) -> dict[int, Port]:
    ids = {p for s in shipments for p in (s.pol_port_id, s.pod_port_id) if p}
    return {p.id: p for p in db.scalars(select(Port).where(Port.id.in_(ids)))} if ids else {}


@router.get("/shipments")
def list_shipments(db: Db, user: Customer) -> dict:
    shipments = list(db.scalars(scope_shipments(select(Shipment), user).order_by(
        Shipment.eta.desc().nulls_last(), Shipment.id.desc())))
    ports = _ports(db, shipments)
    return ok([_summary(s, ports) for s in shipments])


@router.get("/shipments/{shipment_id}")
def get_shipment(shipment_id: int, db: Db, user: Customer) -> dict:
    shipment = get_scoped_or_404(db, Shipment, shipment_id, user)
    containers = db.scalars(select(Container).where(Container.shipment_id == shipment.id).order_by(Container.id))
    events = db.scalars(select(ShipmentEvent).where(ShipmentEvent.shipment_id == shipment.id)).all()
    to_status = {e.id: e.to_status for e in events}
    documents = db.scalars(select(Document).where(
        Document.shipment_id == shipment.id, Document.visible_to_customer.is_(True),
        Document.superseded_by_id.is_(None)).order_by(Document.uploaded_at, Document.id))
    return ok({
        **_summary(shipment, _ports(db, [shipment])),
        "containers": [{"container_no": c.container_no, "container_type": c.container_type} for c in containers],
        "timeline": [{"status": to_status[e.id], "occurred_at": e.occurred_at}
                     for e in effective_events(events) if e.kind == "TRANSITION"],
        "documents": [{"id": d.id, "doc_type": d.doc_type, "created_at": d.uploaded_at} for d in documents]})


@router.get("/documents/{document_id}/file")
def download_document(document_id: int, db: Db, user: Customer) -> FileResponse:
    document = db.get(Document, document_id)
    if document is None or not document.visible_to_customer or document.superseded_by_id is not None:
        raise AppError("NOT_FOUND", "Không tìm thấy chứng từ", 404)
    get_scoped_or_404(db, Shipment, document.shipment_id, user)
    path = path_for(document.file_sha256)
    if not path.is_file():
        raise AppError("NOT_FOUND", "Không tìm thấy chứng từ", 404)
    extension = mimetypes.guess_extension(document.mime) or ""
    extension = ".jpg" if extension == ".jpe" else extension
    return FileResponse(path, media_type=document.mime, filename=f"{document.doc_type}-{document.id}{extension}",
                        content_disposition_type="attachment",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
