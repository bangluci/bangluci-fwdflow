import pytest
from sqlalchemy import func, select

from app.ai.guard import reset_rate_limits
from app.ai.hs.models import HsSuggestionLog
from app.config import get_settings
from tests.hs.catalog import LAPTOP, pick

BODY = {"description": "Máy tính xách tay 14 inch, CPU Intel, RAM 16GB"}


@pytest.fixture(autouse=True)
def _fresh_limits():
    reset_rate_limits()


@pytest.mark.parametrize("role", ["DISPATCH", "ACCOUNTANT", "CUSTOMER", "DRIVER"])
def test_hs_suggest_forbidden_for_other_roles(client, login_as, role):
    login_as(role)
    assert client.post("/api/hs/suggest", json=BODY).status_code == 403


def test_hs_suggest_returns_items_for_docs(client, login_as, catalog, query_vector, claude):
    claude(pick(LAPTOP, "84713010"))
    login_as("DOCS")
    data = client.post("/api/hs/suggest", json=BODY).json()["data"]
    assert data["status"] == "OK" and data["degraded"] is False and data["log_id"]
    first = data["items"][0]
    assert first["code"] == LAPTOP and first["rank"] == 1 and first["explanation"]
    assert {"description_vi", "description_en", "rrf_score", "cosine", "needs_review"} <= first.keys()


def test_hs_suggest_rate_limited_after_60_per_hour(client, login_as, catalog, query_vector, claude):
    claude(pick(LAPTOP))
    login_as("DOCS")
    for _ in range(60):
        assert client.post("/api/hs/suggest", json=BODY).status_code == 200
    res = client.post("/api/hs/suggest", json=BODY)
    assert res.status_code == 429 and res.json()["error"]["code"] == "RATE_LIMITED"


def test_hs_suggest_ai_disabled_flag(client, db, login_as, catalog, query_vector, claude, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_external_enabled", False)
    claude(pick(LAPTOP))
    login_as("DOCS")
    res = client.post("/api/hs/suggest", json=BODY)
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_DISABLED"
    assert db.scalar(select(func.count()).select_from(HsSuggestionLog)) == 0


def test_hs_suggest_disabled_when_daily_budget_exceeded(client, login_as, catalog, query_vector, claude, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_daily_token_budget", 500)
    claude(pick(LAPTOP))
    login_as("DOCS")
    assert client.post("/api/hs/suggest", json=BODY).status_code == 200  # 1000 token vượt trần 500
    res = client.post("/api/hs/suggest", json=BODY)
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_DISABLED"


def test_hs_suggest_empty_description_400(client, login_as):
    login_as("DOCS")
    res = client.post("/api/hs/suggest", json={"description": "  "})
    assert res.status_code == 400 and res.json()["error"]["code"] == "DESCRIPTION_REQUIRED"


def test_hs_choice_records_chosen_code(client, db, login_as, catalog, query_vector, claude):
    claude(pick(LAPTOP))
    login_as("DOCS")
    log_id = client.post("/api/hs/suggest", json=BODY).json()["data"]["log_id"]
    res = client.post(f"/api/hs/suggestions/{log_id}/choice", json={"code": LAPTOP})
    assert res.status_code == 200
    log = db.get(HsSuggestionLog, log_id)
    assert log.chosen_code == LAPTOP and log.chosen_at is not None


def test_hs_choice_rejects_code_not_in_candidates(client, login_as, catalog, query_vector, claude):
    claude(pick(LAPTOP))
    login_as("DOCS")
    log_id = client.post("/api/hs/suggest", json=BODY).json()["data"]["log_id"]
    res = client.post(f"/api/hs/suggestions/{log_id}/choice", json={"code": "12345678"})
    assert res.status_code == 400 and res.json()["error"]["code"] == "CODE_NOT_IN_SUGGESTION"


def test_hs_choice_of_another_users_suggestion_is_404(client, login_as, catalog, query_vector, claude):
    claude(pick(LAPTOP))
    login_as("DOCS")
    log_id = client.post("/api/hs/suggest", json=BODY).json()["data"]["log_id"]
    client.cookies.clear()
    login_as("ADMIN")
    assert client.post(f"/api/hs/suggestions/{log_id}/choice", json={"code": LAPTOP}).status_code == 404
    assert client.post("/api/hs/suggestions/999999/choice", json={"code": LAPTOP}).status_code == 404


def test_item_saved_as_ai_accepted_after_suggestion(client, login_as, make_shipment, catalog, query_vector, claude):
    claude(pick(LAPTOP))
    login_as("DOCS")
    client.post("/api/hs/suggest", json=BODY)
    shipment = make_shipment()
    item = {"description": "Laptop", "quantity": "1", "hs_code": LAPTOP, "hs_source": "ai_accepted"}
    saved = client.post(f"/api/shipments/{shipment.id}/items", json=item).json()["data"]
    assert saved["hs_source"] == "ai_accepted"
    edited = client.patch(f"/api/shipments/{shipment.id}/items/{saved['id']}", json={"hs_code": "85171300"}).json()["data"]
    assert edited["hs_source"] == "manual"  # sửa mã tay thì nguồn về manual
