import pytest
from sqlalchemy import select

from app.ai.extraction.models import ExtractionStatus
from app.audit.models import AuditLog
from app.catalog.models import Carrier
from app.config import get_settings
from app.shipments.models import Container, ShipmentItem
from tests.extraction.samples import bl, dump, invoice


@pytest.fixture
def review_hbl(db, make_shipment, make_extraction):
    """Lô FCL chưa có số HBL / tàu + bản trích xuất HBL đang chờ duyệt."""
    shipment = make_shipment(status="IN_TRANSIT")

    def _make(**overrides):
        return make_extraction(shipment=shipment, status="REVIEW", detected_doc_type="HBL", field_issues=[],
                               result=dump(bl(**overrides)))

    _make.shipment = shipment
    return _make


def _approve(client, extraction, version=None, **body):
    payload = {"version": extraction.version if version is None else version, **body}
    return client.post(f"/api/extractions/{extraction.id}/approve", json=payload)


def _error(res):
    return res.json()["error"]


def test_approve_writes_selected_fields_and_containers(client, db, login_as, review_hbl):
    login_as("DOCS")
    extraction = review_hbl()
    res = _approve(client, extraction)
    shipment = review_hbl.shipment
    assert res.status_code == 200 and res.json()["data"]["status"] == "APPROVED"
    assert (shipment.hbl_no, shipment.vessel, shipment.voyage, shipment.total_packages) == ("HBL001", "EVER A", "12E", 100)
    assert shipment.version == 2
    (container,) = db.scalars(select(Container).where(Container.shipment_id == shipment.id)).all()
    assert (container.container_no, container.seal_no, container.container_type) == ("CSQU3054383", "S1", "40HC")
    assert extraction.approved_result["bl_no"] == "HBL001" and extraction.reviewed_by is not None


def test_approve_keeps_old_value_when_not_chosen(client, db, login_as, review_hbl):
    login_as("DOCS")
    shipment = review_hbl.shipment
    shipment.vessel = "OLD VESSEL"
    shipment.voyage = "OLD VOYAGE"
    db.flush()
    extraction = review_hbl()
    fields = {"/voyage": {"value": "12E", "use": "new"}}
    assert _approve(client, extraction, fields=fields).status_code == 200
    assert (shipment.vessel, shipment.voyage) == ("OLD VESSEL", "12E")


def test_use_old_skips_write_even_for_empty_field(client, db, login_as, review_hbl):
    login_as("DOCS")
    extraction = review_hbl()
    assert _approve(client, extraction, fields={"/vessel": {"value": "EVER A", "use": "old"}}).status_code == 200
    assert review_hbl.shipment.vessel is None and extraction.approved_result["vessel"] == "EVER A"


def test_approve_records_edited_fields_and_audit_source(client, db, login_as, review_hbl):
    login_as("DOCS")
    extraction = review_hbl()
    fields = {"/consignee": {"value": "CONG TY TNHH MINH LONG 2"},
              "/containers/0": {"value": {"seal_no": "S99"}}}
    res = _approve(client, extraction, fields=fields)
    assert res.status_code == 200 and extraction.edited_fields == ["/consignee", "/containers/0/seal_no"]
    shipment_audit = db.scalar(select(AuditLog).where(AuditLog.entity == "shipment", AuditLog.action == "UPDATE"))
    assert shipment_audit.after["_source"]["/bl_no"] == "ai_accepted"
    container_audit = db.scalar(select(AuditLog).where(AuditLog.entity == "container", AuditLog.action == "CREATE"))
    assert container_audit.after["_source"]["/containers/0/seal_no"] == "ai_edited"
    assert container_audit.after["_source"]["/containers/0/container_no"] == "ai_accepted"


def test_approve_rejects_block_issue_field_invalid(client, db, login_as, review_hbl):
    login_as("DOCS")
    bad = {"container_no": "CSQU3054384", "seal_no": "S1", "container_type_raw": "45G1", "container_type": "40HC",
           "packages": 1, "gross_weight_kg": "1"}
    extraction = review_hbl(containers=[bad])
    res = _approve(client, extraction)
    assert res.status_code == 422 and _error(res)["code"] == "FIELD_INVALID"
    assert "/containers/0/container_no" in _error(res)["details"]["paths"]
    fixed = _approve(client, extraction, fields={"/containers/0": {"value": {"container_no": "CSQU3054383"}}})
    assert fixed.status_code == 200 and extraction.edited_fields == ["/containers/0/container_no"]


def test_approve_rejects_invalid_edit_type(client, login_as, review_hbl):
    login_as("DOCS")
    res = _approve(client, review_hbl(), fields={"/total_packages": {"value": "nhiều"}})
    assert res.status_code == 422 and _error(res)["details"]["paths"] == ["/total_packages"]


@pytest.mark.parametrize("path", ["/detected_doc_type", "/legible", "/khong_co", "/containers/9", "/vessel/0"])
def test_approve_rejects_unknown_or_readonly_path(client, login_as, review_hbl, path):
    login_as("DOCS")
    assert _approve(client, review_hbl(), fields={path: {"value": "x"}}).status_code == 422


def test_approve_requires_manual_check_when_suspicious(client, login_as, review_hbl):
    login_as("DOCS")
    extraction = review_hbl(suspicious_content=True, suspicious_note="Có chữ ẩn")
    extraction.suspicious_content = True
    res = _approve(client, extraction)
    assert res.status_code == 422 and _error(res)["code"] == "MANUAL_CHECK_REQUIRED"
    ok = _approve(client, extraction, manual_check_done=True)
    assert ok.status_code == 200 and extraction.manual_check_done is True


def test_approve_requires_confirm_on_doc_type_mismatch(client, login_as, review_hbl):
    login_as("DOCS")
    extraction = review_hbl()
    extraction.detected_doc_type = "MBL"
    res = _approve(client, extraction)
    assert res.status_code == 422 and _error(res)["code"] == "DOC_TYPE_MISMATCH"
    assert _approve(client, extraction, confirm_doc_type_mismatch=True).status_code == 200


def test_approve_version_conflict(client, login_as, review_hbl):
    login_as("DOCS")
    extraction = review_hbl()
    res = _approve(client, extraction, version=extraction.version + 1)
    assert res.status_code == 409 and _error(res)["code"] == "VERSION_CONFLICT"


def test_approve_from_approved_is_invalid_transition(client, login_as, review_hbl):
    login_as("DOCS")
    extraction = review_hbl()
    _approve(client, extraction)
    res = _approve(client, extraction)
    assert res.status_code == 409 and _error(res)["code"] == "INVALID_TRANSITION"


def test_approve_unresolved_carrier_is_skipped_not_failed(client, db, login_as, review_hbl):
    login_as("DOCS")
    shipment = review_hbl.shipment
    shipment.carrier_id = None
    db.flush()
    res = _approve(client, review_hbl(carrier_name="HÃNG LẠ"))
    assert res.status_code == 200 and res.json()["data"]["skipped"] == [
        {"path": "/carrier_name", "reason": "Không tìm thấy hãng tàu 'HÃNG LẠ' trong danh mục"}]
    assert shipment.carrier_id is None


def test_approve_resolves_carrier_and_ports_by_alias(client, db, login_as, review_hbl):
    from app.catalog.models import Port

    login_as("DOCS")
    shipment = review_hbl.shipment
    shipment.carrier_id = shipment.pod_port_id = shipment.pol_port_id = None
    db.add(Port(code="VNHPH", name="Hải Phòng", aliases=["HAI PHONG"]))
    db.flush()
    assert _approve(client, review_hbl(carrier_name="maersk", pod="Hai Phong", pol="cnsha")).status_code == 200
    assert shipment.carrier_id == db.scalar(select(Carrier.id).where(Carrier.code == "MAEU"))
    assert shipment.pod_port_id is not None and shipment.pol_port_id is not None


def test_approve_lcl_shipment_skips_containers(client, db, login_as, make_shipment, make_extraction):
    login_as("DOCS")
    shipment = make_shipment(status="IN_TRANSIT", load_type="LCL")
    extraction = make_extraction(shipment=shipment, status="REVIEW", detected_doc_type="HBL", field_issues=[],
                                 result=dump(bl()))
    res = _approve(client, extraction)
    assert res.json()["data"]["skipped"] == [{"path": "/containers", "reason": "Lô LCL không có container"}]
    assert db.scalars(select(Container).where(Container.shipment_id == shipment.id)).all() == []


def test_approve_invoice_creates_items_in_minor_units(client, db, login_as, make_shipment, make_extraction):
    login_as("DOCS")
    shipment = make_shipment()
    extraction = make_extraction(shipment=shipment, status="REVIEW", doc_type="INVOICE", detected_doc_type="INVOICE",
                                 field_issues=[], result=dump(invoice()))
    assert _approve(client, extraction, fields={"/lines/1": {"value": {}, "use": "old"}}).status_code == 200
    items = db.scalars(select(ShipmentItem).where(ShipmentItem.shipment_id == shipment.id)).all()
    assert [(i.line_no, i.description, i.value_amount, i.value_currency) for i in items] == [
        (1, "Vải cotton", 100050, "USD")]


def test_reject_requires_reason(client, login_as, review_hbl):
    login_as("DOCS")
    extraction = review_hbl()
    assert client.post(f"/api/extractions/{extraction.id}/reject", json={"reason": " ngắn "}).status_code == 422
    res = client.post(f"/api/extractions/{extraction.id}/reject", json={"reason": "Sai chứng từ, tải lại"})
    assert res.status_code == 200 and extraction.status == ExtractionStatus.REJECTED
    assert extraction.reject_reason == "Sai chứng từ, tải lại"


def test_retry_resets_attempts_and_pending(client, login_as, make_extraction):
    login_as("DOCS")
    extraction = make_extraction(status="FAILED", attempts=4, error_code="AI_UNAVAILABLE", error_message="lỗi")
    res = client.post(f"/api/extractions/{extraction.id}/retry")
    assert res.status_code == 200
    assert (extraction.status, extraction.attempts, extraction.error_code) == (ExtractionStatus.PENDING, 0, None)


def test_retry_only_from_failed(client, login_as, make_extraction):
    login_as("DOCS")
    res = client.post(f"/api/extractions/{make_extraction(status='REVIEW').id}/retry")
    assert res.status_code == 409 and _error(res)["code"] == "INVALID_TRANSITION"


def test_retry_when_ai_disabled_returns_ai_disabled(client, login_as, make_extraction, monkeypatch):
    login_as("DOCS")
    extraction = make_extraction(status="FAILED", attempts=4)
    monkeypatch.setattr(get_settings(), "ai_external_enabled", False)
    res = client.post(f"/api/extractions/{extraction.id}/retry")
    assert res.status_code == 503 and _error(res)["code"] == "AI_DISABLED" and extraction.status == "FAILED"


def test_dispatch_cannot_approve(client, login_as, review_hbl):
    login_as("DISPATCH")
    assert _approve(client, review_hbl()).status_code == 403


def test_no_audit_row_contains_password_hash(db):
    rows = db.scalars(select(AuditLog)).all()
    assert not [r for r in rows if "password_hash" in str(r.before) + str(r.after) and "<changed>" not in
                str(r.before) + str(r.after)]
