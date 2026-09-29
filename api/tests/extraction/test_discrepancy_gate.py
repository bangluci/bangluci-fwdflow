from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from tests.extraction.samples import bl, dump, packing_list


@pytest.fixture
def approve_doc(make_document, make_extraction):
    """Tạo chứng từ + bản trích xuất đã duyệt cho một lô."""

    def _make(shipment, doc_type, result, when=None):
        document = make_document(shipment, doc_type)
        return document, make_extraction(document=document, status="APPROVED", approved_result=dump(result),
                                         reviewed_at=when or datetime.now(UTC), doc_type=doc_type)

    return _make


def _mismatched_containers():
    return [{"container_no": "CSQU3054384", "seal_no": "S1"}]  # sai một ký tự so với HBL


def _clear(client, shipment):
    return client.post(f"/api/shipments/{shipment.id}/transition", json={"to_status": "CUSTOMS_CLEARING"})


def test_block_discrepancy_blocks_customs_clearing(client, login_as, make_shipment, approve_doc):
    login_as("DOCS")
    shipment = make_shipment(status="IN_TRANSIT")
    approve_doc(shipment, "HBL", bl())
    approve_doc(shipment, "PACKING_LIST", packing_list(containers=_mismatched_containers()))
    res = _clear(client, shipment)
    error = res.json()["error"]
    assert res.status_code == 409 and error["code"] == "UNRESOLVED_DISCREPANCY"
    assert set(error["details"]["keys"]) == {"CONTAINER_SET:CSQU3054383", "CONTAINER_SET:CSQU3054384"}


def test_ack_unblocks_customs_clearing(client, db, login_as, make_shipment, approve_doc):
    login_as("DOCS")
    shipment = make_shipment(status="ARRIVED")
    approve_doc(shipment, "HBL", bl())
    approve_doc(shipment, "PACKING_LIST", packing_list(containers=_mismatched_containers()))
    for key in ("CONTAINER_SET:CSQU3054383", "CONTAINER_SET:CSQU3054384"):
        ack = client.post(f"/api/shipments/{shipment.id}/discrepancy-acks",
                          json={"discrepancy_key": key, "reason": "Đã hỏi shipper, số đúng là ở HBL"})
        assert ack.status_code == 201
    assert _clear(client, shipment).json()["data"]["status"] == "CUSTOMS_CLEARING"
    audit = db.scalar(select(AuditLog).where(AuditLog.entity == "discrepancy_ack"))
    assert "shipper" in audit.after["reason"]


def test_fixing_values_unblocks_without_ack(client, login_as, make_shipment, approve_doc):
    login_as("DOCS")
    shipment = make_shipment(status="IN_TRANSIT")
    wrong = {"container_no": "CSQU3054384", "seal_no": "S1", "container_type_raw": "45G1", "container_type": "40HC",
             "packages": 1, "gross_weight_kg": "1"}
    old_hbl, _ = approve_doc(shipment, "HBL", bl(containers=[wrong]))
    approve_doc(shipment, "PACKING_LIST", packing_list())
    assert _clear(client, shipment).status_code == 409
    new_hbl, _ = approve_doc(shipment, "HBL", bl())  # HBL sửa lại, khớp packing list
    old_hbl.superseded_by_id = new_hbl.id
    assert _clear(client, shipment).status_code == 200


def test_crosscheck_ignores_superseded_documents(client, login_as, make_shipment, approve_doc):
    login_as("DOCS")
    shipment = make_shipment(status="IN_TRANSIT")
    old, _ = approve_doc(shipment, "PACKING_LIST", packing_list(containers=_mismatched_containers()))
    approve_doc(shipment, "HBL", bl())
    assert client.get(f"/api/shipments/{shipment.id}/crosscheck").json()["data"]["status"] == "DISCREPANCY"
    new, _ = approve_doc(shipment, "PACKING_LIST", packing_list())
    old.superseded_by_id = new.id
    data = client.get(f"/api/shipments/{shipment.id}/crosscheck").json()["data"]
    assert data["status"] == "MATCH" and set(data["documents"]) == {"HBL", "PACKING_LIST"}


def test_ack_unknown_key_422(client, login_as, make_shipment, approve_doc):
    login_as("DOCS")
    shipment = make_shipment(status="IN_TRANSIT")
    approve_doc(shipment, "HBL", bl())
    res = client.post(f"/api/shipments/{shipment.id}/discrepancy-acks",
                      json={"discrepancy_key": "PACKAGES", "reason": "Không có sai lệch này"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "UNKNOWN_DISCREPANCY"


def test_ack_twice_409_and_short_reason_422(client, login_as, make_shipment, approve_doc):
    login_as("DOCS")
    shipment = make_shipment(status="IN_TRANSIT")
    approve_doc(shipment, "HBL", bl())
    approve_doc(shipment, "PACKING_LIST", packing_list(total_packages=99))
    url = f"/api/shipments/{shipment.id}/discrepancy-acks"
    assert client.post(url, json={"discrepancy_key": "PACKAGES", "reason": "abc"}).status_code == 422
    assert client.post(url, json={"discrepancy_key": "PACKAGES", "reason": "Đã đối chiếu tay"}).status_code == 201
    res = client.post(url, json={"discrepancy_key": "PACKAGES", "reason": "Đã đối chiếu tay"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "ALREADY_ACKED"


def test_warn_only_does_not_block(client, login_as, make_shipment, approve_doc):
    login_as("DOCS")
    shipment = make_shipment(status="IN_TRANSIT")
    approve_doc(shipment, "HBL", bl())
    approve_doc(shipment, "PACKING_LIST", packing_list(total_packages=99))
    report = client.get(f"/api/shipments/{shipment.id}/crosscheck").json()["data"]
    assert [d["level"] for d in report["discrepancies"]] == ["WARN"]
    assert _clear(client, shipment).status_code == 200


def test_insufficient_does_not_block(client, login_as, make_shipment, approve_doc):
    login_as("DOCS")
    shipment = make_shipment(status="IN_TRANSIT")
    approve_doc(shipment, "HBL", bl())
    assert client.get(f"/api/shipments/{shipment.id}/crosscheck").json()["data"]["status"] == "INSUFFICIENT"
    assert _clear(client, shipment).status_code == 200


def test_crosscheck_report_includes_ack(client, login_as, make_shipment, approve_doc):
    login_as("DOCS")
    shipment = make_shipment(status="IN_TRANSIT")
    approve_doc(shipment, "HBL", bl())
    approve_doc(shipment, "PACKING_LIST", packing_list(total_packages=99))
    client.post(f"/api/shipments/{shipment.id}/discrepancy-acks",
                json={"discrepancy_key": "PACKAGES", "reason": "Đã đối chiếu tay"})
    (item,) = client.get(f"/api/shipments/{shipment.id}/crosscheck").json()["data"]["discrepancies"]
    assert item["ack"]["reason"] == "Đã đối chiếu tay" and item["values"] == {"HBL": 100, "PACKING_LIST": 99}


def test_accountant_can_read_but_not_ack(client, login_as, make_shipment):
    login_as("ACCOUNTANT")
    shipment = make_shipment()
    assert client.get(f"/api/shipments/{shipment.id}/crosscheck").status_code == 200
    res = client.post(f"/api/shipments/{shipment.id}/discrepancy-acks",
                      json={"discrepancy_key": "PACKAGES", "reason": "Đã đối chiếu tay"})
    assert res.status_code == 403
