import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.documents.models import DEFAULT_VISIBLE_TYPES, DocType, Document, RequiredDocRule


def test_required_doc_rules_seeded_15_rows(db):
    assert db.scalar(select(func.count()).select_from(RequiredDocRule)) == 15


def test_document_unique_sha_per_shipment(db, make_shipment, make_document):
    shipment = make_shipment()
    first = make_document(shipment)
    db.add(Document(shipment_id=shipment.id, doc_type="INVOICE", file_sha256=first.file_sha256, mime="application/pdf",
                    size_bytes=1, pages=1, visible_to_customer=True, uploaded_by=first.uploaded_by))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_required_doc_rule_unique_nulls_not_distinct(db):
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO required_doc_rules (load_type, claims_fta, doc_type, required_from_status) "
                        "VALUES ('FCL', NULL, 'HBL', 'CLEARED')"))
    db.rollback()


def test_default_visible_types():
    assert DEFAULT_VISIBLE_TYPES == {DocType.HBL, DocType.INVOICE, DocType.PACKING_LIST, DocType.CUSTOMS_DECLARATION,
                                     DocType.ORIGIN_PROOF}
