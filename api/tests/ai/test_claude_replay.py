import httpx2
import pytest

from app.ai.claude import (
    PermanentAIError,
    TransientAIError,
    call_structured,
    fixture_key,
    strict_schema,
    write_fixture,
)
from app.config import get_settings
from tests.ai.conftest import message_json
from tests.ai.test_claude import BLOCKS, Doc

SYSTEM, MAX_TOKENS = "hệ thống", 1000
TEXT = '{"name": "ABC", "total": 2, "lines": []}'


def _key():
    return fixture_key("extraction", get_settings().claude_model_extraction, SYSTEM, BLOCKS, strict_schema(Doc),
                       MAX_TOKENS)


def _call():
    return call_structured("extraction", SYSTEM, BLOCKS, Doc, MAX_TOKENS)


def test_replay_returns_recorded_response(replay_dir):
    write_fixture(replay_dir, _key(), response=message_json(text=TEXT))
    result = _call()
    assert result.parsed.name == "ABC" and result.usage["input_tokens"] == 100


def test_replay_missing_fixture_raises_with_key(replay_dir):
    with pytest.raises(PermanentAIError) as err:
        _call()
    assert err.value.type == "replay_missing" and _key() in err.value.message


@pytest.mark.parametrize(("transient", "expected"), [(True, TransientAIError), (False, PermanentAIError)])
def test_replay_reproduces_recorded_error_class(replay_dir, transient, expected):
    error = {"status": 529 if transient else 400, "type": "overloaded_error", "message": "lỗi ghi sẵn",
             "transient": transient}
    write_fixture(replay_dir, _key(), error=error)
    with pytest.raises(expected) as err:
        _call()
    assert err.value.status == error["status"] and err.value.message == "lỗi ghi sẵn"


def test_record_writes_fixture_then_replay_matches(mock_llm, replay_dir, monkeypatch):
    mock_llm(lambda request: httpx2.Response(200, json=message_json(text=TEXT)))
    monkeypatch.setattr(get_settings(), "llm_mode", "record")
    live = _call()
    assert (replay_dir / f"{_key()}.json").is_file()
    monkeypatch.setattr(get_settings(), "llm_mode", "replay")
    replayed = _call()
    assert replayed.parsed == live.parsed and replayed.usage == live.usage


def test_record_also_records_errors(mock_llm, replay_dir, monkeypatch):
    mock_llm(lambda request: httpx2.Response(529, json={"type": "error", "error": {"type": "overloaded_error",
                                                                                   "message": "quá tải"}}))
    monkeypatch.setattr(get_settings(), "llm_mode", "record")
    with pytest.raises(TransientAIError):
        _call()
    monkeypatch.setattr(get_settings(), "llm_mode", "replay")
    with pytest.raises(TransientAIError) as err:
        _call()
    assert err.value.status == 529


def test_fixture_key_ignores_dict_order():
    a = fixture_key("extraction", "m", "s", [{"type": "text", "text": "x"}], {"a": 1, "b": 2}, 10)
    b = fixture_key("extraction", "m", "s", [{"text": "x", "type": "text"}], {"b": 2, "a": 1}, 10)
    assert a == b
    assert a != fixture_key("extraction", "m", "s", [{"type": "text", "text": "y"}], {"a": 1, "b": 2}, 10)
