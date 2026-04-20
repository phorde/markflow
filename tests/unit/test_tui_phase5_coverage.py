from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace

import pytest

from markflow import tui
from markflow.llm_types import DiscoveredModel, ModelSelectionResult

pytestmark = pytest.mark.unit


def _defaults(**overrides: object) -> Namespace:
    values = dict(
        mode="auto",
        input="in.pdf",
        output_dir="out",
        html=False,
        routing_mode="balanced",
        disable_llm=False,
        llm_api_key="key",
        llm_base_url="https://api.example.com",
        llm_provider_preset="custom",
        zai_plan="general",
        llm_provider_name="",
        llm_model="",
        routing_debug=False,
        no_autotune_local=False,
        llm_discovery_timeout=8,
    )
    values.update(overrides)
    return Namespace(**values)


def test_prompt_fallbacks_and_cancelled_arrow_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui, "_can_use_arrow_ui", lambda: False)
    monkeypatch.setattr(tui.Prompt, "ask", lambda *args, **kwargs: "fast")
    monkeypatch.setattr(tui, "_FALLBACK_HINT_SHOWN", False)
    selected = tui._select_option(
        console=SimpleNamespace(print=lambda *a, **k: None),
        title="Mode",
        text="choose",
        options=[("auto", "Auto"), ("fast", "Fast")],
        default="auto",
        fallback_label="fallback",
    )
    assert selected == "fast"

    monkeypatch.setattr(tui, "_select_option", lambda **kwargs: "invalid")
    monkeypatch.setattr(tui.Confirm, "ask", lambda *args, **kwargs: True)
    assert tui._select_yes_no(
        console=SimpleNamespace(),
        title="YesNo",
        text="text",
        default=False,
        fallback_label="fallback",
    )

    class _Prompt:
        def __init__(self, value: object) -> None:
            self.value = value

        def ask(self) -> object:
            return self.value

    fake_q = SimpleNamespace(
        text=lambda *args, **kwargs: _Prompt(None),
        password=lambda *args, **kwargs: _Prompt(None),
    )
    monkeypatch.setattr(tui, "questionary", fake_q)
    monkeypatch.setattr(tui, "_can_use_arrow_ui", lambda: True)
    assert tui._ask_text(SimpleNamespace(), "label", "default") == "default"
    assert tui._ask_secret(SimpleNamespace(), "label", "secret-default") == "secret-default"

    monkeypatch.setattr(tui, "_can_use_arrow_ui", lambda: False)
    monkeypatch.setattr(tui.Prompt, "ask", lambda *args, **kwargs: "typed-fallback")
    assert tui._ask_text(SimpleNamespace(), "label", "default") == "typed-fallback"
    assert tui._ask_secret(SimpleNamespace(), "label", "secret") == "typed-fallback"


def test_tui_remaining_helper_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui, "questionary", SimpleNamespace())
    monkeypatch.setattr(tui.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(tui.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    assert tui._arrow_ui_unavailable_reason() == "unknown"

    monkeypatch.setattr(tui, "_select_option", lambda **kwargs: "no")
    assert (
        tui._select_yes_no(
            console=SimpleNamespace(),
            title="No",
            text="no",
            default=True,
            fallback_label="fallback",
        )
        is False
    )

    monkeypatch.setattr(tui, "_select_option", lambda **kwargs: "m2")
    console = SimpleNamespace(print=lambda *args, **kwargs: None)
    assert (
        tui._prompt_discovered_model_selection(
            console,
            [DiscoveredModel("m1", "m1", True, False), DiscoveredModel("m2", "m2", True, True)],
            "missing",
        )
        == "m2"
    )


def test_run_interactive_setup_without_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    defaults = _defaults(disable_llm=True, no_autotune_local=True)
    yes_no = {
        "Output Format": True,
        "LLM Orchestration": False,
        "Routing Debug": True,
        "Machine Autotune": False,
    }
    monkeypatch.setattr(tui, "_can_use_arrow_ui", lambda: True)
    monkeypatch.setattr(tui, "_select_option", lambda **kwargs: kwargs["default"])
    monkeypatch.setattr(tui, "_select_yes_no", lambda **kwargs: yes_no[kwargs["title"]])
    monkeypatch.setattr(tui, "_ask_text", lambda console, label, default="": default)

    updated = tui.run_interactive_setup(defaults)

    assert updated.disable_llm is True
    assert updated.html is True
    assert updated.routing_debug is True
    assert updated.no_autotune_local is True


def test_run_interactive_setup_zai_discovery_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = _defaults(llm_provider_preset="z-ai", zai_plan="coding", llm_model="old")
    yes_no = {
        "Output Format": False,
        "LLM Orchestration": True,
        "Model Discovery": True,
        "Routing Debug": False,
        "Machine Autotune": True,
    }

    def select_option(**kwargs: object) -> str:
        title = kwargs["title"]
        if title == "Provider Preset":
            return "z-ai"
        if title == "Z.AI Plan":
            return "coding"
        return str(kwargs["default"])

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        def discover_models_sync(self) -> list[DiscoveredModel]:
            raise RuntimeError("network")

    monkeypatch.setattr(tui, "_can_use_arrow_ui", lambda: False)
    monkeypatch.setattr(tui, "_select_option", select_option)
    monkeypatch.setattr(tui, "_select_yes_no", lambda **kwargs: yes_no[kwargs["title"]])
    monkeypatch.setattr(
        tui,
        "_ask_text",
        lambda console, label, default="": (
            "manual-after-error" if label.startswith("Model id") else default
        ),
    )
    monkeypatch.setattr(tui, "_ask_secret", lambda console, label, default="": "key")
    monkeypatch.setattr(tui, "OpenAICompatibleClient", _Client)

    updated = tui.run_interactive_setup(defaults)

    assert updated.llm_provider_preset == "z-ai"
    assert updated.zai_plan == "coding"
    assert updated.llm_model == "manual-after-error"


def test_run_interactive_setup_discovery_no_recommendation_then_manual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = _defaults(llm_model="")
    yes_no = {
        "Output Format": False,
        "LLM Orchestration": True,
        "Model Discovery": True,
        "Routing Debug": False,
        "Machine Autotune": True,
    }
    discovered = [DiscoveredModel("chat", "chat", True, False)]

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        def discover_models_sync(self) -> list[DiscoveredModel]:
            return discovered

    selector = ModelSelectionResult(
        selected_model=None,
        fallback_models=[],
        total_score=0.0,
        component_scores={},
        reason_lines=[],
        tradeoff_lines=[],
        influencing_signals=[],
    )

    monkeypatch.setattr(tui, "_can_use_arrow_ui", lambda: False)
    monkeypatch.setattr(tui, "_select_option", lambda **kwargs: kwargs["default"])
    monkeypatch.setattr(tui, "_select_yes_no", lambda **kwargs: yes_no[kwargs["title"]])
    monkeypatch.setattr(tui, "_ask_secret", lambda console, label, default="": "key")
    monkeypatch.setattr(
        tui,
        "_ask_text",
        lambda console, label, default="": (
            "manual-no-rec" if label.startswith("Model id") else default
        ),
    )
    monkeypatch.setattr(tui, "OpenAICompatibleClient", _Client)
    monkeypatch.setattr(tui, "collect_ocr_benchmark_signals", lambda timeout_seconds: ([], ["w"]))
    monkeypatch.setattr(tui, "select_best_model", lambda **kwargs: selector)
    monkeypatch.setattr(tui, "_prompt_discovered_model_selection", lambda **kwargs: "")

    updated = tui.run_interactive_setup(defaults)

    assert updated.llm_model == "manual-no-rec"


def test_run_interactive_setup_recommendation_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = _defaults(llm_model="")
    yes_no_values = iter([False, True, True, False, False, True])
    discovered = [DiscoveredModel("recommended", "recommended", True, True)]

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        def discover_models_sync(self) -> list[DiscoveredModel]:
            return discovered

    selector = ModelSelectionResult(
        selected_model=discovered[0],
        fallback_models=[],
        total_score=0.9,
        component_scores={},
        reason_lines=["reason"],
        tradeoff_lines=["tradeoff"],
        influencing_signals=[],
    )

    monkeypatch.setattr(tui, "_can_use_arrow_ui", lambda: False)
    monkeypatch.setattr(tui, "_select_option", lambda **kwargs: kwargs["default"])
    monkeypatch.setattr(tui, "_select_yes_no", lambda **kwargs: next(yes_no_values))
    monkeypatch.setattr(tui, "_ask_secret", lambda console, label, default="": "key")
    monkeypatch.setattr(tui, "_ask_text", lambda console, label, default="": default)
    monkeypatch.setattr(tui, "OpenAICompatibleClient", _Client)
    monkeypatch.setattr(tui, "collect_ocr_benchmark_signals", lambda timeout_seconds: ([], []))
    monkeypatch.setattr(tui, "select_best_model", lambda **kwargs: selector)
    monkeypatch.setattr(tui, "_prompt_discovered_model_selection", lambda **kwargs: "manual-choice")

    updated = tui.run_interactive_setup(defaults)

    assert updated.llm_model == "manual-choice"


def test_run_interactive_setup_recommendation_kept_and_no_recommendation_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered = [DiscoveredModel("recommended", "recommended", True, True)]

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        def discover_models_sync(self) -> list[DiscoveredModel]:
            return discovered

    selector = ModelSelectionResult(
        selected_model=discovered[0],
        fallback_models=[],
        total_score=0.9,
        component_scores={},
        reason_lines=["reason"],
        tradeoff_lines=["tradeoff"],
        influencing_signals=[],
    )

    yes_no_values = iter([False, True, True, True, False, True])
    monkeypatch.setattr(tui, "_can_use_arrow_ui", lambda: False)
    monkeypatch.setattr(tui, "_select_option", lambda **kwargs: kwargs["default"])
    monkeypatch.setattr(tui, "_select_yes_no", lambda **kwargs: next(yes_no_values))
    monkeypatch.setattr(tui, "_ask_secret", lambda console, label, default="": "key")
    monkeypatch.setattr(tui, "_ask_text", lambda console, label, default="": default)
    monkeypatch.setattr(tui, "OpenAICompatibleClient", _Client)
    monkeypatch.setattr(tui, "collect_ocr_benchmark_signals", lambda timeout_seconds: ([], ["w"]))
    monkeypatch.setattr(tui, "select_best_model", lambda **kwargs: selector)

    kept = tui.run_interactive_setup(_defaults())
    assert kept.llm_model == "recommended"

    no_selector = ModelSelectionResult(
        selected_model=None,
        fallback_models=[],
        total_score=0.0,
        component_scores={},
        reason_lines=[],
        tradeoff_lines=[],
        influencing_signals=[],
    )
    yes_no_values = iter([False, True, True, False, True])
    monkeypatch.setattr(tui, "_select_yes_no", lambda **kwargs: next(yes_no_values))
    monkeypatch.setattr(tui, "select_best_model", lambda **kwargs: no_selector)
    monkeypatch.setattr(tui, "_prompt_discovered_model_selection", lambda **kwargs: "chosen")

    chosen = tui.run_interactive_setup(_defaults())
    assert chosen.llm_model == "chosen"
