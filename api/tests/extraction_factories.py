"""Fixture tạo Extraction cho test (đăng ký trong conftest bằng pytest_plugins)."""

import pytest

from app.ai.extraction.models import Extraction


@pytest.fixture
def make_extraction(db, make_shipment, make_document):
    """Extraction gắn vào chứng từ; mặc định tạo lô + chứng từ HBL mới."""

    def _make(document=None, status: str = "PENDING", **fields) -> Extraction:
        if document is None:
            shipment = fields.pop("shipment", None) or make_shipment()
            document = make_document(shipment, fields.get("doc_type", "HBL"))
        extraction = Extraction(document_id=document.id, shipment_id=document.shipment_id,
                                doc_type=fields.pop("doc_type", document.doc_type), status=status, **fields)
        db.add(extraction)
        db.flush()
        return extraction

    return _make
