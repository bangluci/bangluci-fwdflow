import anthropic
import httpx2
import pytest

from app.ai import claude
from app.ai.guard import reset_rate_limits
from app.config import get_settings


def message_json(text: str = "{}", stop_reason: str = "end_turn", usage: dict | None = None,
                 content: list | None = None) -> dict:
    """Body của POST /v1/messages đủ để SDK dựng BetaMessage."""
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5",
        "content": [{"type": "text", "text": text}] if content is None else content,
        "stop_reason": stop_reason, "stop_sequence": None,
        "usage": usage or {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0,
                           "cache_read_input_tokens": 5},
    }


def error_json(error_type: str, message: str) -> dict:
    return {"type": "error", "error": {"type": error_type, "message": message}}


@pytest.fixture
def live_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_mode", "live")


@pytest.fixture
def mock_llm(monkeypatch, live_mode):
    """`mock_llm(handler)` gắn client dùng MockTransport (không gọi mạng); trả danh sách request đã gửi."""

    def install(handler) -> list[httpx2.Request]:
        seen: list[httpx2.Request] = []

        def recording(request: httpx2.Request) -> httpx2.Response:
            seen.append(request)
            return handler(request)

        http_client = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(recording))
        client = anthropic.Anthropic(api_key="test-key", max_retries=0, http_client=http_client)
        monkeypatch.setattr(claude, "get_client", lambda: client)
        return seen

    return install


@pytest.fixture
def replay_dir(tmp_path, monkeypatch):
    """Chế độ replay trên thư mục fixture tạm."""
    monkeypatch.setattr(get_settings(), "llm_mode", "replay")
    monkeypatch.setattr(get_settings(), "llm_fixture_dir", tmp_path / "llm")
    return tmp_path / "llm"


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    reset_rate_limits()
