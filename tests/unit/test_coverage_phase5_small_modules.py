from __future__ import annotations

import builtins
import urllib.error
from pathlib import Path

import pytest

from markflow import benchmark_ingestion as benchmark
from markflow.extraction import rendering
from markflow.extraction.local_ocr import (
    easyocr_language_list,
    local_ocr_language_tokens,
    normalize_ocr_confidence,
    score_local_ocr_confidence,
    tesseract_language,
)
from markflow.extraction.page_analysis import (
    clean_markdown,
    inspect_text_layer,
    looks_like_atomic_markdown_line,
    normalize_markdown_document,
)
from markflow.extraction.review import (
    medical_validation_warnings,
    score_markdown_confidence,
    should_use_cleanup,
    should_use_visual_qa,
    validate_markdown_text,
)
from markflow.llm_types import BenchmarkSignal, DiscoveredModel
from markflow.model_selection import (
    _cost_efficiency,
    _latency_proxy,
    _match_signals,
    _metric_from_signals,
    _string_similarity,
    _zscore,
    select_best_model,
)

pytestmark = pytest.mark.unit


class _SparsePage:
    number = 4

    def __init__(self, text: str, blocks: list[tuple[object, ...]]) -> None:
        self._text = text
        self._blocks = blocks

    def get_text(self, mode: str):
        if mode == "text":
            return self._text
        if mode == "blocks":
            return self._blocks
        return ""

    def get_images(self, full: bool = True):
        return []


def test_benchmark_fetch_and_collection_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return "conteudo acentuado".encode()

    captured: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: int) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(benchmark.urllib.request, "urlopen", fake_urlopen)
    assert benchmark._fetch("https://example.test", timeout_seconds=0) == "conteudo acentuado"
    assert captured["timeout"] == 3

    monkeypatch.setattr(
        benchmark,
        "_fetch",
        lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    signals, warnings = benchmark.collect_ocr_benchmark_signals()
    assert signals == []
    assert any(item.startswith("benchmark_unreachable:") for item in warnings)
    assert "benchmark_signals_missing:falling_back_to_metadata_heuristics" in warnings

    monkeypatch.setattr(
        benchmark,
        "_fetch",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad parse")),
    )
    _, warnings = benchmark.collect_ocr_benchmark_signals()
    assert any(item.startswith("benchmark_parse_failed:") for item in warnings)


def test_benchmark_parsers_cover_partial_html_and_markdown_rows() -> None:
    assert benchmark._parse_ocrbench_v2("") == []
    assert benchmark._parse_ocrbench_v2_markdown_rows("| 1 | tiny | 99 |\n") == []

    markdown = "| 1 | OCR Model | 90 | 80 | 70 | 60 |\n"
    markdown_signals = benchmark._parse_ocrbench_v2_markdown_rows(markdown)
    assert markdown_signals[0].model_name == "OCR Model"
    assert markdown_signals[0].metadata["metric_count"] == 4

    html = """
    <table>
      <tr><td>x</td><td>Model</td><td>90</td><td>80</td><td>70</td><td>60</td></tr>
      <tr><td>1</td><td>🥇 Vision Model</td><td>90</td><td>80</td><td>70</td><td>60</td></tr>
      <tr><td>2</td><td></td><td>90</td><td>80</td><td>70</td><td>60</td></tr>
      <tr><td>3</td><td>Few Metrics</td><td>90</td><td>x</td><td>101</td><td>-1</td></tr>
      <tr><td>4</td><td>Vision Model</td><td>92</td><td>82</td><td>72</td><td>62</td></tr>
    </table>
    """
    signals = benchmark._parse_ocrbench_v2_html(html)
    assert len(signals) == 1
    assert signals[0].metadata["row_count"] == 2
    assert signals[0].metadata["parser"] == "html_table"


def test_rendering_preprocess_import_fallback_and_image_modes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_import = builtins.__import__

    def blocked_pil_import(name: str, *args: object, **kwargs: object):
        if name == "PIL":
            raise ImportError("PIL unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_pil_import)
    assert (
        rendering.preprocess_ocr_image(
            b"raw",
            enable_preprocess=True,
            autocontrast=True,
            sharpen=True,
            binarize_threshold=120,
        )
        == b"raw"
    )
    monkeypatch.setattr(builtins, "__import__", original_import)

    from PIL import Image

    path = tmp_path / "rgba.png"
    Image.new("RGBA", (3, 3), color=(255, 0, 0, 128)).save(path)
    processed = rendering.preprocess_ocr_image(
        path.read_bytes(),
        enable_preprocess=True,
        autocontrast=False,
        sharpen=False,
        binarize_threshold=0,
    )
    assert processed.startswith(b"\xff\xd8")


def test_rendering_sanitizer_without_bleach(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def blocked_bleach_import(name: str, *args: object, **kwargs: object):
        if name == "bleach":
            raise ImportError("bleach unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_bleach_import)
    sanitized = rendering.sanitize_rendered_html(
        '<p onclick="evil()">ok</p><script>alert(1)</script>' '<a href="javascript:alert(1)">x</a>'
    )
    assert "<script" not in sanitized
    assert "onclick" not in sanitized
    assert 'href="#"' in sanitized


def test_local_ocr_and_page_analysis_remaining_branches() -> None:
    assert normalize_ocr_confidence(101) == 0.0
    assert local_ocr_language_tokens("") == ["pt", "en"]
    assert easyocr_language_list("deu") == ["pt", "en"]
    assert tesseract_language("deu") == "deu"
    assert score_local_ocr_confidence("texto legivel suficiente", 0.0, []) > 0

    assert clean_markdown("```markdown\nabc") == "abc"
    assert clean_markdown("abc```") == "abc"
    assert looks_like_atomic_markdown_line("")
    assert looks_like_atomic_markdown_line("- item")
    assert looks_like_atomic_markdown_line("[x] tarefa")
    assert looks_like_atomic_markdown_line("|---|---|")
    assert looks_like_atomic_markdown_line("TITULO CURTO")
    assert normalize_markdown_document("") == ""
    text = "um dois tres quatro cinco seis sete oito nove dez"
    payload = inspect_text_layer(_SparsePage(text, []), text_min_chars=1)
    assert payload is not None
    assert payload["page_index"] == 4
    assert "short_text_layer" in payload["warnings"]
    assert "low_text_structure" in payload["warnings"]


def test_review_policy_remaining_branches() -> None:
    warnings = validate_markdown_text("a|b\nc|d")
    assert "weak_table_structure" in warnings
    assert "replacement_character_present" in validate_markdown_text("texto com \ufffd caractere")
    assert "garbled_symbol_density" in validate_markdown_text("texto " + "@" * 20)
    consonants = "bcdfg " * 45
    assert "garbled_no_vowel_token_ratio" in validate_markdown_text(consonants)
    singles = "a " * 45
    assert "garbled_single_char_ratio" in validate_markdown_text(singles)

    assert medical_validation_warnings("sem numeros", "texto candidato suficientemente longo") == []
    assert "medical_validator_too_short" in medical_validation_warnings("", "curto")
    assert score_markdown_confidence("", "text-layer", []) == 0.0
    assert score_markdown_confidence("[Page 1 failed: boom]", "vision-ocr", []) == 0.0

    assert should_use_visual_qa(
        0.99,
        [],
        "text-layer",
        enable_visual_qa=True,
        medical_strict=True,
        llm_enabled=True,
        qa_confidence_threshold=0.5,
    )
    assert not should_use_visual_qa(
        0.99,
        [],
        "text-layer",
        enable_visual_qa=True,
        medical_strict=False,
        llm_enabled=True,
        qa_confidence_threshold=0.5,
    )
    assert should_use_cleanup(
        0.99,
        [],
        "text-layer",
        enable_nlp_review=True,
        medical_strict=True,
        llm_enabled=True,
        cleanup_confidence_threshold=0.5,
    )
    assert not should_use_cleanup(
        0.99,
        [],
        "vision-ocr",
        enable_nlp_review=True,
        medical_strict=False,
        llm_enabled=True,
        cleanup_confidence_threshold=0.5,
    )


def test_model_selection_remaining_branches() -> None:
    assert _zscore([]) == {}
    assert _string_similarity("", "model") == 0.0
    signal = BenchmarkSignal(
        source="s",
        model_name="Vision Model",
        normalized_model_name="vision-model",
        ocr_score=None,
        structured_extraction_score=0.8,
        context_stability_score=0.7,
        confidence=0.05,
    )
    model = DiscoveredModel(
        id="vision-model",
        normalized_id="vision-model",
        supports_chat=True,
        supports_vision=True,
        context_window=0,
    )
    assert _match_signals(model, [signal]) == [signal]
    assert _metric_from_signals([signal], "ocr_score") == -1.0
    assert _metric_from_signals([signal], "structured_extraction_score") == pytest.approx(0.8)
    assert (
        _cost_efficiency(
            DiscoveredModel(
                id="expensive",
                normalized_id="expensive",
                supports_chat=True,
                supports_vision=False,
                input_cost_per_million=100,
                output_cost_per_million=100,
            )
        )
        == 0.0
    )
    assert (
        _latency_proxy(
            DiscoveredModel(
                id="model-70b",
                normalized_id="model-70b",
                supports_chat=True,
                supports_vision=False,
            )
        )
        == 0.35
    )

    no_chat = select_best_model(
        [
            DiscoveredModel(
                id="embed",
                normalized_id="embed",
                supports_chat=False,
                supports_vision=False,
            )
        ],
        [],
        "balanced",
        require_vision=False,
    )
    assert no_chat.selected_model is None

    degraded = select_best_model(
        [
            DiscoveredModel(
                id="chat", normalized_id="chat", supports_chat=True, supports_vision=False
            )
        ],
        [],
        "high-accuracy-ocr",
        require_vision=True,
    )
    assert degraded.selected_model is not None
    assert any("vision capability" in line for line in degraded.reason_lines)
    assert "Higher OCR accuracy favored" in degraded.tradeoff_lines[0]
