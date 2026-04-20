from __future__ import annotations

from pathlib import Path
import sys

import pytest

from markflow import cli
from markflow import benchmark_ingestion as benchmark
from markflow.extraction.rendering import sanitize_rendered_html
from markflow.extraction.local_ocr import tesseract_language
from markflow.extraction.page_analysis import (
    clean_markdown,
    inspect_text_layer,
    looks_like_atomic_markdown_line,
    normalize_markdown_document,
)
from markflow.extraction.review import should_use_cleanup, should_use_visual_qa
from markflow.llm_types import DiscoveredModel
from markflow.model_selection import _heuristic_ocr_boost
from markflow.model_selection import _match_signals
from markflow.provider_presets import resolve_provider_base_url
from markflow.routing import classify_task_kind
from markflow.security import redact_sensitive_text

pytestmark = pytest.mark.unit


def test_cli_autotune_tui_failure_and_document_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = cli.apply_mode_profile(cli.parse_args) if False else None
    assert args is None

    base = cli.argparse.Namespace(
        input=".",
        output_dir="out",
        suffix=".md",
        html=False,
        concurrency=1,
        timeout=1,
        zoom=1.0,
        max_image_side=100,
        rgb_ocr=False,
        scanned_fast=False,
        ocr_retries=1,
        qa_retries=1,
        cleanup_retries=1,
        text_min_chars=1,
        qa_confidence_threshold=0.1,
        cleanup_confidence_threshold=0.1,
        min_acceptable_confidence=0.1,
        remote_first=False,
        disable_local_ocr=False,
        local_ocr_lang="pt",
        local_ocr_engine="easyocr",
        local_min_confidence=0.1,
        local_ocr_psm=6,
        disable_ocr_preprocess=False,
        no_autocontrast=False,
        no_sharpen=False,
        ocr_binarize_threshold=0,
        disable_render_cache=False,
        medical_strict=False,
        strict_recovery_attempts=0,
        allow_single_pass_llm_review=False,
        disable_strict_llm_required=False,
        no_text_layer=False,
        disable_visual_qa=False,
        disable_nlp_review=False,
        disable_cache=False,
        allow_sensitive_cache=False,
        cache_schema_version=1,
        cache_ttl_seconds=0,
        no_autotune_local=False,
        llm_base_url="",
        llm_provider_preset="custom",
        zai_plan="general",
        llm_provider_name="",
        llm_model="",
        routing_mode="balanced",
        routing_debug=False,
        llm_discovery_timeout=1,
        disable_llm=True,
        mode="auto",
        tui=True,
    )
    monkeypatch.setattr(cli, "_autotune_for_machine", lambda cfg: cfg)
    assert cli.build_config(base).concurrency == 1

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(cli, "parse_args", lambda: base)
    monkeypatch.setattr(cli, "run_interactive_setup", lambda args: args)
    monkeypatch.setattr(cli, "discover_pdfs", lambda value: [pdf])
    monkeypatch.setattr(
        cli,
        "process_document",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("document boom")),
    )
    assert cli.main() == 2


def test_remaining_helper_branches() -> None:
    assert tesseract_language("") == "por+eng"
    assert clean_markdown("```\nabc\n```") == "abc"
    assert looks_like_atomic_markdown_line("| --- | --- |")
    assert looks_like_atomic_markdown_line(":---|---:")
    assert normalize_markdown_document("a\n\n\nb") == "a\n\nb"
    assert normalize_markdown_document("# T\n\nbody\n\nnext") == "# T\n\nbody\n\nnext"
    assert resolve_provider_base_url("z-ai", "general").endswith("/paas/v4")
    assert classify_task_kind("vision-ocr", [], 0.8) == "balanced_document_extraction"
    assert redact_sensitive_text("plain text", secrets=[""]) == "plain text"

    class RichPage:
        number = 0

        def get_text(self, mode: str):
            if mode == "text":
                return "palavra " * 20
            if mode == "blocks":
                return [(0, 0, 1, 1, "texto")]
            return ""

        def get_images(self, full: bool = True):
            return []

    payload = inspect_text_layer(RichPage(), text_min_chars=10)
    assert payload is not None
    assert payload["warnings"] == []


def test_remaining_benchmark_and_rendering_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <tr><td>1</td><td>HTML Model</td><td>90</td><td>80</td><td>70</td><td>60</td></tr>
    """
    assert benchmark._parse_ocrbench_v2(html)[0].model_name == "HTML Model"
    assert benchmark._parse_ocrbench_v2_html("<tr><td>1</td></tr>") == []
    monkeypatch.setattr(benchmark, "_fetch", lambda *args, **kwargs: "no rows")
    signals, warnings = benchmark.collect_ocr_benchmark_signals()
    assert signals == []
    assert any(item.startswith("benchmark_empty:") for item in warnings)

    class FakeBleach:
        @staticmethod
        def clean(body: str, **kwargs: object) -> str:
            assert "h1" in kwargs["tags"]
            assert kwargs["protocols"] == ["http", "https", "mailto"]
            return body.replace("javascript:alert(1)", "")

    monkeypatch.setitem(sys.modules, "bleach", FakeBleach)
    sanitized = sanitize_rendered_html(
        '<h1>Ok</h1><a href="https://example.com" title="x">safe</a>'
        '<a href="javascript:alert(1)">bad</a>'
    )
    assert "<h1>Ok</h1>" in sanitized
    assert "javascript:" not in sanitized


def test_remaining_review_and_selection_branches() -> None:
    assert should_use_visual_qa(
        0.9,
        ["garbled_symbol_density"],
        "vision-ocr",
        enable_visual_qa=True,
        medical_strict=False,
        llm_enabled=True,
        qa_confidence_threshold=0.1,
    )
    assert should_use_cleanup(
        0.9,
        ["garbled_symbol_density"],
        "vision-ocr",
        enable_nlp_review=True,
        medical_strict=False,
        llm_enabled=True,
        cleanup_confidence_threshold=0.1,
    )
    assert should_use_cleanup(
        0.1,
        ["very_short_output"],
        "text-layer",
        enable_nlp_review=True,
        medical_strict=False,
        llm_enabled=True,
        cleanup_confidence_threshold=0.5,
    )

    assert _heuristic_ocr_boost(
        DiscoveredModel("ocr-vision", "ocr-vision", True, True, context_window=128000)
    ) == pytest.approx(0.55)
    assert _heuristic_ocr_boost(
        DiscoveredModel("plain", "plain", True, True, context_window=64000)
    ) == pytest.approx(0.42)
    assert (
        _match_signals(
            DiscoveredModel("a", "a", True, False),
            [
                benchmark.BenchmarkSignal(
                    source="s",
                    model_name="b",
                    normalized_model_name="different",
                    confidence=1,
                ),
                benchmark.BenchmarkSignal(
                    source="s",
                    model_name="c",
                    normalized_model_name="also-different",
                    confidence=1,
                ),
            ],
        )
        == []
    )
