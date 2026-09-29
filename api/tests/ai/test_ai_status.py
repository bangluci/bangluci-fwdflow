from datetime import UTC, datetime

from app.config import get_settings

USAGE = {"input_tokens": 900, "output_tokens": 100}


def test_status_reports_budget_exceeded_for_admin(client, login_as, make_extraction, monkeypatch):
    login_as("ADMIN")
    monkeypatch.setattr(get_settings(), "ai_daily_token_budget", 1000)
    make_extraction(status="REVIEW", usage=USAGE, processed_at=datetime.now(UTC))
    data = client.get("/api/ai/status").json()["data"]
    assert data == {"enabled": False, "reason": "DAILY_BUDGET_EXCEEDED", "tokens_today": 1000, "budget": 1000,
                    "provider": "anthropic", "provider_label": "Claude API (Anthropic, Mỹ)"}


def test_status_hides_token_numbers_for_docs(client, login_as):
    login_as("DOCS")
    data = client.get("/api/ai/status").json()["data"]
    assert data == {"enabled": True, "reason": None, "tokens_today": None, "budget": None,
                    "provider": "anthropic", "provider_label": "Claude API (Anthropic, Mỹ)"}


def test_status_names_the_gemini_provider(client, login_as, monkeypatch):
    login_as("DOCS")
    monkeypatch.setattr(get_settings(), "llm_provider", "gemini")
    data = client.get("/api/ai/status").json()["data"]
    assert (data["provider"], data["provider_label"]) == ("gemini", "Gemini API (Google, Mỹ)")


def test_status_reports_disabled_by_config(client, login_as, monkeypatch):
    login_as("DISPATCH")
    monkeypatch.setattr(get_settings(), "ai_external_enabled", False)
    data = client.get("/api/ai/status").json()["data"]
    assert (data["enabled"], data["reason"]) == (False, "DISABLED_BY_CONFIG")


def test_status_requires_internal_role(client, login_as):
    login_as("CUSTOMER")
    assert client.get("/api/ai/status").status_code == 403


def test_status_get_does_not_write_audit(client, db, login_as, make_extraction, monkeypatch):
    from sqlalchemy import func, select

    from app.audit.models import AuditLog

    login_as("ADMIN")
    monkeypatch.setattr(get_settings(), "ai_daily_token_budget", 1000)
    make_extraction(status="REVIEW", usage=USAGE, processed_at=datetime.now(UTC))
    client.get("/api/ai/status")
    count = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "AI_BUDGET_EXCEEDED"))
    assert count == 0
