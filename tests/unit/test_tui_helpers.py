from __future__ import annotations

from types import SimpleNamespace

import pytest

from markflow import tui

pytestmark = pytest.mark.unit


def test_can_use_arrow_ui_false_without_questionary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tui, "questionary", None)
    assert not tui._can_use_arrow_ui()
    assert tui._arrow_ui_unavailable_reason() == "questionary_not_installed"


def test_arrow_reason_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_q = SimpleNamespace(Choice=lambda **kwargs: kwargs)
    monkeypatch.setattr(tui, "questionary", fake_q)
    monkeypatch.setattr(tui.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(tui.sys, "stdout", SimpleNamespace(isatty=lambda: False))
    assert tui._arrow_ui_unavailable_reason() == "non_tty_terminal"


def test_strip_optional_quotes() -> None:
    assert tui._strip_optional_quotes('"abc"') == "abc"
    assert tui._strip_optional_quotes("'abc'") == "abc"
    assert tui._strip_optional_quotes("abc") == "abc"


def test_arrow_ui_option_and_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Prompt:
        def __init__(self, value):
            self.value = value

        def ask(self):
            return self.value

    fake_q = SimpleNamespace(
        Choice=lambda **kwargs: kwargs,
        select=lambda *args, **kwargs: _Prompt("yes"),
        text=lambda *args, **kwargs: _Prompt("typed"),
        password=lambda *args, **kwargs: _Prompt("secret"),
    )
    monkeypatch.setattr(tui, "questionary", fake_q)
    monkeypatch.setattr(tui.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(tui.sys, "stdout", SimpleNamespace(isatty=lambda: True))

    selected = tui._select_option(
        console=SimpleNamespace(print=lambda *a, **k: None),
        title="T",
        text="x",
        options=[("yes", "Yes"), ("no", "No")],
        default="no",
        fallback_label="fallback",
    )
    assert selected == "yes"
    assert tui._ask_text(SimpleNamespace(), "label", "default") == "typed"
    assert tui._ask_secret(SimpleNamespace(), "label", "default") == "secret"
