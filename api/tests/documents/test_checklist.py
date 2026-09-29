import pytest

from app.documents.checklist import checklist_items, missing_documents


def _missing(db, shipment, at_status=None):
    return set(missing_documents(db, shipment, at_status))


def test_created_requires_nothing(db, make_shipment):
    assert missing_documents(db, make_shipment()) == []


def test_in_transit_fcl_requires_mbl_hbl_invoice_packing_list(db, make_shipment):
    assert _missing(db, make_shipment(status="IN_TRANSIT")) == {"MBL", "HBL", "INVOICE", "PACKING_LIST"}


def test_in_transit_lcl_does_not_require_mbl(db, make_shipment):
    assert _missing(db, make_shipment(status="IN_TRANSIT", load_type="LCL")) == {"HBL", "INVOICE", "PACKING_LIST"}


def test_arrived_adds_arrival_notice(db, make_shipment):
    assert "ARRIVAL_NOTICE" in _missing(db, make_shipment(status="ARRIVED"))


def test_pre_arrival_customs_clearing_requires_arrival_notice(db, make_shipment):
    assert "ARRIVAL_NOTICE" in _missing(db, make_shipment(status="CUSTOMS_CLEARING"))


def test_origin_proof_only_when_claims_fta(db, make_shipment):
    assert "ORIGIN_PROOF" not in _missing(db, make_shipment(status="CUSTOMS_CLEARING"))
    assert "ORIGIN_PROOF" in _missing(db, make_shipment(status="CUSTOMS_CLEARING", claims_fta=True))


def test_cleared_requires_declaration_and_do(db, make_shipment):
    assert {"CUSTOMS_DECLARATION", "DO"} <= _missing(db, make_shipment(status="CLEARED"))


def test_at_status_looks_ahead_of_current_status(db, make_shipment):
    shipment = make_shipment(status="CUSTOMS_CLEARING")
    assert "DO" not in _missing(db, shipment) and "DO" in _missing(db, shipment, at_status="CLEARED")


def test_cancelled_requires_nothing(db, make_shipment):
    assert checklist_items(db, make_shipment(status="CANCELLED")) == []


def test_uploaded_document_removed_from_missing(db, make_shipment, make_document):
    shipment = make_shipment(status="IN_TRANSIT")
    make_document(shipment, "MBL")
    assert "MBL" not in _missing(db, shipment)


def test_only_active_document_counts(db, make_shipment, make_document):
    shipment = make_shipment(status="IN_TRANSIT")
    old, new = make_document(shipment, "HBL"), make_document(shipment, "HBL")
    old.superseded_by_id = new.id
    db.flush()
    assert "HBL" not in _missing(db, shipment)
    new.superseded_by_id = old.id  # mô phỏng cả hai đều đã bị thay thế
    db.flush()
    assert "HBL" in _missing(db, shipment)


@pytest.mark.parametrize("status", ["CLEARED", "AT_WAREHOUSE"])
def test_doc_checklist_endpoint_shape(client, login_as, make_shipment, status):
    login_as("DISPATCH")
    body = client.get(f"/api/shipments/{make_shipment(status=status).id}/doc-checklist").json()["data"]
    assert body["status"] == status and body["missing"]
    assert {"doc_type", "label", "present", "required_from_status"} <= body["items"][0].keys()
