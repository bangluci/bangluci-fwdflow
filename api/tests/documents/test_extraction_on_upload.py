from sqlalchemy import func, select

from app.ai.extraction.models import Extraction, ExtractionStatus
from app.ai.guard import check_user_rate
from app.audit.models import AuditLog
from app.config import get_settings
from app.documents.models import Document
from tests.documents import pdf_factory as factory


def _upload(client, shipment, doc_type="HBL", data=None):
    return client.post(f"/api/shipments/{shipment.id}/documents",
                       files={"file": ("a.pdf", data or factory.simple_pdf(), "application/pdf")},
                       data={"doc_type": doc_type})


def _count(db, model, **where):
    stmt = select(func.count()).select_from(model)
    for column, value in where.items():
        stmt = stmt.where(getattr(model, column) == value)
    return db.scalar(stmt)


def test_upload_hbl_creates_pending_extraction(client, db, login_as, make_shipment):
    login_as("DOCS")
    data = _upload(client, make_shipment()).json()["data"]
    extraction = db.get(Extraction, data["extraction_id"])
    assert (extraction.status, extraction.doc_type, extraction.document_id) == (ExtractionStatus.PENDING, "HBL",
                                                                                  data["id"])
    assert _count(db, AuditLog, entity="extraction", action="CREATE") == 1


def test_upload_do_creates_no_extraction(client, db, login_as, make_shipment):
    login_as("DOCS")
    data = _upload(client, make_shipment(), doc_type="DO").json()["data"]
    assert data["extraction_id"] is None and _count(db, Extraction) == 0


def test_duplicate_upload_creates_no_extraction(client, db, login_as, make_shipment):
    login_as("DOCS")
    shipment, pdf = make_shipment(), factory.simple_pdf()
    _upload(client, shipment, data=pdf)
    assert _upload(client, shipment, doc_type="INVOICE", data=pdf).status_code == 409
    assert _count(db, Extraction) == 1


def test_upload_rate_limited_returns_429_and_saves_nothing(client, db, login_as, make_shipment, files_dir):
    user = login_as("DOCS")
    for _ in range(30):
        check_user_rate(user, "extraction")
    res = _upload(client, make_shipment())
    assert res.status_code == 429 and res.json()["error"]["code"] == "RATE_LIMITED"
    assert _count(db, Document) == 0 and not files_dir.exists()


def test_rate_limit_does_not_apply_to_types_ai_does_not_read(client, db, login_as, make_shipment):
    user = login_as("DOCS")
    for _ in range(30):
        check_user_rate(user, "extraction")
    assert _upload(client, make_shipment(), doc_type="DO").status_code == 201


def test_upload_when_ai_disabled_still_saves_document(client, db, login_as, make_shipment, monkeypatch):
    login_as("DOCS")
    monkeypatch.setattr(get_settings(), "ai_external_enabled", False)
    data = _upload(client, make_shipment()).json()["data"]
    assert db.get(Extraction, data["extraction_id"]).status == ExtractionStatus.PENDING


def test_supersede_queues_extraction_for_new_version(client, db, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    old = _upload(client, shipment, data=factory.simple_pdf(1)).json()["data"]
    new = client.post(f"/api/documents/{old['id']}/supersede",
                      files={"file": ("b.pdf", factory.simple_pdf(2), "application/pdf")}).json()["data"]
    assert new["extraction_id"] != old["extraction_id"] and _count(db, Extraction) == 2


def test_cancel_shipment_cancels_pending_extractions(client, db, login_as, make_shipment, make_extraction):
    login_as("DOCS")
    shipment = make_shipment()
    pending = make_extraction(shipment=shipment)
    reviewing = make_extraction(shipment=shipment, status="REVIEW")
    res = client.post(f"/api/shipments/{shipment.id}/cancel", json={"reason": "Khách huỷ đơn"})
    assert res.status_code == 200
    assert (pending.status, reviewing.status) == (ExtractionStatus.CANCELLED, ExtractionStatus.REVIEW)
