from datetime import date

import pytest
from sqlalchemy import func, select

from app.audit.models import AuditLog
from app.freetime.models import FreeTimeRule, FreeTimeTier

DEM = {"fee_type": "DEM", "free_days": 5, "tiers": [{"from_day": 6, "to_day": 10, "rate_amount": 2000,
                                                     "currency": "USD"},
                                                    {"from_day": 11, "to_day": None, "rate_amount": 4000,
                                                     "currency": "USD"}]}
DET = {"fee_type": "DET", "free_days": 7, "tiers": [{"from_day": 8, "to_day": None, "rate_amount": 1000,
                                                     "currency": "USD"}]}
COMBINED = {"fee_type": "COMBINED", "free_days": 10, "tiers": [{"from_day": 11, "to_day": None, "rate_amount": 1500,
                                                               "currency": "USD"}]}


def _body(ft, rules, effective_from="2026-12-01", **overrides):
    return {"carrier_id": ft.carrier().id, "port_id": ft.port().id, "container_type": "40HC",
            "effective_from": effective_from, "rules": rules, **overrides}


def _post(client, body):
    return client.post("/api/freetime/rules", json=body)


def _count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_post_dem_det_set_creates_two_rules_with_tiers(client, db, login_as, ft):
    login_as("DOCS")
    res = _post(client, _body(ft, [DEM, DET]))
    assert res.status_code == 201
    data = res.json()["data"]
    assert [(r["fee_type"], r["free_days"], len(r["tiers"])) for r in data["rules"]] == [("DEM", 5, 2), ("DET", 7, 1)]
    assert data["editable"] is True and (_count(db, FreeTimeRule), _count(db, FreeTimeTier)) == (2, 3)


def test_post_combined_set_creates_one_rule(client, db, login_as, ft):
    login_as("DOCS")
    assert _post(client, _body(ft, [COMBINED])).status_code == 201
    assert _count(db, FreeTimeRule) == 1


def test_post_bad_tiers_400_invalid_tiers(client, login_as, ft):
    login_as("DOCS")
    bad = {**DET, "tiers": [{"from_day": 9, "to_day": None, "rate_amount": 1000, "currency": "USD"}]}  # free 7 → phải 8
    res = _post(client, _body(ft, [DEM, bad]))
    error = res.json()["error"]
    assert res.status_code == 400 and error["code"] == "INVALID_TIERS"
    assert error["details"]["reason"] == "FIRST_TIER_START"


@pytest.mark.parametrize("rules", [[COMBINED, DEM], [DEM]], ids=["combined-with-dem", "lone-dem"])
def test_post_invalid_rule_set_400(client, login_as, ft, rules):
    login_as("DOCS")
    res = _post(client, _body(ft, rules))
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_RULE_SET"


def test_post_other_mode_same_effective_date_409(client, login_as, ft):
    login_as("DOCS")
    assert _post(client, _body(ft, [COMBINED])).status_code == 201
    res = _post(client, _body(ft, [DEM, DET]))
    assert res.status_code == 409 and res.json()["error"]["code"] == "RULE_VERSION_EXISTS"


def test_post_same_key_same_date_409(client, login_as, ft):
    login_as("DOCS")
    assert _post(client, _body(ft, [DEM, DET])).status_code == 201
    assert _post(client, _body(ft, [DEM, DET])).status_code == 409


def test_post_new_effective_date_is_a_new_version(client, login_as, ft):
    login_as("DOCS")
    assert _post(client, _body(ft, [DEM, DET], effective_from="2026-12-01")).status_code == 201
    assert _post(client, _body(ft, [COMBINED], effective_from="2027-01-01")).status_code == 201


def test_post_inactive_carrier_400_inactive_reference(client, db, login_as, ft):
    login_as("DOCS")
    carrier = ft.carrier()
    carrier.active = False
    db.flush()
    res = _post(client, _body(ft, [DEM, DET]))
    assert res.status_code == 400 and res.json()["error"]["code"] == "INACTIVE_REFERENCE"


def test_post_free_days_out_of_range_422(client, login_as, ft):
    login_as("DOCS")
    assert _post(client, _body(ft, [{**COMBINED, "free_days": 366}])).status_code == 422


def test_get_groups_versions_and_marks_editable(client, login_as, ft):
    login_as("DOCS")
    _post(client, _body(ft, [DEM, DET], effective_from="2026-01-01"))
    _post(client, _body(ft, [COMBINED], effective_from="2099-01-01"))
    versions = client.get("/api/freetime/rules").json()["data"]
    assert [(v["effective_from"], v["editable"], len(v["rules"])) for v in versions] == [
        ("2099-01-01", True, 1), ("2026-01-01", False, 2)]
    assert versions[0]["carrier_name"] and versions[0]["port_code"] == "VNSGN"
    assert client.get("/api/freetime/rules", params={"port_id": 999999}).json()["data"] == []


def test_delete_future_version_removes_rules_and_tiers(client, db, login_as, ft):
    login_as("DOCS")
    versions = _post(client, _body(ft, [DEM, DET], effective_from="2099-01-01")).json()["data"]
    assert client.delete(f"/api/freetime/rules/{versions['rules'][0]['id']}").status_code == 200
    assert (_count(db, FreeTimeRule), _count(db, FreeTimeTier)) == (0, 0)


def test_delete_effective_version_409_rule_already_effective(client, login_as, ft):
    login_as("DOCS")
    created = _post(client, _body(ft, [DEM, DET], effective_from="2026-01-01")).json()["data"]
    res = client.delete(f"/api/freetime/rules/{created['rules'][0]['id']}")
    assert res.status_code == 409 and res.json()["error"]["code"] == "RULE_ALREADY_EFFECTIVE"


def test_delete_unknown_rule_404(client, login_as):
    login_as("DOCS")
    assert client.delete("/api/freetime/rules/999999").status_code == 404


def test_effective_today_counts_as_effective(client, db, login_as, ft):
    login_as("DOCS")
    today = db.scalar(select(func.nlq_today()))
    created = _post(client, _body(ft, [COMBINED], effective_from=today.isoformat())).json()["data"]
    assert created["editable"] is False and isinstance(today, date)
    assert client.delete(f"/api/freetime/rules/{created['rules'][0]['id']}").status_code == 409


def test_rules_write_permissions_and_audit(client, db, login_as, ft):
    user = login_as("DOCS")
    assert _post(client, _body(ft, [DEM, DET])).status_code == 201
    entities = {row.entity for row in db.scalars(select(AuditLog).where(AuditLog.actor_id == user.id))}
    assert {"free_time_rule", "free_time_tier"} <= entities
    for role in ("DISPATCH", "ACCOUNTANT"):
        client.cookies.clear()
        login_as(role)
        assert _post(client, _body(ft, [COMBINED], effective_from="2027-05-01")).status_code == 403
        assert client.get("/api/freetime/rules").status_code == 200
