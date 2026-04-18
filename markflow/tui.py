"""Interactive terminal flows for extraction mode and runtime options."""

from __future__ import annotations

import os
import sys
from argparse import Namespace

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .benchmark_ingestion import collect_ocr_benchmark_signals
from .llm_client import OpenAICompatibleClient
from .model_selection import select_best_model
from .provider_presets import (
    apply_provider_preset,
    get_provider_label,
    get_provider_preset,
    list_provider_preset_keys,
)


_MODE_HELP = {
    "auto": "Adaptive mode with intelligent routing; system decides optimal extraction path.",
    "fast": "Speed-optimized for high-throughput batches; minimal post-processing overhead.",
    "quality": "Quality/accuracy-focused with fail-closed safeguards and strict validation.",
    "local": "Local extraction only; no remote OCR or LLM calls (fully offline).",
    "remote": "Remote-first strategy with intelligent fallback to local methods.",
}

try:
    import questionary
    from questionary import Choice
except Exception:  # pragma: no cover - runtime optional dependency
    questionary = None
    Choice = None


_FALLBACK_HINT_SHOWN = False


def _can_use_arrow_ui() -> bool:
    """Return whether the terminal can use arrow-based selectors."""
    return (
        questionary is not None
        and hasattr(sys.stdin, "isatty")
        and hasattr(sys.stdout, "isatty")
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )


def _arrow_ui_unavailable_reason() -> str:
    """Return a concise explanation when arrow-key mode is unavailable."""
    if questionary is None:
        return "questionary_not_installed"
    if not hasattr(sys.stdin, "isatty") or not hasattr(sys.stdout, "isatty"):
        return "tty_capability_unknown"
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return "non_tty_terminal"
    return "unknown"


def _select_option(
    *,
    console: Console,
    title: str,
    text: str,
    options: list[tuple[str, str]],
    default: str,
    fallback_label: str,
) -> str:
    """Select one option using arrow-key UI, with Prompt fallback."""
    global _FALLBACK_HINT_SHOWN
    if _can_use_arrow_ui():
        prompt_choices = [Choice(title=label, value=value) for value, label in options]
        result = questionary.select(
            f"{title}: {text}",
            choices=prompt_choices,
            default=default,
            use_shortcuts=True,
            qmark=">",
        ).ask()
        if result in {value for value, _ in options}:
            return str(result)
        return default

    allowed = [value for value, _ in options]
    if not _FALLBACK_HINT_SHOWN:
        console.print("[dim]Tip: install/enable full TTY for arrow-key selector UI.[/dim]")
        _FALLBACK_HINT_SHOWN = True
    return Prompt.ask(fallback_label, choices=allowed, default=default)


def _select_yes_no(
    *,
    console: Console,
    title: str,
    text: str,
    default: bool,
    fallback_label: str,
) -> bool:
    """Select yes/no using arrow-key UI, with Confirm fallback."""
    options = [("yes", "Yes"), ("no", "No")]
    selected = _select_option(
        console=console,
        title=title,
        text=text,
        options=options,
        default="yes" if default else "no",
        fallback_label=fallback_label,
    )
    if selected in {"yes", "no"}:
        return selected == "yes"
    return Confirm.ask(fallback_label, default=default)


def _ask_text(console: Console, label: str, default: str = "") -> str:
    """Ask free-text input with inline interactive prompt when available."""
    if _can_use_arrow_ui():
        value = questionary.text(label, default=default, qmark=">").ask()
        return str(value if value is not None else default)
    return Prompt.ask(label, default=default)


def _ask_secret(console: Console, label: str, default: str = "") -> str:
    """Ask secret input with hidden characters."""
    if _can_use_arrow_ui():
        value = questionary.password(label, default=default, qmark=">").ask()
        return str(value if value is not None else default)
    return Prompt.ask(label, default=default, password=True)


def _strip_optional_quotes(value: str) -> str:
    """Strip matching surrounding quotes from interactive inputs."""
    text = (value or "").strip()
    if len(text) >= 2 and ((text[0] == '"' and text[-1] == '"') or (text[0] == "'" and text[-1] == "'")):
        return text[1:-1].strip()
    return text


def _prompt_discovered_model_selection(
    console: Console,
    discovered_models: list,
    current_model: str,
) -> str:
    """Show an interactive model picker and return selected model id or empty for auto."""
    if not discovered_models:
        return ""

    table = Table(title="Discovered Models", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("Model ID")
    table.add_column("Chat")
    table.add_column("Vision")
    table.add_column("Context")

    options: list[tuple[str, str]] = [("auto", "Auto-select at runtime (router decides)")]
    for index, model in enumerate(discovered_models, start=1):
        model_id = str(getattr(model, "id", ""))
        vision_value = "yes" if bool(getattr(model, "supports_vision", False)) else "unknown"
        context_value = (
            str(int(getattr(model, "context_window", 0) or 0))
            if getattr(model, "context_window", 0)
            else "-"
        )
        options.append((model_id, f"{model_id}  [vision={vision_value}, ctx={context_value}]"))
        table.add_row(
            str(index),
            model_id,
            "yes" if bool(getattr(model, "supports_chat", False)) else "no",
            vision_value,
            context_value,
        )

    console.print(table)
    default_choice = "auto"
    if current_model:
        for model in discovered_models:
            if str(getattr(model, "id", "")) == current_model:
                default_choice = current_model
                break

    selected = _select_option(
        console=console,
        title="Model Selection",
        text="Use arrows and Enter to pick a model.",
        options=options,
        default=default_choice,
        fallback_label="Select model id (or 'auto')",
    )

    if selected == "auto":
        return ""
    return selected.strip()


def run_interactive_setup(defaults: Namespace) -> Namespace:
    """Collect execution preferences through an interactive Rich terminal flow.

    Args:
        defaults: Existing argument namespace used to pre-populate prompts.

    Returns:
        Updated namespace with interactive selections.
    """
    console = Console()
    console.print(
        Panel.fit(
            "MarkFlow interactive setup\\n"
            "Configure your OCR extraction preferences and discover optimal models.",
            title="MarkFlow Setup",
            border_style="cyan",
        )
    )
    if _can_use_arrow_ui():
        console.print("[green]Interactive keyboard mode enabled: arrows + Enter.[/green]")
    else:
        console.print(
            "[yellow]Arrow-key mode unavailable; using standard prompts "
            f"({_arrow_ui_unavailable_reason()}).[/yellow]"
        )

    table = Table(title="Available Modes", show_header=True, header_style="bold cyan")
    table.add_column("Mode")
    table.add_column("Description")
    for mode_name, mode_desc in _MODE_HELP.items():
        table.add_row(mode_name, mode_desc)
    console.print(table)

    mode = _select_option(
        console=console,
        title="Execution Mode",
        text="Use arrows and Enter to choose execution mode.",
        options=[(name, f"{name}: {_MODE_HELP[name]}") for name in _MODE_HELP],
        default=getattr(defaults, "mode", "auto"),
        fallback_label="Execution mode",
    )

    input_path = _strip_optional_quotes(
        _ask_text(console, "Input PDF file or directory", str(defaults.input))
    )
    output_dir = _strip_optional_quotes(
        _ask_text(console, "Output directory", str(defaults.output_dir))
    )
    html_enabled = _select_yes_no(
        console=console,
        title="Output Format",
        text="Generate HTML output as well?",
        default=defaults.html,
        fallback_label="Generate HTML output as well?",
    )
    routing_mode = _select_option(
        console=console,
        title="Routing Mode",
        text="Use arrows and Enter to choose OCR routing objective.",
        options=[
            ("fast", "fast: prioritize speed"),
            ("balanced", "balanced: balance speed and quality"),
            ("high-accuracy-ocr", "high-accuracy-ocr: prioritize OCR quality"),
        ],
        default=getattr(defaults, "routing_mode", "balanced"),
        fallback_label="Routing mode",
    )

    llm_enabled = _select_yes_no(
        console=console,
        title="LLM Orchestration",
        text="Enable OpenAI-compatible LLM orchestration?",
        default=not getattr(defaults, "disable_llm", False),
        fallback_label="Enable OpenAI-compatible LLM orchestration?",
    )

    llm_api_key = getattr(defaults, "llm_api_key", "")
    llm_base_url = getattr(defaults, "llm_base_url", "") or "https://api.openai.com"
    llm_provider_preset = getattr(defaults, "llm_provider_preset", "custom")
    llm_zai_plan = getattr(defaults, "zai_plan", "general")
    llm_provider_name = getattr(defaults, "llm_provider_name", "")
    llm_model = getattr(defaults, "llm_model", "")
    routing_debug = bool(getattr(defaults, "routing_debug", False))

    if llm_enabled:
        provider_options = [
            (key, f"{key}: {get_provider_label(key)}") for key in list_provider_preset_keys()
        ]
        llm_provider_preset = _select_option(
            console=console,
            title="Provider Preset",
            text="Use arrows and Enter to choose provider preset.",
            options=provider_options,
            default=llm_provider_preset,
            fallback_label="Provider preset",
        )

        if llm_provider_preset == "z-ai":
            llm_zai_plan = _select_option(
                console=console,
                title="Z.AI Plan",
                text="Use arrows and Enter to choose the Z.AI endpoint plan.",
                options=[
                    ("general", "general: standard endpoint"),
                    ("coding", "coding: coding-optimized endpoint"),
                ],
                default=llm_zai_plan,
                fallback_label="Z.AI plan",
            )

        llm_api_key = _ask_secret(console, "LLM API key", llm_api_key)

        preset_base, preset_name = apply_provider_preset(
            provider_preset=llm_provider_preset,
            zai_plan=llm_zai_plan,
            current_base_url="",
            current_provider_name=llm_provider_name,
        )

        llm_base_url = _strip_optional_quotes(
            _ask_text(
                console,
                "OpenAI-compatible base URL",
                llm_base_url if llm_provider_preset == "custom" else preset_base,
            )
        )
        llm_provider_name = _ask_text(
            console,
            "Provider label (optional)",
            llm_provider_name or preset_name or get_provider_label(llm_provider_preset),
        )

        should_discover = _select_yes_no(
            console=console,
            title="Model Discovery",
            text="Discover models and auto-recommend best OCR model now?",
            default=True,
            fallback_label="Discover models and auto-recommend best OCR model now?",
        )
        if should_discover:
            if not llm_api_key.strip():
                console.print(
                    "[yellow]API key is empty. Model discovery needs a valid key; skipping discovery.[/yellow]"
                )
                llm_model = _strip_optional_quotes(
                    _ask_text(
                        console,
                        "Model id for this provider (manual fallback, leave empty for auto)",
                        llm_model,
                    )
                )
            else:
                timeout_seconds = int(getattr(defaults, "llm_discovery_timeout", 8) or 8)
                preset = get_provider_preset(llm_provider_preset)
                client = OpenAICompatibleClient(
                    api_key=llm_api_key,
                    base_url=llm_base_url,
                    provider_name=llm_provider_name,
                    provider_preset=llm_provider_preset,
                    auth_mode=preset.auth_mode,
                    timeout_seconds=timeout_seconds,
                    extra_headers=preset.required_headers,
                )
                try:
                    discovered = client.discover_models_sync()
                    console.print(f"[green]Discovered {len(discovered)} model(s).[/green]")
                    benchmark_signals, benchmark_warnings = collect_ocr_benchmark_signals(
                        timeout_seconds=timeout_seconds,
                    )
                    selector = select_best_model(
                        discovered_models=discovered,
                        benchmark_signals=benchmark_signals,
                        routing_mode=routing_mode,
                        require_vision=True,
                    )

                    if selector.selected_model is not None:
                        llm_model = selector.selected_model.id
                        console.print(
                            Panel.fit(
                                "\n".join(
                                    [
                                        f"Selected model: [bold]{llm_model}[/bold]",
                                        *selector.reason_lines,
                                        *selector.tradeoff_lines,
                                    ]
                                ),
                                title="OCR Model Recommendation",
                                border_style="magenta",
                            )
                        )
                        keep_recommendation = _select_yes_no(
                            console=console,
                            title="Model Recommendation",
                            text="Use recommended model?",
                            default=True,
                            fallback_label="Use recommended model?",
                        )
                        if not keep_recommendation:
                            llm_model = _prompt_discovered_model_selection(
                                console=console,
                                discovered_models=discovered,
                                current_model=llm_model,
                            )
                    else:
                        console.print(
                            "[yellow]No OCR-specific recommendation available from model metadata.[/yellow]"
                        )
                        llm_model = _prompt_discovered_model_selection(
                            console=console,
                            discovered_models=discovered,
                            current_model=llm_model,
                        )
                        if not llm_model:
                            llm_model = _strip_optional_quotes(
                                _ask_text(
                                    console,
                                    "Model id for this provider (manual fallback, optional)",
                                    llm_model,
                                )
                            )

                    if benchmark_warnings:
                        console.print(
                            "[yellow]Benchmark ingestion notes:[/yellow] " + "; ".join(benchmark_warnings)
                        )
                except Exception as exc:
                    console.print(f"[yellow]Model discovery skipped: {exc}[/yellow]")
                    llm_model = _strip_optional_quotes(
                        _ask_text(
                            console,
                            "Model id for this provider (manual fallback, optional)",
                            llm_model,
                        )
                    )

    routing_debug = _select_yes_no(
        console=console,
        title="Routing Debug",
        text="Enable routing debug view?",
        default=routing_debug,
        fallback_label="Enable routing debug view?",
    )

    autotune = _select_yes_no(
        console=console,
        title="Machine Autotune",
        text="Enable machine-aware autotune for local processing?",
        default=not defaults.no_autotune_local,
        fallback_label="Enable machine-aware autotune for local processing?",
    )

    defaults.mode = mode
    defaults.input = input_path
    defaults.output_dir = output_dir
    defaults.html = html_enabled
    defaults.routing_mode = routing_mode
    defaults.disable_llm = not llm_enabled
    if llm_api_key:
        os.environ["LLM_API_KEY"] = llm_api_key
        provider_env_key = get_provider_preset(llm_provider_preset).api_key_env_var
        if provider_env_key:
            os.environ[provider_env_key] = llm_api_key
    defaults.llm_api_key = ""
    defaults.llm_base_url = llm_base_url
    defaults.llm_provider_preset = llm_provider_preset
    defaults.zai_plan = llm_zai_plan
    defaults.llm_provider_name = llm_provider_name
    defaults.llm_model = llm_model
    defaults.routing_debug = routing_debug
    defaults.no_autotune_local = not autotune

    console.print(
        Panel.fit(
            f"Mode: [bold]{mode}[/bold]\n"
            f"Routing: {routing_mode}\n"
            f"Input: {input_path}\n"
            f"Output: {output_dir}\n"
            f"LLM Enabled: {llm_enabled}\n"
            f"Provider Preset: {llm_provider_preset}\n"
            f"Z.AI Plan: {llm_zai_plan if llm_provider_preset == 'z-ai' else 'n/a'}\n"
            f"Selected Model: {llm_model or 'auto-select at runtime'}",
            title="Configuration Summary",
            border_style="green",
        )
    )
    return defaults
