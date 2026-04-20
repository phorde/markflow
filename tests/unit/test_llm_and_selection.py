from __future__ import annotations

import asyncio
import pytest

from markflow.benchmark_ingestion import _parse_ocrbench_v2_html, _parse_ocrbench_v2_markdown_rows
from markflow.llm_client import (
    OpenAICompatibleClient,
    _redact_sensitive,
    _validate_secure_base_url,
    normalize_model_identifier,
)
from markflow.llm_types import BenchmarkSignal, DiscoveredModel
from markflow.model_selection import select_best_model
from markflow.provider_presets import (
    apply_provider_preset,
    get_provider_preset,
    resolve_provider_base_url,
)
from markflow.routing import OcrAwareRouter, classify_complexity, classify_task_kind

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, status: int, payload: dict | None = None, text: str = "") -> None:
        self.status = status
        self._payload = payload or {}
        self._text = text

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def json(self) -> dict:
        return self._payload

    async def text(self) -> str:
        return self._text


class _FakeSession:
    def __init__(
        self,
        get_payloads: list[_FakeResponse] | None = None,
        post_payloads: list[_FakeResponse] | None = None,
    ) -> None:
        self.get_payloads = list(get_payloads or [])
        self.post_payloads = list(post_payloads or [])
        self.calls: list[tuple[str, str]] = []

    def get(self, url: str, **kwargs):
        self.calls.append(("GET", url))
        return self.get_payloads.pop(0)

    def post(self, url: str, **kwargs):
        self.calls.append(("POST", url))
        return self.post_payloads.pop(0)


def test_normalize_model_identifier_and_redaction() -> None:
    assert normalize_model_identifier("GPT 4 Omni") == "gpt-4-omni"
    redacted = _redact_sensitive("Bearer secret-token-123", "secret-token-123")
    assert "secret-token-123" not in redacted


def test_validate_secure_base_url() -> None:
    _validate_secure_base_url("https://api.openai.com/v1")
    _validate_secure_base_url("http://localhost:8080/v1")
    with pytest.raises(RuntimeError):
        _validate_secure_base_url("http://example.com")


def test_list_models_async_and_chat_completion_async() -> None:
    client = OpenAICompatibleClient(api_key="key", base_url="https://api.example.com/v1")
    session = _FakeSession(
        get_payloads=[
            _FakeResponse(
                200,
                payload={
                    "data": [
                        {
                            "id": "gpt-4-vision",
                            "context_window": 128000,
                            "pricing": {"input": 5, "output": 15},
                        }
                    ]
                },
            )
        ],
        post_payloads=[
            _FakeResponse(
                200,
                payload={
                    "model": "gpt-4-vision",
                    "choices": [{"message": {"content": "hello"}}],
                    "usage": {"prompt_tokens": 1},
                },
            )
        ],
    )
    models = asyncio.run(client.list_models_async(session))  # type: ignore[arg-type]
    assert len(models) == 1
    assert models[0].supports_vision
    result = asyncio.run(
        client.chat_completion_async(
            session,  # type: ignore[arg-type]
            model="gpt-4-vision",
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result.text == "hello"
    assert session.calls[0][1].endswith("/models")
    assert session.calls[1][1].endswith("/chat/completions")


def test_parse_benchmark_formats() -> None:
    html = (
        "<table><tr><td>1</td><td>GPT-4 Vision</td><td>90</td><td>91</td>"
        "<td>92</td><td>93</td></tr></table>"
    )
    markdown = "| 1 | GPT-4 Vision | 90 | 91 | 92 | 93 |\n"
    html_signals = _parse_ocrbench_v2_html(html)
    markdown_signals = _parse_ocrbench_v2_markdown_rows(markdown)
    assert html_signals[0].normalized_model_name == "gpt-4-vision"
    assert markdown_signals[0].model_name == "GPT-4 Vision"


def test_model_selection_and_routing() -> None:
    models = [
        DiscoveredModel("gpt-4-vision", "gpt-4-vision", True, True, 128000, 5.0, 15.0),
        DiscoveredModel("cheap-mini", "cheap-mini", True, False, 32000, 0.1, 0.2),
    ]
    signals = [
        BenchmarkSignal(
            source="ocrbench_v2",
            model_name="GPT-4 Vision",
            normalized_model_name="gpt-4-vision",
            ocr_score=0.95,
            structured_extraction_score=0.93,
            context_stability_score=0.92,
            confidence=0.9,
        )
    ]
    selection = select_best_model(models, signals, "balanced", require_vision=True)
    assert selection.selected_model is not None
    assert selection.selected_model.id == "gpt-4-vision"
    assert classify_task_kind("text-layer", [], 0.9) == "simple_text_extraction"
    assert classify_complexity(True, 0, 100) == "low"
    router = OcrAwareRouter()
    decision = router.route("remote_ocr", "high", "balanced", models, signals, True)
    assert decision.selected_model is not None
    assert decision.selected_model.id == "gpt-4-vision"


def test_provider_presets() -> None:
    assert resolve_provider_base_url("z-ai", "coding").endswith("/api/coding/paas/v4")
    base_url, provider_name = apply_provider_preset("openai", "general", "", "")
    assert base_url == get_provider_preset("openai").base_url
    assert provider_name == "OpenAI"
