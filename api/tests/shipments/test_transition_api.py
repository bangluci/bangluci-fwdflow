from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.shipments.models import ContainerEvent, CustomsDeclaration

NOW = datetime.now(UTC)


def _go(client, shipment, to_status):
    return client.post(f"/api/shipments/{shipment.id}/transition", json={"to_status": to_status})


def _cancel(client, shipment, reason="Khách huỷ đơn"):
    return client.post(f"/api/shipments/{shipment.id}/cancel", json={"reason": reason})


def _declaration(db, shipment, no="123456789012", cleared=True):
    registered = NOW - timedelta(days=2)
    db.add(CustomsDeclaration(shipment_id=shipment.id, declaration_no=no, type_code="A11", registered_at=registered,
                              cleared_at=NOW - timedelta(days=1) if cleared else None))
    db.flush()


def test_transition_created_to_in_transit_ok(client, login_as, make_shipment):
    login_as("DOCS")
    res = _go(client, make_shipment(), "IN_TRANSIT")
    data = res.json()["data"]
    assert res.status_code == 200 and data["status"] == "IN_TRANSIT" and data["version"] == 1
    assert [e["to_status"] for e in data["events"]] == ["CREATED", "IN_TRANSIT"]


def test_transition_missing_eta_409_missing_fields(client, login_as, make_shipment):
    login_as("DOCS")
    res = _go(client, make_shipment(eta=None), "IN_TRANSIT")
    assert res.status_code == 409 and res.json()["error"]["code"] == "MISSING_FIELDS"
    assert "ETA" in res.json()["error"]["message"]


def test_transition_skip_step_409(client, login_as, make_shipment):
    login_as("DOCS")
    res = _go(client, make_shipment(), "ARRIVED")
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_TRANSITION"


def test_transition_backward_409(client, login_as, make_shipment):
    login_as("DOCS")
    assert _go(client, make_shipment(status="ARRIVED"), "IN_TRANSIT").status_code == 409


def test_transition_in_transit_to_customs_clearing_ok(client, login_as, make_shipment):
    login_as("DOCS")
    assert _go(client, make_shipment(status="IN_TRANSIT"), "CUSTOMS_CLEARING").json()["data"]["status"] == \
        "CUSTOMS_CLEARING"


@pytest.mark.parametrize("target", ["AT_WAREHOUSE", "DELIVERING", "COMPLETED", "CANCELLED"])
def test_transition_to_system_only_status_409(client, login_as, make_shipment, target):
    login_as("ADMIN")
    assert _go(client, make_shipment(status="CLEARED"), target).status_code == 409


def test_dispatch_transition_403(client, login_as, make_shipment):
    login_as("DISPATCH")
    assert _go(client, make_shipment(), "IN_TRANSIT").status_code == 403


def test_transition_unknown_status_422(client, login_as, make_shipment):
    login_as("DOCS")
    assert _go(client, make_shipment(), "FLYING").status_code == 422


def test_cancel_empty_reason_422(client, login_as, make_shipment):
    login_as("DOCS")
    assert _cancel(client, make_shipment(), reason="  ").status_code == 422


def test_cancel_after_gate_out_409(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    shipment = make_shipment(status="CLEARED")
    make_container(shipment, milestones={"DISCHARGED": NOW - timedelta(days=3), "GATE_OUT_FULL": NOW - timedelta(days=1)})
    res = _cancel(client, shipment)
    assert res.status_code == 409 and res.json()["error"]["code"] == "CANCEL_AFTER_GATE_OUT"


def test_cancel_allowed_when_gate_out_voided(client, db, login_as, make_shipment, make_container):
    login_as("DOCS")
    shipment = make_shipment(status="CLEARED")
    container = make_container(shipment, milestones={"DISCHARGED": NOW - timedelta(days=3),
                                                     "GATE_OUT_FULL": NOW - timedelta(days=1)})
    gate = db.scalar(select(ContainerEvent).where(ContainerEvent.container_id == container.id,
                                                  ContainerEvent.kind == "GATE_OUT_FULL"))
    db.add(ContainerEvent(container_id=container.id, kind="VOID", adjusts_event_id=gate.id, occurred_at=NOW,
                          reason="Nhập nhầm"))
    db.flush()
    assert _cancel(client, shipment).json()["data"]["status"] == "CANCELLED"


def test_cancel_completed_409(client, login_as, make_shipment):
    login_as("DOCS")
    res = _cancel(client, make_shipment(status="COMPLETED"))
    assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_TRANSITION"


def test_cancel_writes_event_with_reason_and_audit(client, db, login_as, make_shipment):
    login_as("DOCS")
    data = _cancel(client, make_shipment(), reason="Khách huỷ đơn").json()["data"]
    last = data["events"][-1]
    assert (last["to_status"], last["reason"]) == ("CANCELLED", "Khách huỷ đơn")
    assert db.scalar(select(AuditLog).where(AuditLog.action == "CANCEL", AuditLog.entity == "shipment")) is not None


def test_cleared_requires_declaration_409(client, login_as, make_shipment):
    login_as("DOCS")
    res = _go(client, make_shipment(status="CUSTOMS_CLEARING"), "CLEARED")
    assert res.status_code == 409 and res.json()["error"]["code"] == "DECLARATION_NOT_CLEARED"


def test_cleared_requires_all_declarations_cleared_409(client, db, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment(status="CUSTOMS_CLEARING")
    _declaration(db, shipment)
    _declaration(db, shipment, no="123456789013", cleared=False)
    assert _go(client, shipment, "CLEARED").status_code == 409


def test_cleared_blocked_missing_documents_409(client, db, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment(status="CUSTOMS_CLEARING")
    _declaration(db, shipment)
    res = _go(client, shipment, "CLEARED")
    assert res.status_code == 409 and res.json()["error"]["code"] == "MISSING_DOCUMENTS"
    assert "D/O" in res.json()["error"]["message"]


def test_cleared_ok_when_all_declarations_cleared(client, db, login_as, make_shipment, make_required_documents):
    login_as("DOCS")
    shipment = make_shipment(status="CUSTOMS_CLEARING")
    _declaration(db, shipment)
    make_required_documents(shipment)
    assert _go(client, shipment, "CLEARED").json()["data"]["status"] == "CLEARED"


def test_cleared_requires_origin_proof_when_claims_fta(client, db, login_as, make_shipment, make_required_documents):
    login_as("DOCS")
    shipment = make_shipment(status="CUSTOMS_CLEARING", claims_fta=True)
    _declaration(db, shipment)
    make_required_documents(shipment)
    res = _go(client, shipment, "CLEARED")
    assert res.status_code == 409 and "xuất xứ" in res.json()["error"]["message"]
