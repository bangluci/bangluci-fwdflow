import pytest
from sqlalchemy import text

AS_OF = "2026-11-08"


@pytest.fixture
def clocks(db, ft):
    """3 container: RED (dỡ 20/10), YELLOW (dỡ 04/11), GREEN (dỡ 08/11), tính tới 08/11 theo quy tắc mẫu."""
    ft.standard_rules()
    db.execute(text("SELECT set_config('app.as_of', :d, true)"), {"d": AS_OF})
    return {level: ft.container(milestones={"DISCHARGED": day}) for level, day in
            (("RED", "2026-10-20"), ("YELLOW", "2026-11-04"), ("GREEN", "2026-11-08"))}


def _get(client, **params):
    return client.get("/api/freetime/containers", params=params).json()


def _numbers(payload, fee_type="DEM"):
    return [row["container_no"] for row in payload["data"] if row["fee_type"] == fee_type]


def test_list_sorted_worst_level_first_then_due_date(client, login_as, clocks):
    login_as("DOCS")
    payload = _get(client)
    expected = [clocks[level].container_no for level in ("RED", "YELLOW", "GREEN")]
    assert _numbers(payload) == expected
    assert payload["meta"] == {"total": 6, "page": 1, "limit": 50}
    assert {"days_left", "fee_amount", "container_level", "due_date"} <= payload["data"][0].keys()


def test_filter_by_level_status_and_fee_type(client, login_as, ft, clocks):
    login_as("DOCS")
    closed = ft.container(milestones={"DISCHARGED": "2026-11-01", "GATE_OUT_FULL": "2026-11-03"})
    red_rows = _get(client, level="RED")["data"]
    assert [(r["container_no"], r["fee_type"]) for r in red_rows] == [(clocks["RED"].container_no, "DEM")]
    closed_rows = _get(client, status="CLOSED")["data"]
    assert [(r["container_no"], r["fee_type"]) for r in closed_rows] == [(closed.container_no, "DEM")]
    assert {r["fee_type"] for r in _get(client, fee_type="DET")["data"]} == {"DET"}
    both = _get(client, level=["RED", "YELLOW"])["data"]
    assert {r["level"] for r in both} == {"RED", "YELLOW"}


def test_unknown_filter_value_is_422(client, login_as, clocks):
    login_as("DOCS")
    assert client.get("/api/freetime/containers", params={"level": "BLUE"}).status_code == 422
    assert client.get("/api/freetime/containers", params={"limit": 201}).status_code == 422


def test_cancelled_shipments_hidden_unless_included(client, login_as, ft, clocks):
    login_as("DOCS")
    cancelled = ft.container(status="CANCELLED", milestones={"DISCHARGED": "2026-10-01"})
    assert cancelled.container_no not in _numbers(_get(client))
    assert cancelled.container_no in _numbers(_get(client, include_cancelled="true"))


def test_completed_shipments_keep_closed_clocks_visible(client, login_as, ft, clocks):
    login_as("DOCS")
    done = ft.container(status="COMPLETED", milestones={"DISCHARGED": "2026-11-01", "GATE_OUT_FULL": "2026-11-03",
                                                        "EMPTY_RETURNED": "2026-11-06"})
    assert done.container_no in _numbers(_get(client, status="CLOSED"))


def test_filter_by_q_container_or_shipment_code(client, login_as, db, clocks):
    login_as("DOCS")
    target = clocks["YELLOW"]
    spaced = f"{target.container_no[:4]} {target.container_no[4:10]}-{target.container_no[10:]}".lower()
    assert set(_numbers(_get(client, q=spaced))) == {target.container_no}
    code = db.execute(text("SELECT code FROM shipments WHERE id = :s"), {"s": target.shipment_id}).scalar()
    assert set(_numbers(_get(client, q=code))) == {target.container_no}
    assert _get(client, q="%")["data"] == []


def test_filter_by_shipment_customer_and_carrier(client, login_as, clocks):
    login_as("DOCS")
    red = clocks["RED"]
    assert set(_numbers(_get(client, shipment_id=red.shipment_id))) == {red.container_no}
    assert _get(client, carrier_id=999999)["data"] == []


def test_pagination_meta(client, login_as, clocks):
    login_as("DOCS")
    payload = _get(client, page=2, limit=4)
    assert payload["meta"] == {"total": 6, "page": 2, "limit": 4} and len(payload["data"]) == 2


@pytest.mark.parametrize("role", ["CUSTOMER", "DRIVER"])
def test_forbidden_for_customer_and_driver(client, login_as, role):
    login_as(role)
    assert client.get("/api/freetime/containers").status_code == 403


def test_shipment_list_filter_by_freetime_level(client, login_as, ft, clocks):
    login_as("DOCS")
    cancelled = ft.container(status="CANCELLED", milestones={"DISCHARGED": "2026-10-01"})

    def codes(*levels):
        res = client.get("/api/shipments", params={"freetime_level": list(levels)})
        return {row["id"] for row in res.json()["data"]}

    assert codes("RED") == {clocks["RED"].shipment_id}
    assert codes("YELLOW", "RED") == {clocks["RED"].shipment_id, clocks["YELLOW"].shipment_id}
    assert cancelled.shipment_id not in codes("RED")
    assert client.get("/api/shipments", params={"freetime_level": "BLUE"}).status_code == 422
