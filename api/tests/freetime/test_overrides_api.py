from sqlalchemy import func, select

from app.audit.models import AuditLog
from app.freetime.models import ShipmentFreeTimeOverride


def _url(shipment):
    return f"/api/shipments/{shipment.id}/freetime-overrides"


def _put(client, shipment, fee_type="DEM", free_days=10, source="DO", **extra):
    return client.put(_url(shipment), json={"fee_type": fee_type, "free_days": free_days, "source": source, **extra})


def test_put_override_creates_then_updates_same_fee_type(client, db, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    assert _put(client, shipment, free_days=10).status_code == 200
    res = _put(client, shipment, free_days=14, source="CONTRACT")
    assert res.json()["data"]["free_days"] == 14 and res.json()["data"]["source"] == "CONTRACT"
    assert db.scalar(select(func.count()).select_from(ShipmentFreeTimeOverride)) == 1
    assert [o["free_days"] for o in client.get(_url(shipment)).json()["data"]] == [14]


def test_override_changes_container_clock(client, login_as, ft):
    login_as("DOCS")
    ft.standard_rules()
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    shipment_url = f"/api/shipments/{container.shipment_id}/freetime-overrides"
    assert client.put(shipment_url, json={"fee_type": "DEM", "free_days": 10, "source": "DO"}).status_code == 200
    dem = ft.rows("2026-11-03", container)["DEM"]
    assert (dem["free_days"], dem["rule_source"]) == (10, "OVERRIDE")
    assert client.delete(f"{shipment_url}/DEM").status_code == 200
    dem = ft.rows("2026-11-03", container)["DEM"]
    assert (dem["free_days"], dem["rule_source"]) == (5, "RULE")


def test_delete_override_missing_404(client, login_as, make_shipment):
    login_as("DOCS")
    assert client.delete(f"{_url(make_shipment())}/DEM").status_code == 404


def test_override_mixing_combined_and_dem_400(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    assert _put(client, shipment, "DEM").status_code == 200
    res = _put(client, shipment, "COMBINED")
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_OVERRIDE_SET"
    other = make_shipment()
    assert _put(client, other, "COMBINED").status_code == 200
    assert _put(client, other, "DET").status_code == 400


def test_override_document_must_belong_to_shipment_and_match_source_400(client, login_as, make_shipment,
                                                                      make_document):
    login_as("DOCS")
    shipment, other = make_shipment(), make_shipment()
    foreign_do = make_document(other, "DO")
    invoice = make_document(shipment, "INVOICE")
    for document in (foreign_do, invoice):
        res = _put(client, shipment, source="DO", document_id=document.id)
        assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_DOCUMENT"
    own_do = make_document(shipment, "DO")
    assert _put(client, shipment, source="DO", document_id=own_do.id).json()["data"]["document_id"] == own_do.id


def test_override_document_superseded_is_rejected(client, db, login_as, make_shipment, make_document):
    login_as("DOCS")
    shipment = make_shipment()
    old, new = make_document(shipment, "ARRIVAL_NOTICE"), make_document(shipment, "ARRIVAL_NOTICE")
    old.superseded_by_id = new.id
    db.flush()
    assert _put(client, shipment, source="ARRIVAL_NOTICE", document_id=old.id).status_code == 400
    assert _put(client, shipment, source="ARRIVAL_NOTICE", document_id=new.id).status_code == 200


def test_override_on_cancelled_shipment_409(client, login_as, make_shipment):
    login_as("DOCS")
    res = _put(client, make_shipment(status="CANCELLED"))
    assert res.status_code == 409 and res.json()["error"]["code"] == "SHIPMENT_CLOSED"


def test_override_free_days_out_of_range_422(client, login_as, make_shipment):
    login_as("DOCS")
    assert _put(client, make_shipment(), free_days=366).status_code == 422


def test_override_write_records_audit(client, db, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    _put(client, shipment, free_days=10)
    _put(client, shipment, free_days=12)
    client.delete(f"{_url(shipment)}/DEM")
    actions = [row.action for row in db.scalars(select(AuditLog).where(
        AuditLog.entity == "shipment_free_time_override").order_by(AuditLog.id))]
    assert actions == ["CREATE", "UPDATE", "DELETE"]


def test_override_write_forbidden_for_dispatch_and_accountant_403(client, login_as, make_shipment):
    shipment = make_shipment()
    for role in ("DISPATCH", "ACCOUNTANT"):
        client.cookies.clear()
        login_as(role)
        assert _put(client, shipment).status_code == 403
        assert client.get(_url(shipment)).status_code == 200
