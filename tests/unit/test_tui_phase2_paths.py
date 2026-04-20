from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace

import pytest

from markflow import tui
from markflow.llm_types import DiscoveredModel

pytestmark = pytest.mark.unit


def test_arrow_unavailable_reason_for_missing_tty_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tui, "questionary", SimpleNamespace())
    monkeypatch.setattr(tui.sys, "stdin", object())
    monkeypatch.setattr(tui.sys, "stdout", object())
    assert tui._arrow_ui_unavailable_reason() == "tty_capability_unknown"


def test_select_option_falls_back_to_default_when_arrow_returns_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Prompt:
        def ask(self):
            return None

    fake_q = SimpleNamespace(
        Choice=lambda **kwargs: kwargs,
        select=lambda *args, **kwargs: Prompt(),
    )
    monkeypatch.setattr(tui, "questionary", fake_q)
    monkeypatch.setattr(tui.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(tui.sys, "stdout", SimpleNamespace(isatty=lambda: True))

    selected = tui._select_option(
        console=SimpleNamespace(print=lambda *a, **k: None),
        title="Mode",
        text="choose",
        options=[("auto", "Auto"), ("fast", "Fast")],
        default="fast",
        fallback_label="fallback",
    )
    assert selected == "fast"


def test_prompt_discovered_model_selection_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    console = SimpleNamespace(print=lambda *a, **k: None)
    assert tui._prompt_discovered_model_selection(console, [], "") == ""

    monkeypatch.setattr(tui, "_select_option", lambda **kwargs: "auto")
    models = [DiscoveredModel("m1", "m1", True, True, 1000)]
    assert tui._prompt_discovered_model_selection(console, models, "m1") == ""

    monkeypatch.setattr(tui, "_select_option", lambda **kwargs: "m1")
    assert tui._prompt_discovered_model_selection(console, models, "") == "m1"


def test_run_interactive_setup_discovery_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = Namespace(
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
    yes_no = {
        "Output Format": False,
        "LLM Orchestration": True,
        "Model Discovery": True,
        "Routing Debug": False,
        "Machine Autotune": True,
    }
    monkeypatch.setattr(tui, "_can_use_arrow_ui", lambda: False)
    monkeypatch.setattr(tui, "_select_option", lambda **kwargs: kwargs["default"])
    monkeypatch.setattr(tui, "_select_yes_no", lambda **kwargs: yes_no[kwargs["title"]])
    monkeypatch.setattr(
        tui,
        "_ask_text",
        lambda console, label, default="": (
            "manual-model" if label.startswith("Model id") else default
        ),
    )
    monkeypatch.setattr(tui, "_ask_secret", lambda console, label, default="": "")

    updated = tui.run_interactive_setup(defaults)
    assert updated.llm_model == "manual-model"
