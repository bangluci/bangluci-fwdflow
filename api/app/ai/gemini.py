"""Nhà cung cấp Gemini (Google AI Studio, có gói miễn phí) cho `call_structured`, cùng giao diện và cùng cách
record / replay với Claude. Gọi REST `generateContent` bằng httpx2 (đã là dependency của SDK Anthropic)."""

import json
import logging
import time
from typing import Any

import httpx2
from pydantic import BaseModel

from app.ai import claude
from app.ai.claude import PermanentAIError, StructuredResult, TransientAIError
from app.config import get_settings

log = logging.getLogger("fwdflow.ai")

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT_SECONDS = 180.0
TEMPERATURE = 0
STOP_REASONS = {"STOP": "end_turn", "MAX_TOKENS": "max_tokens"}  # mọi lý do khác (SAFETY, RECITATION…) coi như từ chối


def _parts(content_blocks: list[dict]) -> list[dict]:
    """Khối nội dung dạng Anthropic (text / image base64) → `parts` của Gemini."""
    parts = []
    for block in content_blocks:
        if block["type"] == "text":
            parts.append({"text": block["text"]})
        elif block["type"] == "image" and block["source"]["type"] == "base64":
            parts.append({"inlineData": {"mimeType": block["source"]["media_type"], "data": block["source"]["data"]}})
        else:
            raise PermanentAIError(0, "unsupported_block", f"Gemini chưa hỗ trợ khối nội dung {block['type']!r}")
    return parts


def build_request(model: str, system: str, content_blocks: list[dict], schema: dict, max_tokens: int) -> dict:
    config: dict[str, Any] = {"responseMimeType": "application/json", "responseJsonSchema": schema,
                              "maxOutputTokens": max_tokens, "temperature": TEMPERATURE}
    if "2.5-flash" in model:  # bản Flash 2.5 mặc định "nghĩ" và ăn vào hạn mức đầu ra; tắt để JSON không bị cắt
        config["thinkingConfig"] = {"thinkingBudget": 0}
    return {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": _parts(content_blocks)}], "generationConfig": config}


def parse_response(body: dict) -> tuple[str, str | None, dict[str, int]]:
    """(văn bản, stop_reason kiểu Anthropic, usage)."""
    candidates = body.get("candidates") or []
    usage_meta = body.get("usageMetadata") or {}
    usage = {"input_tokens": int(usage_meta.get("promptTokenCount") or 0),
             "output_tokens": int(usage_meta.get("candidatesTokenCount") or 0)
             + int(usage_meta.get("thoughtsTokenCount") or 0),
             "cache_read_input_tokens": int(usage_meta.get("cachedContentTokenCount") or 0),
             "cache_creation_input_tokens": 0}
    if not candidates:  # bị chặn ngay từ prompt (`promptFeedback.blockReason`)
        return "", "refusal", usage
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
    return text, STOP_REASONS.get(candidate.get("finishReason"), "refusal"), usage


def _error_from(response: httpx2.Response) -> claude.AIError:
    try:
        detail = response.json().get("error", {})
    except ValueError:
        detail = {}
    status_name = detail.get("status") or f"HTTP_{response.status_code}"
    message = f"{status_name}: {detail.get('message') or response.text[:200]}"
    transient = response.status_code == 429 or response.status_code >= 500
    return (TransientAIError if transient else PermanentAIError)(response.status_code, status_name, message)


def _client() -> httpx2.Client:
    return httpx2.Client(timeout=TIMEOUT_SECONDS)


def _live_call(model: str, request: dict) -> dict:
    api_key = get_settings().gemini_api_key
    if not api_key:
        raise PermanentAIError(0, "no_api_key", "Chưa cấu hình GEMINI_API_KEY")
    try:
        with _client() as client:
            response = client.post(f"{API_ROOT}/models/{model}:generateContent", json=request,
                                   headers={"x-goog-api-key": api_key})
    except httpx2.TransportError as exc:  # gồm timeout
        raise TransientAIError(0, type(exc).__name__, "Không kết nối được tới Gemini API") from exc
    if response.status_code >= 400:
        raise _error_from(response)
    return response.json()


def _obtain(mode: str, key: str, model: str, request: dict, meta: dict) -> dict:
    settings = get_settings()
    if mode == "replay":
        return claude.read_fixture_body(settings.llm_fixture_dir, key)["response"]
    if not settings.ai_external_enabled:
        raise PermanentAIError(0, "ai_disabled", "Tính năng AI đang tắt")
    try:
        body = _live_call(model, request)
    except claude.AIError as exc:
        if mode == "record":
            error = {"status": exc.status, "type": exc.type, "message": exc.message,
                     "transient": isinstance(exc, TransientAIError)}
            claude.write_fixture(settings.llm_fixture_dir, key, error=error, request=meta)
        raise
    if mode == "record":
        claude.write_fixture(settings.llm_fixture_dir, key, response=body, request=meta)
    return body


def call_structured(feature: str, system: str, content_blocks: list[dict], schema_model: type[BaseModel],
                    max_tokens: int) -> StructuredResult:
    settings = get_settings()
    schema = claude.strict_schema(schema_model)
    model = getattr(settings, f"gemini_model_{feature}")
    config = {"feature": feature, "provider": "gemini", "model": model, "max_tokens": max_tokens,
              "schema_version": claude.schema_version(schema)}
    request = build_request(model, system, content_blocks, schema, max_tokens)
    key = claude.fixture_key(feature, model, system, content_blocks, schema, max_tokens)
    started = time.perf_counter()
    body = _obtain(settings.llm_mode, key, model, request, config)
    latency_ms = round((time.perf_counter() - started) * 1000)
    text, stop_reason, usage = parse_response(body)
    parsed, validation_error = claude._parse(schema_model, stop_reason, text)
    result = StructuredResult(parsed, text, stop_reason, latency_ms, usage, config, validation_error)
    log.info(json.dumps({"feature": feature, "provider": "gemini", "model": model, "mode": settings.llm_mode,
                         "stop_reason": stop_reason, "usage": usage, "latency_ms": latency_ms}))
    return result
