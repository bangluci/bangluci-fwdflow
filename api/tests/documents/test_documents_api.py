import hashlib

import pytest
from sqlalchemy import func, select

from app.audit.models import AuditLog
from app.documents.models import DEFAULT_VISIBLE_TYPES, DocType, Document
from app.documents.service import clean_filename
from app.documents.storage import path_for
from tests.documents import pdf_factory as factory

PDF = factory.simple_pdf()


def _upload(client, shipment, data=PDF, doc_type="INVOICE", name="hoa-don.pdf", **form):
    return client.post(f"/api/shipments/{shipment.id}/documents", files={"file": (name, data, "application/pdf")},
                       data={"doc_type": doc_type, **form})


def test_upload_pdf_returns_sha256_pages_mime(client, login_as, make_shipment):
    login_as("DOCS")
    res = _upload(client, make_shipment(), factory.simple_pdf(3))
    data = res.json()["data"]
    assert res.status_code == 201
    assert (data["mime"], data["pages"], data["doc_type"]) == ("application/pdf", 3, "INVOICE")
    assert path_for(data["file_sha256"]).stat().st_size == data["size_bytes"]


def test_upload_same_file_other_shipment_ok(client, login_as, make_shipment):
    login_as("DOCS")
    assert _upload(client, make_shipment()).status_code == 201
    assert _upload(client, make_shipment()).status_code == 201


def test_upload_same_type_keep_both_ok(client, db, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    _upload(client, shipment, factory.simple_pdf(1))
    assert _upload(client, shipment, factory.simple_pdf(2), keep_both="true").status_code == 201
    assert db.scalar(select(func.count()).select_from(Document).where(Document.shipment_id == shipment.id)) == 2


def test_upload_duplicate_same_shipment_409(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    _upload(client, shipment)
    res = _upload(client, shipment, doc_type="PACKING_LIST", keep_both="true")
    assert res.status_code == 409 and res.json()["error"]["code"] == "DUPLICATE_FILE"


def test_upload_same_type_409_same_type_exists(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    _upload(client, shipment, factory.simple_pdf(1))
    res = _upload(client, shipment, factory.simple_pdf(2))
    assert res.status_code == 409 and res.json()["error"]["code"] == "SAME_TYPE_EXISTS"


def test_upload_cancelled_shipment_409(client, login_as, make_shipment):
    login_as("DOCS")
    res = _upload(client, make_shipment(status="CANCELLED"))
    assert res.status_code == 409 and res.json()["error"]["code"] == "SHIPMENT_CLOSED"


@pytest.mark.parametrize(("data", "code"), [
    (b"MZ\x90\x00 chuong trinh", "UNSUPPORTED_FILE_TYPE"),
    (factory.encrypted_pdf(), "PDF_ENCRYPTED"),
    (factory.javascript_pdf(), "PDF_ACTIVE_CONTENT"),
    (factory.simple_pdf(21), "PDF_TOO_MANY_PAGES"),
    (factory.png_bytes((8001, 10)), "IMAGE_TOO_LARGE"),
], ids=["exe", "encrypted", "javascript", "21-pages", "8001px"])
def test_upload_rejected_files_400(client, login_as, make_shipment, data, code):
    login_as("DOCS")
    res = _upload(client, make_shipment(), data)
    assert res.status_code == 400 and res.json()["error"]["code"] == code and res.json()["error"]["message"]


def test_upload_audit_failure_prevents_commit(client, db, login_as, make_shipment, monkeypatch):
    login_as("DOCS")
    shipment = make_shipment()
    commits = []
    monkeypatch.setattr(db, "commit", lambda: commits.append(1))

    def boom(*args, **kwargs):
        raise RuntimeError("audit lỗi")

    monkeypatch.setattr("app.documents.service.record_audit", boom)
    with pytest.raises(RuntimeError):
        _upload(client, shipment)
    assert commits == []


def test_upload_writes_audit(client, db, login_as, make_shipment):
    login_as("DOCS")
    _upload(client, make_shipment())
    row = db.scalar(select(AuditLog).where(AuditLog.entity == "document", AuditLog.action == "CREATE"))
    assert row.after["doc_type"] == "INVOICE"


def test_original_name_keeps_only_base_name(client, login_as, make_shipment):
    login_as("DOCS")
    data = _upload(client, make_shipment(), name="..\\..\\thu-muc\\hoadon.pdf").json()["data"]
    assert data["original_name"] == "hoadon.pdf"


def test_clean_filename_drops_control_chars_and_caps_length():
    assert clean_filename("a/b\\hoa\x01\x7fdon.pdf") == "hoadon.pdf"
    assert clean_filename("x" * 300) == "x" * 200
    assert clean_filename("  ") is None and clean_filename(None) is None


@pytest.mark.parametrize("doc_type", [t.value for t in DocType])
def test_default_visible_to_customer_by_type(client, login_as, make_shipment, doc_type):
    login_as("DOCS")
    data = _upload(client, make_shipment(), doc_type=doc_type).json()["data"]
    assert data["visible_to_customer"] is (DocType(doc_type) in DEFAULT_VISIBLE_TYPES)


def test_download_content_type_from_db_and_nosniff(client, login_as, make_shipment):
    login_as("DOCS")
    doc = _upload(client, make_shipment()).json()["data"]
    res = client.get(f"/api/documents/{doc['id']}/file")
    assert res.status_code == 200 and res.content == PDF
    assert hashlib.sha256(res.content).hexdigest() == doc["file_sha256"]
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["cache-control"] == "private, no-store"
    assert res.headers["content-disposition"].startswith("inline")


def test_download_missing_file_404(client, login_as, make_shipment, make_document):
    login_as("DOCS")
    document = make_document(make_shipment())
    assert client.get(f"/api/documents/{document.id}/file").status_code == 404


def test_list_documents_newest_first_and_active_only(client, login_as, make_shipment, make_document, db):
    login_as("DOCS")
    shipment = make_shipment()
    old, new = make_document(shipment, "INVOICE"), make_document(shipment, "INVOICE")
    old.superseded_by_id = new.id
    db.flush()
    url = f"/api/shipments/{shipment.id}/documents"
    ids = [d["id"] for d in client.get(url).json()["data"]]
    active = [d["id"] for d in client.get(url, params={"active_only": "true"}).json()["data"]]
    assert ids == [new.id, old.id] and active == [new.id]


def test_dispatch_upload_403(client, login_as, make_shipment):
    login_as("DISPATCH")
    assert _upload(client, make_shipment()).status_code == 403


def test_customer_role_cannot_use_internal_document_endpoints(client, login_as, make_shipment, make_document):
    login_as("CUSTOMER")
    document = make_document(make_shipment())
    assert client.get(f"/api/documents/{document.id}/file").status_code == 403
    assert client.get(f"/api/shipments/{document.shipment_id}/documents").status_code == 403
