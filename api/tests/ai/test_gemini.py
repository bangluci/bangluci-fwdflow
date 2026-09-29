import json

import httpx2
import pytest
from pydantic import BaseModel

from app.ai import gemini
from app.ai.claude import PermanentAIError, TransientAIError, call_structured, strict_schema
from app.config import get_settings


class Doc(BaseModel):
    name: str | None
    total: int | None


BLOCKS = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}},
          {"type": "text", "text": "<document>x</document>"}]
OK = {"candidates": [{"content": {"parts": [{"text": '{"name": "ABC", "total": 3}'}]}, "finishReason": "STOP"}],
      "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 15, "thoughtsTokenCount": 5}}


@pytest.fixture
def gemini_live(monkeypatch):
    """Chế độ live với Gemini, HTTP được thay bằng MockTransport; trả danh sách request đã gửi."""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "llm_mode", "live")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    def install(handler) -> list[httpx2.Request]:
        seen: list[httpx2.Request] = []

        def recording(request: httpx2.Request) -> httpx2.Response:
            seen.append(request)
            return handler(request)

        monkeypatch.setattr(gemini, "_client", lambda: httpx2.Client(transport=httpx2.MockTransport(recording)))
        return seen

    return install


def _call():
    return call_structured("extraction", "hệ thống", BLOCKS, Doc, 1000)


def test_request_shape_and_json_mode(gemini_live):
    seen = gemini_live(lambda request: httpx2.Response(200, json=OK))
    _call()
    request = seen[0]
    assert str(request.url).endswith("/models/gemini-2.5-flash:generateContent")
    assert request.headers["x-goog-api-key"] == "test-key"
    body = json.loads(request.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "hệ thống"
    parts = body["contents"][0]["parts"]
    assert parts[0] == {"inlineData": {"mimeType": "image/jpeg", "data": "QUJD"}} and parts[1]["text"].startswith("<document>")
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json" and config["maxOutputTokens"] == 1000
    assert config["responseJsonSchema"] == strict_schema(Doc) and config["responseJsonSchema"]["additionalProperties"] is False
    assert config["thinkingConfig"] == {"thinkingBudget": 0}


def test_parses_json_and_maps_usage(gemini_live):
    gemini_live(lambda request: httpx2.Response(200, json=OK))
    result = _call()
    assert result.parsed.name == "ABC" and result.parsed.total == 3
    assert result.stop_reason == "end_turn" and result.validation_error is None
    assert result.usage == {"input_tokens": 120, "output_tokens": 20, "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0}
    assert result.config["provider"] == "gemini" and result.config["model"] == "gemini-2.5-flash"


def test_max_tokens_is_not_parsed(gemini_live):
    body = {"candidates": [{"content": {"parts": [{"text": '{"name": "A'}]}, "finishReason": "MAX_TOKENS"}]}
    gemini_live(lambda request: httpx2.Response(200, json=body))
    result = _call()
    assert result.parsed is None and result.stop_reason == "max_tokens" and result.raw_text == '{"name": "A'


@pytest.mark.parametrize("body", [
    {"candidates": [{"finishReason": "SAFETY"}]},
    {"promptFeedback": {"blockReason": "SAFETY"}},
])
def test_blocked_answers_are_refusals(gemini_live, body):
    gemini_live(lambda request: httpx2.Response(200, json=body))
    result = _call()
    assert result.parsed is None and result.stop_reason == "refusal"


@pytest.mark.parametrize(("status", "state", "error_class"), [
    (429, "RESOURCE_EXHAUSTED", TransientAIError), (503, "UNAVAILABLE", TransientAIError),
    (400, "INVALID_ARGUMENT", PermanentAIError), (403, "PERMISSION_DENIED", PermanentAIError),
])
def test_http_errors_are_classified(gemini_live, status, state, error_class):
    gemini_live(lambda request: httpx2.Response(status, json={"error": {"code": status, "status": state, "message": "x"}}))
    with pytest.raises(error_class) as err:
        _call()
    assert err.value.status == status and err.value.type == state


def test_connection_error_is_transient(gemini_live):
    def boom(request):
        raise httpx2.ConnectError("no route")

    gemini_live(boom)
    with pytest.raises(TransientAIError):
        _call()


def test_missing_api_key_is_permanent(gemini_live, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    with pytest.raises(PermanentAIError) as err:
        _call()
    assert err.value.type == "no_api_key"


def test_live_call_blocked_when_external_ai_disabled(gemini_live, monkeypatch):
    seen = gemini_live(lambda request: httpx2.Response(200, json=OK))
    monkeypatch.setattr(get_settings(), "ai_external_enabled", False)
    with pytest.raises(PermanentAIError) as err:
        _call()
    assert err.value.type == "ai_disabled" and seen == []


def test_unsupported_block_type_is_permanent(gemini_live):
    gemini_live(lambda request: httpx2.Response(200, json=OK))
    with pytest.raises(PermanentAIError) as err:
        call_structured("hs", "s", [{"type": "document", "source": {}}], Doc, 100)
    assert err.value.type == "unsupported_block"


def test_record_then_replay_roundtrip_without_network(gemini_live, monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_fixture_dir", tmp_path / "llm")
    seen = gemini_live(lambda request: httpx2.Response(200, json=OK))
    monkeypatch.setattr(settings, "llm_mode", "record")
    recorded = _call()
    monkeypatch.setattr(settings, "llm_mode", "replay")
    replayed = _call()
    assert len(seen) == 1 and replayed.parsed == recorded.parsed and replayed.usage == recorded.usage


def test_replay_without_fixture_is_permanent(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "llm_mode", "replay")
    monkeypatch.setattr(settings, "llm_fixture_dir", tmp_path / "empty")
    with pytest.raises(PermanentAIError) as err:
        _call()
    assert err.value.type == "replay_missing"
