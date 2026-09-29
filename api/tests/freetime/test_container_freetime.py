"""`container_freetime(as_of)`: mỗi ca đối chiếu với số tính tay (tariff mẫu R1..R5 trong conftest)."""

from datetime import date

import pytest
from sqlalchemy import text

from app.shipments.models import ContainerEvent
from tests.freetime.conftest import MSK, RCL


@pytest.fixture(autouse=True)
def _standard_rules(ft):
    ft.standard_rules()


def _row(ft, container, as_of, fee_type):
    return ft.rows(as_of, container)[fee_type]


def test_dem_open_green_two_days_used(ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    rows = ft.rows("2026-11-02", container)
    dem = rows["DEM"]
    assert (dem["status"], dem["level"], dem["due_date"], dem["days_used"], dem["days_left"], dem["days_over"]) == \
        ("OPEN", "GREEN", date(2026, 11, 5), 2, 3, 0)
    assert (dem["rule_source"], dem["free_days"], dem["container_level"]) == ("RULE", 5, "GREEN")
    assert rows["DET"]["status"] == "NOT_STARTED"


def test_gate_out_closes_dem_and_starts_det(ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01", "GATE_OUT_FULL": "2026-11-05"})
    rows = ft.rows("2026-11-06", container)
    assert (rows["DEM"]["status"], rows["DEM"]["end_date"], rows["DEM"]["days_used"], rows["DEM"]["days_over"]) == \
        ("CLOSED", date(2026, 11, 5), 5, 0)
    det = rows["DET"]
    assert (det["status"], det["start_date"], det["days_used"], det["days_left"]) == ("OPEN", date(2026, 11, 5), 2, 5)


def test_no_rule_status(ft):
    container = ft.container(carrier_code=MSK, milestones={"DISCHARGED": "2026-11-01"})
    rows = ft.rows("2026-11-03", container)
    dem = rows["DEM"]
    assert (dem["status"], dem["level"], dem["free_days"], dem["rule_source"], dem["days_used"]) == \
        ("NO_RULE", "NO_RULE", None, "NONE", 3)
    assert rows["DET"]["status"] == "NOT_STARTED" and dem["container_level"] == "NO_RULE"


def test_container_level_is_worst_open_clock(ft):
    container = ft.container(milestones={"DISCHARGED": "2026-10-01", "GATE_OUT_FULL": "2026-10-04"})
    rows = ft.rows("2026-11-01", container)
    assert rows["DEM"]["status"] == "CLOSED" and rows["DET"]["level"] == "RED"
    assert {r["container_level"] for r in rows.values()} == {"RED"}


def test_container_level_null_when_all_clocks_closed(ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01", "GATE_OUT_FULL": "2026-11-03",
                                         "EMPTY_RETURNED": "2026-11-06"})
    rows = ft.rows("2026-11-20", container)
    assert {r["status"] for r in rows.values()} == {"CLOSED"}
    assert all(r["level"] is None and r["container_level"] is None for r in rows.values())


@pytest.mark.parametrize(("as_of", "used", "left", "level"), [
    ("2026-11-01", 1, 4, "GREEN"), ("2026-11-02", 2, 3, "GREEN"), ("2026-11-03", 3, 2, "YELLOW"),
    ("2026-11-05", 5, 0, "YELLOW"), ("2026-11-06", 6, -1, "RED"),
])
def test_level_thresholds_at_boundaries(ft, as_of, used, left, level):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    dem = _row(ft, container, as_of, "DEM")
    assert (dem["days_used"], dem["days_left"], dem["level"]) == (used, left, level)


def test_open_dem_fee_sums_tiers_until_as_of(ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    dem = _row(ft, container, "2026-11-08", "DEM")
    assert (dem["days_over"], dem["fee_amount"], dem["fee_currency"]) == (3, 6000, "USD")


def test_fee_spans_two_tiers(ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    dem = _row(ft, container, "2026-11-13", "DEM")
    assert (dem["days_over"], dem["fee_amount"]) == (8, 5 * 2000 + 3 * 4000)


def test_closed_det_fee_and_zero_fee_for_clean_dem(ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01", "GATE_OUT_FULL": "2026-11-03",
                                         "EMPTY_RETURNED": "2026-11-12"})
    rows = ft.rows("2026-11-20", container)
    assert (rows["DET"]["days_used"], rows["DET"]["days_over"], rows["DET"]["fee_amount"]) == (10, 3, 3000)
    assert (rows["DEM"]["days_used"], rows["DEM"]["days_over"], rows["DEM"]["fee_amount"]) == (3, 0, 0)


def test_combined_rule_has_single_open_clock(ft):
    container = ft.container(port_code="VNHPH", milestones={"DISCHARGED": "2026-11-01"})
    rows = ft.rows("2026-11-15", container)
    assert set(rows) == {"COMBINED"}
    combined = rows["COMBINED"]
    assert (combined["status"], combined["days_used"], combined["days_over"], combined["fee_amount"],
            combined["level"]) == ("OPEN", 15, 5, 7500, "RED")


def test_combined_closed_at_empty_return_crosses_tiers(ft):
    container = ft.container(port_code="VNHPH", milestones={"DISCHARGED": "2026-11-01",
                                                            "EMPTY_RETURNED": "2026-11-25"})
    combined = _row(ft, container, "2026-12-01", "COMBINED")
    assert (combined["status"], combined["days_over"], combined["fee_amount"]) == ("CLOSED", 15, 10 * 1500 + 5 * 3000)


def test_vnd_tiers_and_currency(ft):
    container = ft.container(port_code="VNCMT", container_type="20GP", milestones={"DISCHARGED": "2026-11-01"})
    dem = _row(ft, container, "2026-11-08", "DEM")
    assert (dem["days_over"], dem["fee_amount"], dem["fee_currency"]) == (4, 4 * 500000, "VND")


def test_override_wins_over_rule_and_uses_absolute_tiers(ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    ft.override(container.shipment_id, "DEM", 10)
    dem = _row(ft, container, "2026-11-12", "DEM")
    assert (dem["free_days"], dem["rule_source"], dem["due_date"], dem["days_over"]) == \
        (10, "OVERRIDE", date(2026, 11, 10), 2)
    assert dem["fee_amount"] == 2 * 4000  # ngày 11 và 12 rơi vào bậc "từ ngày 11"


def test_override_shorter_than_rule_prices_early_days_at_first_tier(ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    ft.override(container.shipment_id, "DEM", 3)
    dem = _row(ft, container, "2026-11-06", "DEM")
    assert (dem["days_over"], dem["fee_amount"]) == (3, 3 * 2000)


def test_override_combined_replaces_dem_det_clocks(ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    ft.override(container.shipment_id, "COMBINED", 14, source="CONTRACT")
    rows = ft.rows("2026-11-05", container)
    assert set(rows) == {"COMBINED"}
    assert (rows["COMBINED"]["free_days"], rows["COMBINED"]["rule_source"], rows["COMBINED"]["fee_amount"]) == \
        (14, "OVERRIDE", None)


def test_override_det_only_keeps_dem_from_rule(ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01", "GATE_OUT_FULL": "2026-11-05"})
    ft.override(container.shipment_id, "DET", 20)
    rows = ft.rows("2026-11-10", container)
    assert (rows["DEM"]["free_days"], rows["DEM"]["rule_source"], rows["DEM"]["status"]) == (5, "RULE", "CLOSED")
    det = rows["DET"]
    assert (det["free_days"], det["rule_source"], det["days_used"], det["days_left"], det["level"]) == \
        (20, "OVERRIDE", 6, 14, "GREEN")


def test_rule_version_is_chosen_by_discharged_date(ft):
    ft.rules(RCL, "VNSGN", "40HC", effective_from="2026-11-15", dem=(3, [(4, None, 5000, "USD")]),
             det=(7, [(8, None, 1000, "USD")]))
    old = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    new = ft.container(milestones={"DISCHARGED": "2026-11-20"})
    assert _row(ft, old, "2026-11-25", "DEM")["free_days"] == 5
    assert _row(ft, new, "2026-11-25", "DEM")["free_days"] == 3


def test_rule_not_yet_effective_at_discharge_is_no_rule(ft):
    ft.rules(MSK, "VNSGN", "40HC", effective_from="2026-12-01", dem=(5, [(6, None, 2000, "USD")]),
             det=(7, [(8, None, 1000, "USD")]))
    container = ft.container(carrier_code=MSK, milestones={"DISCHARGED": "2026-11-01"})
    assert _row(ft, container, "2026-11-03", "DEM")["status"] == "NO_RULE"


def test_not_started_before_arrival(ft):
    container = ft.container(status="IN_TRANSIT", eta="2026-12-01")
    rows = ft.rows("2026-11-02", container)
    assert {r["status"] for r in rows.values()} == {"NOT_STARTED"}
    assert all(r["level"] is None and r["container_level"] is None for r in rows.values())


def test_missing_data_when_eta_passed_without_discharge(ft):
    container = ft.container(status="IN_TRANSIT", eta="2026-10-30")
    rows = ft.rows("2026-11-02", container)
    assert (rows["DEM"]["status"], rows["DEM"]["level"], rows["DEM"]["container_level"]) == \
        ("MISSING_DATA", "MISSING_DATA", "MISSING_DATA")


def test_missing_data_when_shipment_already_arrived_even_if_eta_future(ft):
    container = ft.container(status="ARRIVED", eta="2026-12-01")
    assert _row(ft, container, "2026-11-02", "DEM")["status"] == "MISSING_DATA"


def test_det_is_never_missing_data(ft):
    container = ft.container(status="CLEARED", eta="2026-10-01")
    rows = ft.rows("2026-11-02", container)
    assert (rows["DEM"]["status"], rows["DET"]["status"]) == ("MISSING_DATA", "NOT_STARTED")


def test_lcl_shipments_have_no_clocks(ft):
    container = ft.container(load_type="LCL", milestones={"DISCHARGED": "2026-11-01"})
    assert ft.rows("2026-11-02", container) == {}


@pytest.mark.parametrize("status", ["CANCELLED", "COMPLETED"])
def test_finished_shipments_still_listed(ft, status):
    container = ft.container(status=status, milestones={"DISCHARGED": "2026-11-01"})
    assert _row(ft, container, "2026-11-02", "DEM")["shipment_status"] == status


def test_retime_moves_start_date(db, ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    discharged = db.query(ContainerEvent).filter_by(container_id=container.id, kind="DISCHARGED").one()
    db.add(ContainerEvent(container_id=container.id, kind="RETIME", adjusts_event_id=discharged.id,
                          occurred_at=ft.at("2026-11-03"), reason="Sửa giờ dỡ"))
    db.flush()
    dem = _row(ft, container, "2026-11-05", "DEM")
    assert (dem["start_date"], dem["days_used"]) == (date(2026, 11, 3), 3)


def test_void_gate_out_reopens_dem(db, ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01", "GATE_OUT_FULL": "2026-11-03"})
    gate = db.query(ContainerEvent).filter_by(container_id=container.id, kind="GATE_OUT_FULL").one()
    assert _row(ft, container, "2026-11-04", "DEM")["status"] == "CLOSED"
    db.add(ContainerEvent(container_id=container.id, kind="VOID", adjusts_event_id=gate.id,
                          occurred_at=ft.at("2026-11-03"), reason="Nhập nhầm"))
    db.flush()
    rows = ft.rows("2026-11-04", container)
    assert (rows["DEM"]["status"], rows["DEM"]["end_date"], rows["DET"]["status"]) == ("OPEN", None, "NOT_STARTED")


def test_zero_free_days_is_overdue_on_first_day(ft):
    ft.rules(MSK, "VNSGN", "40HC", dem=(0, [(1, None, 700, "USD")]), det=(0, [(1, None, 300, "USD")]))
    container = ft.container(carrier_code=MSK, milestones={"DISCHARGED": "2026-11-01"})
    dem = _row(ft, container, "2026-11-01", "DEM")
    assert (dem["days_used"], dem["days_left"], dem["level"], dem["due_date"], dem["fee_amount"]) == \
        (1, -1, "RED", date(2026, 10, 31), 700)


def test_milestone_dates_use_vietnam_calendar_day(db, ft):
    container = ft.container()
    db.add(ContainerEvent(container_id=container.id, kind="DISCHARGED",
                          occurred_at=ft.at("2026-10-31").replace(hour=18, minute=0)))  # 01:00 ngày 01/11 giờ VN
    db.flush()
    assert _row(ft, container, "2026-11-02", "DEM")["discharged_date"] == date(2026, 11, 1)


def test_containers_are_independent(ft):
    fresh = ft.container(milestones={"DISCHARGED": "2026-11-05"})
    old = ft.container(milestones={"DISCHARGED": "2026-10-01"})
    assert _row(ft, fresh, "2026-11-06", "DEM")["level"] == "GREEN"
    assert _row(ft, old, "2026-11-06", "DEM")["level"] == "RED"


def test_fee_is_null_without_tiers_or_start(ft):
    not_started = ft.container(status="IN_TRANSIT", eta="2026-12-01")
    no_rule = ft.container(carrier_code=MSK, milestones={"DISCHARGED": "2026-11-01"})
    for container in (not_started, no_rule):
        for row in ft.rows("2026-11-03", container).values():
            assert row["fee_amount"] is None and row["fee_currency"] is None


def test_view_reads_function_with_nlq_today(db, ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    db.execute(text("SELECT set_config('app.as_of', '2026-11-08', true)"))
    row = db.execute(text("SELECT * FROM nlq.v_container_freetime WHERE container_id = :c AND fee_type = 'DEM'"),
                     {"c": container.id}).mappings().one()
    assert (row["days_used"], row["days_over"], row["fee_amount"]) == (8, 3, 6000)


def test_view_columns_all_have_comments(db):
    missing = db.execute(text("""
        SELECT a.attname FROM pg_attribute a
        WHERE a.attrelid = 'nlq.v_container_freetime'::regclass AND a.attnum > 0 AND NOT a.attisdropped
          AND coalesce(col_description(a.attrelid, a.attnum), '') = ''""")).scalars().all()
    assert missing == []


def test_view_has_no_pii_columns(db):
    names = db.execute(text("SELECT attname FROM pg_attribute WHERE attrelid = 'nlq.v_container_freetime'::regclass "
                            "AND attnum > 0")).scalars().all()
    assert not [n for n in names if any(word in n for word in ("phone", "address", "tax", "tracking"))]


def test_container_freetime_is_hardened(db):
    row = db.execute(text("SELECT prosecdef, proconfig FROM pg_proc WHERE proname = 'container_freetime'")).one()
    assert row.prosecdef is True and "search_path=pg_catalog, public, pg_temp" in row.proconfig
    assert db.scalar(text("SELECT has_function_privilege('public', 'container_freetime(date)', 'EXECUTE')")) is False
