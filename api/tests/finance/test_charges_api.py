import pytest
from sqlalchemy import func, select

from app.audit.models import AuditLog
from app.finance.models import Charge


def _url(shipment, suffix=""):
    return f"/api/shipments/{shipment.id}/charges{suffix}"


def _usd(**extra):
    return {"direction": "COST", "category": "OCEAN_FREIGHT", "amount": 12345, "currency": "USD",
            "fx_rate": "25410", **extra}


def _count(db):
    return db.scalar(select(func.count()).select_from(Charge))


def test_accountant_creates_usd_charge_returns_amount_vnd(client, login_as, make_shipment):
    login_as("ACCOUNTANT")
    res = client.post(_url(make_shipment()), json=_usd())
    assert res.status_code == 201 and res.json()["data"]["amount_vnd"] == 3136865


def test_usd_charge_without_fx_rate_returns_400(client, db, login_as, make_shipment):
    login_as("ACCOUNTANT")
    body = _usd()
    del body["fx_rate"]
    res = client.post(_url(make_shipment()), json=body)
    assert res.status_code == 400 and res.json()["error"]["code"] == "FX_RATE_REQUIRED" and _count(db) == 0


@pytest.mark.parametrize("role", ["DOCS", "DISPATCH"])
def test_docs_and_dispatch_forbidden_on_charges(client, login_as, make_shipment, role):
    login_as(role)
    shipment = make_shipment()
    for res in (client.get(_url(shipment)), client.post(_url(shipment), json=_usd())):
        assert res.status_code == 403 and res.json()["error"]["code"] == "FORBIDDEN"


def test_charge_create_writes_audit_log(client, db, login_as, make_shipment):
    login_as("ACCOUNTANT")
    charge_id = client.post(_url(make_shipment()), json=_usd()).json()["data"]["id"]
    row = db.scalars(select(AuditLog).where(AuditLog.entity == "charge", AuditLog.entity_id == str(charge_id))).one()
    assert row.action == "CREATE" and row.after["amount_vnd"] == 3136865


def test_charge_update_recomputes_amount_vnd(client, login_as, make_shipment):
    login_as("ACCOUNTANT")
    shipment = make_shipment()
    charge_id = client.post(_url(shipment), json=_usd()).json()["data"]["id"]
    res = client.patch(_url(shipment, f"/{charge_id}"), json={"fx_rate": "25000"})
    assert res.status_code == 200 and res.json()["data"]["amount_vnd"] == 3086250
    res = client.patch(_url(shipment, f"/{charge_id}"), json={"currency": "VND"})
    assert (res.json()["data"]["amount_vnd"], res.json()["data"]["fx_rate"]) == (12345, "1.0000")


def test_charge_delete_writes_audit_log(client, db, login_as, make_shipment):
    login_as("ACCOUNTANT")
    shipment = make_shipment()
    charge_id = client.post(_url(shipment), json=_usd()).json()["data"]["id"]
    assert client.delete(_url(shipment, f"/{charge_id}")).status_code == 200 and _count(db) == 0
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity == "charge").order_by(AuditLog.id)).all()
    assert actions == ["CREATE", "DELETE"]


def test_list_charges_returns_profit_totals(client, login_as, make_shipment):
    login_as("ACCOUNTANT")
    shipment = make_shipment()
    rows = [{"direction": "REVENUE", "category": "OCEAN_FREIGHT", "amount": 15_000_000, "currency": "VND"},
            {"direction": "REVENUE", "category": "OTHER", "amount": 50_000, "currency": "USD", "fx_rate": "25400"},
            {"direction": "COST", "category": "OCEAN_FREIGHT", "amount": 35_000, "currency": "USD", "fx_rate": "25400"},
            {"direction": "COST", "category": "TRUCKING", "amount": 3_500_000, "currency": "VND"},
            {"direction": "COST", "category": "DEM", "amount": 2_200_000, "currency": "VND"}]
    for row in rows:
        assert client.post(_url(shipment), json=row).status_code == 201
    data = client.get(_url(shipment)).json()["data"]
    assert data["profit"] == {"revenue_vnd": 27_700_000, "cost_vnd": 14_590_000, "profit_vnd": 13_110_000}
    assert len(data["items"]) == 5


def test_charge_unknown_shipment_returns_404(client, login_as, make_shipment):
    login_as("ACCOUNTANT")
    shipment, other = make_shipment(), make_shipment()
    charge_id = client.post(_url(shipment), json=_usd()).json()["data"]["id"]
    assert client.get("/api/shipments/999999/charges").status_code == 404
    assert client.post("/api/shipments/999999/charges", json=_usd()).status_code == 404
    assert client.patch(_url(other, f"/{charge_id}"), json={"note": "x"}).status_code == 404
    assert client.delete(_url(other, f"/{charge_id}")).status_code == 404


def test_cancelled_shipment_still_accepts_charges(client, login_as, make_shipment):
    login_as("ACCOUNTANT")
    assert client.post(_url(make_shipment(status="CANCELLED")), json=_usd()).status_code == 201
