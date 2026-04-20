from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace

import pytest

from markflow import tui
from markflow.llm_types import BenchmarkSignal, DiscoveredModel

pytestmark = pytest.mark.unit


def _defaults() -> Namespace:
    return Namespace(
        mode="auto",
        input=".",
        output_dir="out",
        html=False,
        routing_mode="balanced",
        disable_llm=False,
        llm_api_key="",
        llm_base_url="https://api.openai.com",
        llm_provider_preset="custom",
        zai_plan="general",
        llm_provider_name="",
        llm_model="",
        routing_debug=False,
        no_autotune_local=False,
        llm_discovery_timeout=8,
    )


def test_run_interactive_setup_non_tty_path(monkeypatch: pytest.MonkeyPatch) -> None:
    defaults = _defaults()
    answers = {
        "Execution Mode": "quality",
        "Routing Mode": "high-accuracy-ocr",
        "Provider Preset": "openai",
    }
    yes_no = {
        "Output Format": True,
        "LLM Orchestration": True,
        "Model Discovery": False,
        "Routing Debug": True,
        "Machine Autotune": False,
    }

    monkeypatch.setattr(tui, "_can_use_arrow_ui", lambda: False)
    monkeypatch.setattr(
        tui,
        "_select_option",
        lambda **kwargs: answers.get(kwargs["title"], kwargs["default"]),
    )
    monkeypatch.setattr(
        tui,
        "_select_yes_no",
        lambda **kwargs: yes_no.get(kwargs["title"], kwargs["default"]),
    )
    monkeypatch.setattr(
        tui,
        "_ask_text",
        lambda console, label, default="": {
            "Input PDF file or directory": '"./docs"',
            "Output directory": '"./out"',
            "OpenAI-compatible base URL": "https://api.openai.com/v1",
            "Provider label (optional)": "OpenAI",
        }.get(label, default),
    )
    monkeypatch.setattr(tui, "_ask_secret", lambda console, label, default="": "secret-key")
    updated = tui.run_interactive_setup(defaults)
    assert updated.mode == "quality"
    assert updated.input == "./docs"
    assert updated.output_dir == "./out"
    assert updated.html is True
    assert updated.routing_mode == "high-accuracy-ocr"
    assert updated.llm_provider_preset == "openai"
    assert updated.llm_base_url == "https://api.openai.com/v1"
    assert updated.routing_debug is True
    assert updated.no_autotune_local is True
    assert updated.disable_llm is False


def test_run_interactive_setup_with_discovery_and_manual_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = _defaults()
    answers = {
        "Execution Mode": "auto",
        "Routing Mode": "balanced",
        "Provider Preset": "openai",
    }
    yes_no = {
        "Output Format": False,
        "LLM Orchestration": True,
        "Model Discovery": True,
        "Model Recommendation": False,
        "Routing Debug": False,
        "Machine Autotune": True,
    }

    monkeypatch.setattr(tui, "_can_use_arrow_ui", lambda: False)
    monkeypatch.setattr(
        tui,
        "_select_option",
        lambda **kwargs: answers.get(kwargs["title"], kwargs["default"]),
    )
    monkeypatch.setattr(
        tui,
        "_select_yes_no",
        lambda **kwargs: yes_no.get(kwargs["title"], kwargs["default"]),
    )
    monkeypatch.setattr(
        tui,
        "_ask_text",
        lambda console, label, default="": {
            "Input PDF file or directory": "./docs",
            "Output directory": "./out",
            "OpenAI-compatible base URL": "https://api.openai.com/v1",
            "Provider label (optional)": "OpenAI",
        }.get(label, default),
    )
    monkeypatch.setattr(tui, "_ask_secret", lambda console, label, default="": "secret-key")
    monkeypatch.setattr(tui, "_prompt_discovered_model_selection", lambda **kwargs: "manual-model")

    discovered = [DiscoveredModel("gpt-4o", "gpt-4o", True, True, 128000)]
    benchmark = [
        BenchmarkSignal(
            source="ocrbench_v2",
            model_name="gpt-4o",
            normalized_model_name="gpt-4o",
            ocr_score=0.9,
            structured_extraction_score=0.9,
            context_stability_score=0.9,
            confidence=0.8,
        )
    ]
    selector = SimpleNamespace(
        selected_model=SimpleNamespace(id="gpt-4o"),
        reason_lines=["reason"],
        tradeoff_lines=["tradeoff"],
    )

    class _FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def discover_models_sync(self):
            return discovered

    monkeypatch.setattr(tui, "OpenAICompatibleClient", _FakeClient)
    monkeypatch.setattr(
        tui,
        "collect_ocr_benchmark_signals",
        lambda timeout_seconds=8: (benchmark, ["warn"]),
    )
    monkeypatch.setattr(tui, "select_best_model", lambda **kwargs: selector)

    updated = tui.run_interactive_setup(defaults)
    assert updated.llm_model == "manual-model"
    assert updated.no_autotune_local is False
