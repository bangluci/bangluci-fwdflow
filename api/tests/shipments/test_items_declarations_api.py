from sqlalchemy import select

from app.audit.models import AuditLog

ITEM = {"description": "Vải cotton", "quantity": "100", "unit": "M", "packages": 10, "gross_weight_kg": "250.5",
        "value_amount": 1_500_000, "value_currency": "USD"}
DECL = {"declaration_no": "301234567890", "type_code": "A11", "registered_at": "2026-10-01T02:00:00Z"}


def _items(client, shipment):
    return f"/api/shipments/{shipment.id}/items"


def _decls(client, shipment):
    return f"/api/shipments/{shipment.id}/customs-declarations"


def test_add_item_manual_hs_sets_source(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    data = client.post(_items(client, shipment), json={**ITEM, "hs_code": "52081100"}).json()["data"]
    assert (data["line_no"], data["hs_code"], data["hs_source"]) == (1, "52081100", "manual")
    assert client.post(_items(client, shipment), json=ITEM).json()["data"]["line_no"] == 2


def test_update_item_clear_hs_clears_source(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    item = client.post(_items(client, shipment), json={**ITEM, "hs_code": "52081100"}).json()["data"]
    data = client.patch(f"{_items(client, shipment)}/{item['id']}", json={"hs_code": None}).json()["data"]
    assert data["hs_code"] is None and data["hs_source"] is None


def test_add_item_negative_weight_422(client, login_as, make_shipment):
    login_as("DOCS")
    res = client.post(_items(client, make_shipment()), json={**ITEM, "gross_weight_kg": "-1"})
    assert res.status_code == 422


def test_add_item_bad_hs_code_422(client, login_as, make_shipment):
    login_as("DOCS")
    assert client.post(_items(client, make_shipment()), json={**ITEM, "hs_code": "5208"}).status_code == 422


def test_patch_item_unknown_field_422(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    item = client.post(_items(client, shipment), json=ITEM).json()["data"]
    assert client.patch(f"{_items(client, shipment)}/{item['id']}", json={"hs_source": "ai_accepted"}).status_code == 422


def test_delete_item(client, db, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    item = client.post(_items(client, shipment), json=ITEM).json()["data"]
    assert client.delete(f"{_items(client, shipment)}/{item['id']}").status_code == 200
    assert client.get(f"/api/shipments/{shipment.id}").json()["data"]["items"] == []
    assert db.scalar(select(AuditLog).where(AuditLog.entity == "shipment_item", AuditLog.action == "DELETE"))


def test_item_on_cancelled_shipment_409(client, login_as, make_shipment):
    login_as("DOCS")
    res = client.post(_items(client, make_shipment(status="CANCELLED")), json=ITEM)
    assert res.status_code == 409 and res.json()["error"]["code"] == "SHIPMENT_CLOSED"


def test_item_of_other_shipment_404(client, login_as, make_shipment):
    login_as("DOCS")
    first, second = make_shipment(), make_shipment()
    item = client.post(_items(client, first), json=ITEM).json()["data"]
    assert client.delete(f"{_items(client, second)}/{item['id']}").status_code == 404


def test_add_declaration_ok(client, login_as, make_shipment):
    login_as("DOCS")
    res = client.post(_decls(client, make_shipment()), json={**DECL, "lane": "GREEN"})
    assert res.status_code == 201 and res.json()["data"]["lane"] == "GREEN"


def test_declaration_no_not_12_digits_422(client, login_as, make_shipment):
    login_as("DOCS")
    assert client.post(_decls(client, make_shipment()), json={**DECL, "declaration_no": "12345"}).status_code == 422


def test_declaration_cleared_before_registered_422(client, login_as, make_shipment):
    login_as("DOCS")
    res = client.post(_decls(client, make_shipment()), json={**DECL, "cleared_at": "2026-09-30T02:00:00Z"})
    assert res.status_code == 422


def test_duplicate_declaration_no_409(client, login_as, make_shipment):
    login_as("DOCS")
    assert client.post(_decls(client, make_shipment()), json=DECL).status_code == 201
    res = client.post(_decls(client, make_shipment()), json=DECL)
    assert res.status_code == 409 and res.json()["error"]["code"] == "DUPLICATE_DECLARATION"


def test_update_declaration_sets_cleared_at(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    decl = client.post(_decls(client, shipment), json=DECL).json()["data"]
    res = client.patch(f"{_decls(client, shipment)}/{decl['id']}", json={"cleared_at": "2026-10-02T02:00:00Z"})
    assert res.json()["data"]["cleared_at"].startswith("2026-10-02")


def test_declaration_locked_after_cleared_409(client, login_as, make_shipment):
    login_as("DOCS")
    res = client.post(_decls(client, make_shipment(status="CLEARED")), json=DECL)
    assert res.status_code == 409 and res.json()["error"]["code"] == "DECLARATION_LOCKED"


def test_dispatch_cannot_edit_items_403(client, login_as, make_shipment):
    login_as("DISPATCH")
    assert client.post(_items(client, make_shipment()), json=ITEM).status_code == 403
