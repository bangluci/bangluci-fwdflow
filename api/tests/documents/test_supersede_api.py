from sqlalchemy import select

from app.audit.models import AuditLog
from tests.documents import pdf_factory as factory


def _upload(client, shipment, data, doc_type="INVOICE"):
    return client.post(f"/api/shipments/{shipment.id}/documents", files={"file": ("a.pdf", data, "application/pdf")},
                       data={"doc_type": doc_type}).json()["data"]


def _supersede(client, document_id, data):
    return client.post(f"/api/documents/{document_id}/supersede", files={"file": ("b.pdf", data, "application/pdf")})


def test_supersede_links_old_to_new(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    old = _upload(client, shipment, factory.simple_pdf(1))
    new = _supersede(client, old["id"], factory.simple_pdf(2)).json()["data"]
    docs = {d["id"]: d for d in client.get(f"/api/shipments/{shipment.id}/documents").json()["data"]}
    assert docs[old["id"]]["superseded_by_id"] == new["id"] and docs[new["id"]]["superseded_by_id"] is None


def test_supersede_keeps_type(client, login_as, make_shipment):
    login_as("DOCS")
    old = _upload(client, make_shipment(), factory.simple_pdf(1), doc_type="PACKING_LIST")
    new = _supersede(client, old["id"], factory.simple_pdf(2)).json()["data"]
    assert new["doc_type"] == "PACKING_LIST" and new["visible_to_customer"] is True


def test_supersede_already_superseded_409(client, login_as, make_shipment):
    login_as("DOCS")
    old = _upload(client, make_shipment(), factory.simple_pdf(1))
    _supersede(client, old["id"], factory.simple_pdf(2))
    res = _supersede(client, old["id"], factory.simple_pdf(3))
    assert res.status_code == 409 and res.json()["error"]["code"] == "ALREADY_SUPERSEDED"


def test_supersede_duplicate_sha_409(client, login_as, make_shipment):
    login_as("DOCS")
    same = factory.simple_pdf(1)
    old = _upload(client, make_shipment(), same)
    res = _supersede(client, old["id"], same)
    assert res.status_code == 409 and res.json()["error"]["code"] == "DUPLICATE_FILE"


def test_list_active_only_hides_superseded(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    old = _upload(client, shipment, factory.simple_pdf(1))
    new = _supersede(client, old["id"], factory.simple_pdf(2)).json()["data"]
    url = f"/api/shipments/{shipment.id}/documents"
    active = client.get(url, params={"active_only": "true"}).json()["data"]
    assert [d["id"] for d in active] == [new["id"]]


def test_supersede_writes_audit_for_both(client, db, login_as, make_shipment):
    login_as("DOCS")
    old = _upload(client, make_shipment(), factory.simple_pdf(1))
    new = _supersede(client, old["id"], factory.simple_pdf(2)).json()["data"]
    rows = db.scalars(select(AuditLog).where(AuditLog.entity == "document")).all()
    assert {(r.action, r.entity_id) for r in rows} >= {("CREATE", str(new["id"])), ("UPDATE", str(old["id"]))}
