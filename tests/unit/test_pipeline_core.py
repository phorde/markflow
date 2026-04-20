from __future__ import annotations

from pathlib import Path
import os
import time

import pytest

from markflow.extraction.local_ocr import (
    easyocr_language_list as _easyocr_language_list,
    local_ocr_language_tokens as _local_ocr_language_tokens,
    normalize_ocr_confidence as _normalize_ocr_confidence,
    score_local_ocr_confidence as _score_local_ocr_confidence,
    tesseract_language as _tesseract_language,
)
from markflow.extraction.page_analysis import (
    clean_markdown as _clean_markdown,
    normalize_markdown_document as _normalize_markdown_document,
    normalize_whitespace as _normalize_whitespace,
    page_text_confidence as _page_text_confidence,
)
from markflow.extraction.rendering import sanitize_rendered_html as _sanitize_rendered_html
from markflow.extraction.reporting import (
    derive_document_status,
    document_success as _document_success,
)
from markflow.extraction.review import (
    extract_date_tokens as _extract_date_tokens,
    extract_numeric_tokens as _extract_numeric_tokens,
    has_corruption_warning as _has_corruption_warning,
    has_severe_structure_warning as _has_severe_structure_warning,
    medical_validation_warnings as _medical_validation_warnings,
    needs_reprocess_block as _needs_reprocess_block,
    score_markdown_confidence as _score_markdown_confidence,
    should_use_cleanup,
    should_use_visual_qa,
    validate_markdown_text as _validate_markdown_text,
)
from markflow.pipeline import (
    PipelineConfig,
    _ocr_result_items_to_text,
    _page_signature,
    _render_profile_payload,
    _safe_report_url,
    _get_rendered_page_image_b64,
    discover_pdfs,
    render_html,
)

pytestmark = pytest.mark.unit


def test_normalize_ocr_confidence_handles_common_ranges() -> None:
    assert _normalize_ocr_confidence(0.73) == 0.73
    assert _normalize_ocr_confidence(73) == 0.73
    assert _normalize_ocr_confidence(100) == 1.0
    assert _normalize_ocr_confidence(None) == 0.0
    assert _normalize_ocr_confidence("bad") == 0.0
    assert _normalize_ocr_confidence(-5) == 0.0
    assert _normalize_ocr_confidence(float("inf")) == 0.0


def test_clean_and_normalize_markdown_document() -> None:
    raw = "```markdown\n# Title\n\nline 1\nline 2\n```"
    cleaned = _clean_markdown(raw)
    assert cleaned == "# Title\n\nline 1\nline 2"
    assert _normalize_markdown_document(cleaned) == "# Title\n\nline 1 line 2"
    assert _normalize_whitespace("a\r\n\r\n\r\nb") == "a\n\nb"


def test_validate_markdown_text_flags_corruption_patterns() -> None:
    text = "A1B2C3 D4E5F6 " * 30
    warnings = _validate_markdown_text(text)
    assert "garbled_alnum_mix_ratio" in warnings
    assert _has_corruption_warning(warnings)
    assert _has_severe_structure_warning(warnings)


def test_validate_markdown_text_flags_placeholder_and_short_output() -> None:
    warnings = _validate_markdown_text("N/A")
    assert "suspicious_placeholder_tokens" in warnings
    assert "very_short_output" in warnings


def test_medical_validation_warnings_detect_mismatch_and_date_loss() -> None:
    warnings = _medical_validation_warnings(
        "Paciente em 2024-01-10 glicose 120",
        "Paciente sem data glicose 90",
    )
    assert "medical_validator_date_loss" in warnings
    assert any(item.startswith("medical_validator_numeric_mismatch:") for item in warnings)


def test_extract_tokens_helpers() -> None:
    text = "Data 10/01/2024 valor 123,45 e 678"
    assert _extract_date_tokens(text) == ["10/01/2024"]
    assert _extract_numeric_tokens(text) == ["10", "01", "2024", "123,45", "678"]


def test_markdown_confidence_and_local_score() -> None:
    warnings = _validate_markdown_text("# Titulo\n\nConteudo suficiente para score.")
    confidence = _score_markdown_confidence(
        "# Titulo\n\nConteudo suficiente para score.",
        "text-layer",
        warnings,
    )
    assert 0.0 < confidence <= 0.99
    blended = _score_local_ocr_confidence("Texto de OCR coerente", 0.8, [])
    assert 0.0 < blended <= 0.99


def test_visual_qa_and_cleanup_policy() -> None:
    cfg = PipelineConfig(enable_visual_qa=True, enable_nlp_review=True)
    warnings = ["isolated_table_row"]
    assert should_use_visual_qa(
        0.5,
        warnings,
        "vision-ocr",
        enable_visual_qa=cfg.enable_visual_qa,
        medical_strict=cfg.medical_strict,
        llm_enabled=cfg.llm_enabled,
        qa_confidence_threshold=cfg.qa_confidence_threshold,
    )
    assert should_use_cleanup(
        0.5,
        warnings,
        "vision-ocr",
        enable_nlp_review=cfg.enable_nlp_review,
        medical_strict=cfg.medical_strict,
        llm_enabled=cfg.llm_enabled,
        cleanup_confidence_threshold=cfg.cleanup_confidence_threshold,
    )


def test_language_normalization_helpers() -> None:
    assert _local_ocr_language_tokens("pt-BR, eng Portuguese") == ["pt", "en"]
    assert _easyocr_language_list("spa") == ["pt", "en"]
    assert _tesseract_language("pt,en") == "por+eng"


def test_ocr_result_items_to_text_reconstructs_order_and_confidence() -> None:
    items = [
        ([[10, 20], [20, 20]], "segunda", 0.8),
        ([[0, 0], [10, 0]], "primeira", 0.9),
    ]
    text, confidence = _ocr_result_items_to_text(items, fallback_join=" ")
    assert text == "primeira segunda"
    assert confidence == 0.85


def test_render_payload_and_signature_are_stable() -> None:
    payload = _render_profile_payload("doc", 1.5, 1700, True, True, True, True, 0)
    signature = _page_signature("render", payload, 1)
    assert payload.startswith("v1:doc:1.500:1700")
    assert len(signature) == 64


def test_render_cache_ttl_forces_refresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    values = iter(["cached-a", "cached-b"])
    monkeypatch.setattr("markflow.pipeline._render_page_image_b64", lambda *a, **k: next(values))

    class FakePage:
        pass

    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        page=FakePage(),
        cache_dir=cache_dir,
        page_index=0,
        doc_fingerprint="doc",
        zoom_matrix=1.5,
        max_image_side_px=1200,
        grayscale=True,
        cache_enabled=True,
        preprocess_enabled=True,
        autocontrast=True,
        sharpen=False,
        binarize_threshold=0,
        cache_schema_version=1,
    )
    first = _get_rendered_page_image_b64(**kwargs, cache_ttl_seconds=0)
    assert first == "cached-a"
    cached_file = next(cache_dir.glob("*.b64"))

    stale = time.time() - 10
    os.utime(cached_file, (stale, stale))
    second = _get_rendered_page_image_b64(**kwargs, cache_ttl_seconds=1)
    assert second == "cached-b"


def test_page_text_confidence_bounds() -> None:
    assert _page_text_confidence(0, 0, 0) == 0.0
    assert 0.55 <= _page_text_confidence(1200, 120, 40) <= 0.99


def test_document_status_and_success() -> None:
    strict_cfg = PipelineConfig(medical_strict=True)
    report = {
        "summary": {"error_pages": 0, "needs_reprocess_pages": 1, "llm_review_required_pages": 0}
    }
    assert (
        derive_document_status(report, medical_strict=strict_cfg.medical_strict)
        == "needs_reprocess"
    )
    assert not _document_success("error")
    assert _document_success("accepted")


def test_needs_reprocess_block_contains_page_and_confidence() -> None:
    message = _needs_reprocess_block(1, 0.2, 0.88)
    assert "Page 2" in message
    assert "0.200" in message
    assert "0.880" in message


def test_html_sanitization_removes_dangerous_content() -> None:
    unsafe_html = '<p>ok</p><script>alert(1)</script><a href="javascript:alert(1)">x</a>'
    sanitized = _sanitize_rendered_html(unsafe_html)
    assert "<script>" not in sanitized
    assert "javascript:" not in sanitized
    rendered = render_html("# Titulo\n\n<script>alert(1)</script>\n\n|a|b|\n|-|-|\n|1|2|")
    assert "<script>" not in rendered
    assert "<table>" in rendered


def test_safe_report_url_removes_sensitive_url_parts() -> None:
    assert (
        _safe_report_url("https://user:secret@example.com:8443/v1?token=abc#frag")
        == "https://example.com:8443/v1"
    )
    assert (
        _safe_report_url("https://user:secret@example.com/v1?token=abc") == "https://example.com/v1"
    )
    assert _safe_report_url("https://example.com:bad/v1?token=abc") == "https://example.com/v1"
    assert _safe_report_url("http://[::1?token=abc") == "http://[::1"
    assert _safe_report_url("not-a-url?token=abc") == "not-a-url"


def test_discover_pdfs_supports_file_directory_and_home_expansion(
    monkeypatch: pytest.MonkeyPatch,
    sample_pdf: Path,
    tmp_path: Path,
) -> None:
    assert discover_pdfs(str(sample_pdf)) == [sample_pdf]
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert discover_pdfs(str(Path("~") / sample_pdf.name)) == [sample_pdf]
    other = tmp_path / "ignore.txt"
    other.write_text("x", encoding="utf-8")
    assert discover_pdfs(str(tmp_path)) == [sample_pdf]
    with pytest.raises(FileNotFoundError):
        discover_pdfs(str(tmp_path / "missing.pdf"))
