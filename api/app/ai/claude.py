"""Lớp gọi Claude dùng chung cho cả 3 tính năng AI: structured output, phân loại lỗi, record / replay cho test."""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types.beta import BetaMessage
from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger("fwdflow.ai")

FALLBACK_BETA = "server-side-fallback-2026-07-01"
TIMEOUT_SECONDS = 180.0
DEFAULT_EFFORT = "high"


class AIError(Exception):
    def __init__(self, status: int, error_type: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.type = error_type
        self.message = message


class TransientAIError(AIError):
    """429, 5xx (gồm 529), timeout, lỗi mạng: được phép thử lại."""


class PermanentAIError(AIError):
    """400 và các 4xx khác: không thử lại; `message` giữ thông điệp của API để hiện cho người dùng."""


@dataclass(frozen=True)
class StructuredResult:
    parsed: BaseModel | None
    raw_text: str
    stop_reason: str | None
    latency_ms: int
    usage: dict[str, int]
    config: dict[str, Any]
    validation_error: str | None = None


@cache
def get_client() -> anthropic.Anthropic:
    key = get_settings().anthropic_api_key
    if not key:
        raise PermanentAIError(0, "no_api_key", "Chưa cấu hình ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=key, max_retries=0, timeout=TIMEOUT_SECONDS)


def strict_schema(model: type[BaseModel]) -> dict:
    """JSON schema cho `output_config.format`: inline `$defs`, mọi object đóng và `required` đủ mọi key."""
    schema = model.model_json_schema(mode="serialization")
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
        out = {key: walk(value) for key, value in node.items() if key not in ("title", "default")}
        if out.get("type") == "object" or "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out.get("properties", {}))
        return out

    return walk(schema)


def schema_version(schema: dict) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:12]


def fixture_key(feature: str, model: str, system: str, content_blocks: list[dict], schema: dict,
                max_tokens: int) -> str:
    payload = {"feature": feature, "model": model, "system": system, "content": content_blocks, "schema": schema,
               "max_tokens": max_tokens}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_fixture(directory: Path, key: str, response: dict | None = None, error: dict | None = None,
                  request: dict | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.json"
    body = {"key": key, "request": request, "response": response, "error": error}
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _raise_recorded(error: dict) -> None:
    cls = TransientAIError if error["transient"] else PermanentAIError
    raise cls(error["status"], error["type"], error["message"])


def _read_fixture(directory: Path, key: str) -> BetaMessage:
    path = directory / f"{key}.json"
    if not path.is_file():
        raise PermanentAIError(0, "replay_missing", f"Thiếu fixture LLM {key}")
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("error"):
        _raise_recorded(body["error"])
    return BetaMessage.model_validate(body["response"])


def _classify(exc: Exception) -> AIError:
    """Bắt từ cụ thể tới chung: 429 / lỗi kết nối / 5xx là tạm thời, còn lại là vĩnh viễn."""
    if isinstance(exc, anthropic.APIStatusError):
        body = exc.body if isinstance(exc.body, dict) else {}
        detail = body.get("error", {}) if isinstance(body.get("error"), dict) else {}
        error_type = detail.get("type") or type(exc).__name__
        message = f"{error_type}: {detail.get('message') or exc.message}"
        transient = isinstance(exc, anthropic.RateLimitError) or exc.status_code >= 500
        return (TransientAIError if transient else PermanentAIError)(exc.status_code, error_type, message)
    if isinstance(exc, anthropic.APIConnectionError):  # gồm APITimeoutError
        return TransientAIError(0, type(exc).__name__, "Không kết nối được tới Claude API")
    raise exc


def _live_call(request: dict) -> BetaMessage:
    try:
        return get_client().beta.messages.create(**request)
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        raise _classify(exc) from exc


def _obtain(mode: str, key: str, request: dict, meta: dict) -> BetaMessage:
    settings = get_settings()
    if mode == "replay":
        return _read_fixture(settings.llm_fixture_dir, key)
    if not settings.ai_external_enabled:
        raise PermanentAIError(0, "ai_disabled", "Tính năng AI đang tắt")
    try:
        message = _live_call(request)
    except AIError as exc:
        if mode == "record":
            error = {"status": exc.status, "type": exc.type, "message": exc.message,
                     "transient": isinstance(exc, TransientAIError)}
            write_fixture(settings.llm_fixture_dir, key, error=error, request=meta)
        raise
    if mode == "record":
        write_fixture(settings.llm_fixture_dir, key, response=message.model_dump(mode="json"), request=meta)
    return message


def _usage(message: BetaMessage) -> dict[str, int]:
    usage = message.usage
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }


def _parse(schema_model: type[BaseModel], stop_reason: str | None, text: str) -> tuple[BaseModel | None, str | None]:
    """Chỉ parse khi `end_turn`; refusal hoặc max_tokens giữ nguyên `raw_text`, `parsed=None`."""
    if stop_reason != "end_turn":
        return None, None
    try:
        return schema_model.model_validate_json(text), None
    except ValidationError as exc:
        return None, "; ".join(f"{'/'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())


def call_structured(feature: str, system: str, content_blocks: list[dict], schema_model: type[BaseModel],
                    max_tokens: int) -> StructuredResult:
    settings = get_settings()
    schema = strict_schema(schema_model)
    model = getattr(settings, f"claude_model_{feature}")
    effort = settings.claude_effort_extraction if feature == "extraction" else DEFAULT_EFFORT
    config = {"feature": feature, "model": model, "effort": effort, "max_tokens": max_tokens,
              "schema_version": schema_version(schema)}
    request = {
        "model": model, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": content_blocks}],
        "betas": [FALLBACK_BETA], "fallbacks": "default",
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    }
    key = fixture_key(feature, model, system, content_blocks, schema, max_tokens)
    started = time.perf_counter()
    message = _obtain(settings.llm_mode, key, request, config)
    latency_ms = round((time.perf_counter() - started) * 1000)
    text = "".join(block.text for block in message.content if block.type == "text")
    parsed, validation_error = _parse(schema_model, message.stop_reason, text)
    result = StructuredResult(parsed, text, message.stop_reason, latency_ms, _usage(message), config, validation_error)
    log.info(json.dumps({"feature": feature, "model": model, "mode": settings.llm_mode,
                         "stop_reason": result.stop_reason, "usage": result.usage, "latency_ms": latency_ms}))
    return result
