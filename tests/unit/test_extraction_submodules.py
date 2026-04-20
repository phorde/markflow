from __future__ import annotations

from dataclasses import dataclass
import io

import pytest

from markflow.extraction.local_ocr import (
    easyocr_language_list,
    local_ocr_language_tokens,
    normalize_local_ocr_language_token,
    normalize_ocr_confidence,
    score_local_ocr_confidence,
    tesseract_language,
)
from markflow.extraction.page_analysis import (
    clean_markdown,
    inspect_text_layer,
    looks_like_atomic_markdown_line,
    normalize_markdown_document,
    normalize_whitespace,
    page_text_confidence,
    word_count,
)
from markflow.extraction.rendering import (
    preprocess_ocr_image,
    render_html_document,
    sanitize_rendered_html,
)
from markflow.extraction.review import (
    has_corruption_warning,
    has_severe_structure_warning,
    medical_validation_warnings,
    needs_reprocess_block,
    score_markdown_confidence,
    should_use_cleanup,
    should_use_visual_qa,
    validate_markdown_text,
)

pytestmark = pytest.mark.unit


@dataclass
class _FakePage:
    number: int = 0

    def get_text(self, mode: str):
        if mode == "text":
            return "Paciente em observacao com glicose 120 e data 10/01/2024"
        if mode == "blocks":
            return [(0, 0, 100, 20, "Paciente em observacao")]
        return ""

    def get_images(self, full: bool = True):
        return [("image", 1)] if full else []


def test_page_analysis_helpers() -> None:
    assert clean_markdown("```markdown\nabc\n```") == "abc"
    assert normalize_whitespace("a\r\n\r\n\r\nb") == "a\n\nb"
    assert word_count("ola mundo") == 2
    assert normalize_markdown_document("line 1\nline 2") == "line 1 line 2"
    assert page_text_confidence(0, 0, 0) == 0.0
    assert looks_like_atomic_markdown_line("# titulo")
    assert not looks_like_atomic_markdown_line("texto corrido sem marcador")

    payload = inspect_text_layer(_FakePage(), text_min_chars=10)
    assert payload is not None
    assert payload["source"] == "text-layer"
    assert payload["image_count"] == 1
    assert inspect_text_layer(_FakePage(), text_min_chars=9999) is None


def test_review_helpers() -> None:
    assert validate_markdown_text("") == ["empty_output"]
    table_warnings = validate_markdown_text("|a|b|")
    assert "isolated_table_row" in table_warnings
    assert "very_short_output" in validate_markdown_text("N/A")

    warnings = validate_markdown_text("A1B2C3 D4E5F6 " * 30)
    assert has_corruption_warning(warnings)
    assert has_severe_structure_warning(warnings)
    confidence = score_markdown_confidence("texto de qualidade", "text-layer", [])
    assert 0.0 < confidence <= 0.99
    assert "medical_validator_date_loss" in medical_validation_warnings(
        "Data 10/01/2024 valor 120",
        "Sem data valor 90",
    )
    assert medical_validation_warnings("x", "") == ["medical_validator_empty_output"]
    assert "needs_reprocess" in needs_reprocess_block(0, 0.12, 0.88)

    assert should_use_visual_qa(
        0.5,
        ["isolated_table_row"],
        "vision-ocr",
        enable_visual_qa=True,
        medical_strict=False,
        llm_enabled=True,
        qa_confidence_threshold=0.8,
    )
    assert should_use_cleanup(
        0.5,
        ["isolated_table_row"],
        "vision-ocr",
        enable_nlp_review=True,
        medical_strict=False,
        llm_enabled=True,
        cleanup_confidence_threshold=0.8,
    )
    assert not should_use_visual_qa(
        0.99,
        [],
        "text-layer",
        enable_visual_qa=False,
        medical_strict=False,
        llm_enabled=True,
        qa_confidence_threshold=0.8,
    )
    assert not should_use_cleanup(
        0.99,
        [],
        "text-layer",
        enable_nlp_review=False,
        medical_strict=False,
        llm_enabled=True,
        cleanup_confidence_threshold=0.8,
    )


def test_local_ocr_helpers_and_html_sanitization() -> None:
    assert normalize_ocr_confidence(90) == 0.9
    assert normalize_ocr_confidence("x") == 0.0
    assert normalize_local_ocr_language_token("pt-BR") == "pt"
    assert local_ocr_language_tokens("pt-BR,eng") == ["pt", "en"]
    assert easyocr_language_list("spa") == ["pt", "en"]
    assert tesseract_language("pt,en") == "por+eng"
    assert 0.0 < score_local_ocr_confidence("texto", 0.8, []) <= 0.99

    sanitized = sanitize_rendered_html(
        '<p>ok</p><script>alert(1)</script><a href="javascript:alert(1)">x</a>'
    )
    assert "<script>" not in sanitized
    assert "javascript:" not in sanitized

    try:
        from PIL import Image  # type: ignore[import-not-found]
    except Exception:
        pytest.skip("Pillow not installed")

    image = Image.new("RGB", (4, 4), color="white")
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    processed = preprocess_ocr_image(
        raw_bytes,
        enable_preprocess=True,
        autocontrast=True,
        sharpen=True,
        binarize_threshold=120,
    )
    assert processed
    passthrough = preprocess_ocr_image(
        raw_bytes,
        enable_preprocess=False,
        autocontrast=False,
        sharpen=False,
        binarize_threshold=0,
    )
    assert passthrough == raw_bytes

    rendered = render_html_document("# Titulo\n\n|a|b|\n|-|-|\n|1|2|")
    assert "<h1>Titulo</h1>" in rendered
    assert "<table>" in rendered
