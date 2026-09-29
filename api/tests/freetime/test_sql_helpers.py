import pytest
from sqlalchemy import select, text

from app.events import effective_events
from app.shipments.models import ContainerEvent


def _one(db, sql, **params):
    return db.scalar(text(sql), params)


def test_nlq_today_uses_app_as_of_guc(db):
    db.execute(text("SELECT set_config('app.as_of', '2026-11-03', true)"))
    assert str(_one(db, "SELECT nlq_today()")) == "2026-11-03"


def test_nlq_today_falls_back_to_vn_calendar_date(db):
    assert _one(db, "SELECT nlq_today() = (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date") is True


def test_nlq_today_ignores_empty_guc(db):
    db.execute(text("SELECT set_config('app.as_of', '', true)"))
    assert _one(db, "SELECT nlq_today() = (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date") is True


def test_level_rank_orders_red_yellow_no_rule_missing_data_green(db):
    ranks = [_one(db, "SELECT freetime_level_rank(:l)", l=level)
             for level in ("RED", "YELLOW", "NO_RULE", "MISSING_DATA", "GREEN")]
    assert ranks == sorted(ranks, reverse=True) and len(set(ranks)) == 5


@pytest.mark.parametrize("level", [None, "BLUE", ""])
def test_level_rank_is_null_for_other_values(db, level):
    assert _one(db, "SELECT freetime_level_rank(:l)", l=level) is None


def _milestones(db, container_id):
    rows = db.execute(text("SELECT kind, occurred_at, event_id FROM effective_container_milestones "
                           "WHERE container_id = :c ORDER BY kind"), {"c": container_id}).all()
    return {row.kind: row for row in rows}


def _event(db, container_id, kind, when, adjusts=None):
    event = ContainerEvent(container_id=container_id, kind=kind, occurred_at=when, adjusts_event_id=adjusts,
                           reason="test" if adjusts else None)
    db.add(event)
    db.flush()
    return event


def test_milestones_apply_void_and_retime(db, ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    base = _milestones(db, container.id)["DISCHARGED"]
    later = _event(db, container.id, "RETIME", ft.at("2026-11-03"), adjusts=base.event_id)
    assert _milestones(db, container.id)["DISCHARGED"].occurred_at == ft.at("2026-11-03")
    _event(db, container.id, "VOID", ft.at("2026-11-03"), adjusts=later.id)  # huỷ RETIME: giờ gốc trở lại
    assert _milestones(db, container.id)["DISCHARGED"].occurred_at == ft.at("2026-11-01")
    _event(db, container.id, "VOID", ft.at("2026-11-01"), adjusts=base.event_id)  # huỷ mốc: biến mất
    assert "DISCHARGED" not in _milestones(db, container.id)


def test_milestones_ignore_non_milestone_kinds(db, ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01"})
    assert set(_milestones(db, container.id)) == {"DISCHARGED"}


def test_milestones_match_python_effective_events(db, ft):
    container = ft.container(milestones={"DISCHARGED": "2026-11-01", "GATE_OUT_FULL": "2026-11-06"})
    events = {e.kind: e for e in db.scalars(select(ContainerEvent).where(ContainerEvent.container_id == container.id))}
    first = _event(db, container.id, "RETIME", ft.at("2026-11-02"), adjusts=events["DISCHARGED"].id)
    _event(db, container.id, "RETIME", ft.at("2026-11-04"), adjusts=events["DISCHARGED"].id)
    _event(db, container.id, "VOID", ft.at("2026-11-02"), adjusts=first.id)
    every = list(db.scalars(select(ContainerEvent).where(ContainerEvent.container_id == container.id)))
    expected = {e.kind: e.occurred_at for e in effective_events(every)}
    actual = {kind: row.occurred_at for kind, row in _milestones(db, container.id).items()}
    assert actual == expected and actual["DISCHARGED"] == ft.at("2026-11-04")


def test_helper_functions_not_executable_by_public(db):
    for signature in ("nlq_today()", "freetime_level_rank(text)", "container_freetime(date)"):
        assert _one(db, "SELECT has_function_privilege('public', :s, 'EXECUTE')", s=signature) is False


def test_helpers_use_fixed_search_path(db):
    configs = db.execute(text("SELECT proname, proconfig FROM pg_proc WHERE proname IN "
                              "('nlq_today', 'freetime_level_rank', 'container_freetime')")).all()
    assert len(configs) == 3
    assert all(any("search_path=pg_catalog, public, pg_temp" in c for c in row.proconfig) for row in configs)
