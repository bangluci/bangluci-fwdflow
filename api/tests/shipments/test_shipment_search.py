from datetime import date

from app.catalog.models import Carrier, Customer


def _list(client, **params):
    return client.get("/api/shipments", params=params).json()


def _codes(payload):
    return {row["code"] for row in payload["data"]}


def test_search_by_code_partial(client, login_as, make_shipment):
    login_as("DOCS")
    target, _ = make_shipment(), make_shipment()
    assert _codes(_list(client, q=target.code[3:8])) >= {target.code}
    assert _codes(_list(client, q=target.code)) == {target.code}


def test_search_by_mbl_partial(client, login_as, make_shipment):
    login_as("DOCS")
    target = make_shipment(mbl_no="MAEU7654321")
    make_shipment(mbl_no="COSU111")
    assert _codes(_list(client, q="u76543")) == {target.code}


def test_search_by_hbl_partial(client, login_as, make_shipment):
    login_as("DOCS")
    target = make_shipment(hbl_no="HBL-ABC-99")
    make_shipment()
    assert _codes(_list(client, q="abc-99")) == {target.code}


def test_search_by_container_no_partial_ignores_spaces(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    target = make_shipment()
    container = make_container(target)
    make_container(make_shipment())
    q = f"{container.container_no[:4]} {container.container_no[4:10]}".lower()
    assert _codes(_list(client, q=q)) == {target.code}


def test_search_by_customer_name_unaccent(client, db, login_as, make_shipment):
    login_as("DOCS")
    minh = Customer(name="Công ty Minh Anh")
    db.add(minh)
    db.flush()
    target = make_shipment(customer=minh)
    make_shipment()
    assert _codes(_list(client, q="cong ty minh")) == {target.code}


def test_search_escapes_like_wildcards(client, login_as, make_shipment):
    login_as("DOCS")
    make_shipment()
    assert _list(client, q="%")["data"] == []
    assert _list(client, q="_")["data"] == []


def test_filter_by_status_multi(client, login_as, make_shipment):
    login_as("DOCS")
    created, arrived = make_shipment(), make_shipment(status="ARRIVED")
    make_shipment(status="CLEARED")
    assert _codes(_list(client, status=["CREATED", "ARRIVED"])) == {created.code, arrived.code}


def test_filter_by_customer(client, db, login_as, make_shipment):
    login_as("DOCS")
    customer = Customer(name="KH Loc")
    db.add(customer)
    db.flush()
    target = make_shipment(customer=customer)
    make_shipment()
    assert _codes(_list(client, customer_id=customer.id)) == {target.code}


def test_filter_by_carrier(client, db, login_as, make_shipment):
    login_as("DOCS")
    carrier = Carrier(code="REGU", name="RCL")
    db.add(carrier)
    db.flush()
    target = make_shipment(carrier_id=carrier.id)
    make_shipment()
    assert _codes(_list(client, carrier_id=carrier.id)) == {target.code}


def test_filter_by_eta_range_inclusive(client, login_as, make_shipment):
    login_as("DOCS")
    early, on_edge, late = (make_shipment(eta=date(2026, 11, d)) for d in (1, 10, 20))
    found = _codes(_list(client, eta_from="2026-11-05", eta_to="2026-11-10"))
    assert found == {on_edge.code} and early.code not in found and late.code not in found


def test_list_meta_total_page_limit(client, login_as, make_shipment):
    login_as("DOCS")
    for _ in range(3):
        make_shipment()
    payload = _list(client, page=2, limit=2)
    assert payload["meta"] == {"total": 3, "page": 2, "limit": 2} and len(payload["data"]) == 1


def test_list_rows_carry_screen_columns(client, login_as, make_shipment, make_container):
    login_as("DOCS")
    shipment = make_shipment()
    make_container(shipment)
    row = _list(client)["data"][0]
    assert row["customer_name"] == "KH Test" and row["carrier_code"] == "MAEU" and row["pod_code"] == "VNSGN"
    assert row["container_count"] == 1


def test_limit_over_100_422(client, login_as):
    login_as("DOCS")
    assert client.get("/api/shipments", params={"limit": 101}).status_code == 422
