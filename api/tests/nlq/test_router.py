import pytest

from app.ai.nlq.models import NlQueryLog
from app.ai.nlq.service import AnswerDraft, SqlDraft
from app.config import get_settings

COUNT = SqlDraft(sql="SELECT count(*) AS so_lo FROM nlq.v_shipments", no_permission=False)
ANSWER = AnswerDraft(answer="Có 0 lô.", chart=None)
BODY = {"question": "Có bao nhiêu lô?"}


def test_ask_returns_the_documented_shape(client, login_as, llm):
    llm(COUNT, ANSWER)
    login_as("DOCS")
    data = client.post("/api/assistant/ask", json=BODY).json()["data"]
    assert set(data) == {"log_id", "sql", "columns", "rows", "truncated", "answer", "answer_checked", "chart", "message"}
    assert data["rows"] == [[0]] and data["answer"] == "Có 0 lô." and data["answer_checked"] is True


def test_assistant_rate_limit_429(client, login_as, llm):
    llm(COUNT, ANSWER)
    login_as("ACCOUNTANT")
    for _ in range(30):
        assert client.post("/api/assistant/ask", json=BODY).status_code == 200
    res = client.post("/api/assistant/ask", json=BODY)
    assert res.status_code == 429 and res.json()["error"]["code"] == "RATE_LIMITED"


def test_assistant_ai_disabled(client, db, login_as, llm, monkeypatch):
    llm(COUNT, ANSWER)
    monkeypatch.setattr(get_settings(), "ai_external_enabled", False)
    login_as("DOCS")
    res = client.post("/api/assistant/ask", json=BODY)
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_DISABLED"
    assert db.query(NlQueryLog).count() == 0


def test_assistant_disabled_when_daily_budget_exceeded(client, login_as, llm, monkeypatch):
    llm(COUNT, ANSWER)
    monkeypatch.setattr(get_settings(), "ai_daily_token_budget", 500)
    login_as("DOCS")
    assert client.post("/api/assistant/ask", json=BODY).status_code == 200  # 1000 token vượt trần 500
    res = client.post("/api/assistant/ask", json=BODY)
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_DISABLED"


@pytest.mark.parametrize("role", ["CUSTOMER", "DRIVER"])
def test_customer_and_driver_forbidden(client, login_as, role):
    login_as(role)
    assert client.post("/api/assistant/ask", json=BODY).status_code == 403


@pytest.mark.parametrize("question", ["ab", "x" * 501, ""])
def test_question_length_422(client, login_as, question):
    login_as("DOCS")
    assert client.post("/api/assistant/ask", json={"question": question}).status_code == 422


def test_rating_saved(client, db, login_as, llm):
    llm(COUNT, ANSWER)
    login_as("DOCS")
    log_id = client.post("/api/assistant/ask", json=BODY).json()["data"]["log_id"]
    assert client.post(f"/api/assistant/{log_id}/rating", json={"correct": True}).json()["data"]["correct"] is True
    db.expire_all()
    assert db.get(NlQueryLog, log_id).user_rating is True
    client.post(f"/api/assistant/{log_id}/rating", json={"correct": False})
    db.expire_all()
    assert db.get(NlQueryLog, log_id).user_rating is False


def test_rating_other_user_404(client, login_as, llm):
    llm(COUNT, ANSWER)
    login_as("DOCS")
    log_id = client.post("/api/assistant/ask", json=BODY).json()["data"]["log_id"]
    client.cookies.clear()
    login_as("ADMIN")
    assert client.post(f"/api/assistant/{log_id}/rating", json={"correct": True}).status_code == 404
    assert client.post("/api/assistant/999999/rating", json={"correct": True}).status_code == 404
