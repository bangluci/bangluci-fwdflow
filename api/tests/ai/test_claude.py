import json
from decimal import Decimal

import httpx2
import pytest
from pydantic import BaseModel

from app.ai.claude import (
    PermanentAIError,
    TransientAIError,
    call_structured,
    strict_schema,
)
from app.config import get_settings
from tests.ai.conftest import error_json, message_json


class Line(BaseModel):
    description: str | None
    quantity: Decimal | None


class Doc(BaseModel):
    name: str | None
    total: int | None
    lines: list[Line]


BLOCKS = [{"type": "text", "text": "<document>x</document>"}]


def _call():
    return call_structured("extraction", "hệ thống", BLOCKS, Doc, 1000)


def _respond(**kwargs):
    return lambda request: httpx2.Response(200, json=message_json(**kwargs))


def test_call_structured_parses_end_turn_json(mock_llm):
    mock_llm(_respond(text='{"name": "ABC", "total": 3, "lines": [{"description": "x", "quantity": "1.50"}]}'))
    result = _call()
    assert result.parsed.name == "ABC" and result.parsed.lines[0].quantity == Decimal("1.50")
    assert result.stop_reason == "end_turn" and result.validation_error is None


def test_call_structured_returns_refusal_without_parsing(mock_llm):
    mock_llm(_respond(stop_reason="refusal", content=[]))
    result = _call()
    assert result.parsed is None and result.stop_reason == "refusal" and result.raw_text == ""


def test_call_structured_returns_max_tokens_without_parsing(mock_llm):
    mock_llm(_respond(text='{"name": "AB', stop_reason="max_tokens"))
    result = _call()
    assert result.parsed is None and result.raw_text == '{"name": "AB' and result.validation_error is None


def test_call_structured_reports_schema_violation(mock_llm):
    mock_llm(_respond(text='{"name": 5, "total": null, "lines": []}'))
    result = _call()
    assert result.parsed is None and "name" in result.validation_error


@pytest.mark.parametrize(("handler", "status"), [
    (lambda r: httpx2.Response(429, json=error_json("rate_limit_error", "chậm lại")), 429),
    (lambda r: httpx2.Response(500, json=error_json("api_error", "lỗi máy chủ")), 500),
    (lambda r: httpx2.Response(529, json=error_json("overloaded_error", "quá tải")), 529),
    (lambda r: (_ for _ in ()).throw(httpx2.ReadTimeout("hết giờ")), 0),
    (lambda r: (_ for _ in ()).throw(httpx2.ConnectError("mất mạng")), 0),
], ids=["429", "500", "529", "timeout", "connection"])
def test_transient_errors_are_classified(mock_llm, handler, status):
    mock_llm(handler)
    with pytest.raises(TransientAIError) as err:
        _call()
    assert err.value.status == status and err.value.message


def test_400_is_permanent_with_readable_message(mock_llm):
    mock_llm(lambda r: httpx2.Response(400, json=error_json("invalid_request_error", "schema không hợp lệ")))
    with pytest.raises(PermanentAIError) as err:
        _call()
    assert err.value.status == 400 and err.value.type == "invalid_request_error"
    assert "schema không hợp lệ" in err.value.message


def test_401_is_permanent(mock_llm):
    mock_llm(lambda r: httpx2.Response(401, json=error_json("authentication_error", "key sai")))
    with pytest.raises(PermanentAIError):
        _call()


def test_request_has_fallbacks_default_and_beta_header(mock_llm):
    seen = mock_llm(_respond(text='{"name": null, "total": null, "lines": []}'))
    _call()
    request = seen[0]
    body = json.loads(request.content)
    assert "server-side-fallback-2026-07-01" in request.headers["anthropic-beta"]
    assert body["fallbacks"] == "default" and body["model"] == "claude-opus-5" and body["max_tokens"] == 1000
    assert body["output_config"]["effort"] == "high"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert not {"temperature", "top_p", "top_k", "thinking"} & body.keys()


def test_usage_and_latency_recorded(mock_llm):
    mock_llm(_respond(text='{"name": null, "total": null, "lines": []}',
                      usage={"input_tokens": 1200, "output_tokens": 80, "cache_creation_input_tokens": 7,
                             "cache_read_input_tokens": 900}))
    result = _call()
    assert result.usage == {"input_tokens": 1200, "output_tokens": 80, "cache_read_input_tokens": 900,
                            "cache_creation_input_tokens": 7}
    assert result.latency_ms >= 0
    assert result.config["feature"] == "extraction" and len(result.config["schema_version"]) == 12


def test_live_call_blocked_when_external_ai_disabled(mock_llm, monkeypatch):
    mock_llm(_respond())
    monkeypatch.setattr(get_settings(), "ai_external_enabled", False)
    with pytest.raises(PermanentAIError) as err:
        _call()
    assert err.value.type == "ai_disabled"


def test_strict_schema_closes_every_object_and_requires_all_keys():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert node["required"] == list(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    schema = strict_schema(Doc)
    assert "$defs" not in json.dumps(schema) and "$ref" not in json.dumps(schema)
    walk(schema)
