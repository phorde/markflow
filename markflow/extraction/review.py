"""Review, validation and confidence policy helpers."""

from __future__ import annotations

import re
from typing import List

from .page_analysis import word_count


def validate_markdown_text(text: str) -> List[str]:
    """Run structural and corruption heuristics over markdown output."""
    warnings: List[str] = []
    normalized = (text or "").strip()
    if not normalized:
        warnings.append("empty_output")
        return warnings

    if normalized.count("|") >= 2:
        table_lines = [line for line in normalized.splitlines() if "|" in line]
        if len(table_lines) == 1:
            warnings.append("isolated_table_row")
        if any(len(line.split("|")) <= 2 for line in table_lines):
            warnings.append("weak_table_structure")

    if re.search(r"\b(?:UNK|N/?A|nan|null|None)\b", normalized, flags=re.IGNORECASE):
        warnings.append("suspicious_placeholder_tokens")

    if re.search(r"[\uFFFD]{1,}", normalized):
        warnings.append("replacement_character_present")

    if len(normalized) < 20:
        warnings.append("very_short_output")

    tokens = re.findall(r"\b[\wÀ-ÿ]+\b", normalized, flags=re.UNICODE)
    alpha_tokens = [token for token in tokens if re.search(r"[A-Za-zÀ-ÿ]", token)]
    if len(alpha_tokens) >= 40:
        vowel_pattern = re.compile(r"[aeiouAEIOUÀ-ÿ]")
        no_vowel_ratio = sum(
            1 for token in alpha_tokens if len(token) >= 5 and not vowel_pattern.search(token)
        ) / max(1, len(alpha_tokens))
        single_char_ratio = sum(1 for token in alpha_tokens if len(token) == 1) / max(
            1, len(alpha_tokens)
        )
        alnum_mix_ratio = sum(
            1
            for token in alpha_tokens
            if len(token) >= 4 and re.search(r"[A-Za-zÀ-ÿ]", token) and re.search(r"\d", token)
        ) / max(1, len(alpha_tokens))

        if no_vowel_ratio >= 0.18:
            warnings.append("garbled_no_vowel_token_ratio")
        if single_char_ratio >= 0.30:
            warnings.append("garbled_single_char_ratio")
        if alnum_mix_ratio >= 0.12:
            warnings.append("garbled_alnum_mix_ratio")

    weird_char_ratio = len(
        re.findall(r"[^\w\sÀ-ÿ.,;:!?()\[\]{}\-_/\\|%$#+=*'\"\n]", normalized)
    ) / max(1, len(normalized))
    if weird_char_ratio >= 0.04:
        warnings.append("garbled_symbol_density")

    return warnings


def has_corruption_warning(warnings: List[str]) -> bool:
    """Return whether warning list contains OCR corruption signals."""
    corruption_flags = {
        "garbled_no_vowel_token_ratio",
        "garbled_single_char_ratio",
        "garbled_alnum_mix_ratio",
        "garbled_symbol_density",
    }
    return any(warning in corruption_flags for warning in warnings)


def has_severe_structure_warning(warnings: List[str]) -> bool:
    """Return whether warning list contains fail-critical structure issues."""
    severe = {
        "empty_output",
        "very_short_output",
        "isolated_table_row",
        "replacement_character_present",
        "garbled_no_vowel_token_ratio",
        "garbled_single_char_ratio",
        "garbled_alnum_mix_ratio",
        "garbled_symbol_density",
    }
    return any(warning in severe for warning in warnings)


def extract_numeric_tokens(text: str) -> List[str]:
    return re.findall(r"\b\d+(?:[.,]\d+)?\b", text or "")


def extract_date_tokens(text: str) -> List[str]:
    return re.findall(
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b",
        text or "",
    )


def medical_validation_warnings(reference_text: str, candidate_text: str) -> List[str]:
    """Detect clinically relevant drift between baseline and candidate output."""
    warnings: List[str] = []
    ref = (reference_text or "").strip()
    cand = (candidate_text or "").strip()

    if not cand:
        return ["medical_validator_empty_output"]

    ref_nums = extract_numeric_tokens(ref)
    cand_nums = extract_numeric_tokens(cand)
    if ref_nums:
        overlap = sum(1 for token in ref_nums if token in cand_nums)
        ratio = overlap / max(1, len(ref_nums))
        if ratio < 0.75:
            warnings.append(f"medical_validator_numeric_mismatch:{ratio:.2f}")

    ref_dates = extract_date_tokens(ref)
    cand_dates = extract_date_tokens(cand)
    if ref_dates and not cand_dates:
        warnings.append("medical_validator_date_loss")

    if len(cand) < 24:
        warnings.append("medical_validator_too_short")

    return warnings


def score_markdown_confidence(text: str, source: str, warnings: List[str]) -> float:
    """Compute bounded confidence for markdown output quality."""
    if not (text or "").strip():
        return 0.0

    wc = word_count(text)
    confidence = 0.90 if source == "text-layer" else 0.84
    confidence += min(0.05, len(text) / 8000.0)
    confidence += min(0.05, wc / 900.0)
    confidence -= 0.08 * len(warnings)
    if has_severe_structure_warning(warnings):
        confidence -= 0.05
    if has_corruption_warning(warnings):
        confidence -= 0.22
    if re.search(r"\[Page \d+ failed:", text or ""):
        confidence = 0.0
    return round(max(0.0, min(confidence, 0.99)), 3)


def should_use_visual_qa(
    confidence: float,
    warnings: List[str],
    source: str,
    *,
    enable_visual_qa: bool,
    medical_strict: bool,
    llm_enabled: bool,
    qa_confidence_threshold: float,
) -> bool:
    if not enable_visual_qa:
        return False
    if source == "text-layer" and medical_strict and llm_enabled:
        return True
    if has_corruption_warning(warnings):
        return True
    if source == "text-layer":
        return confidence < qa_confidence_threshold and has_severe_structure_warning(warnings)
    return confidence < qa_confidence_threshold or has_severe_structure_warning(warnings)


def should_use_cleanup(
    confidence: float,
    warnings: List[str],
    source: str,
    *,
    enable_nlp_review: bool,
    medical_strict: bool,
    llm_enabled: bool,
    cleanup_confidence_threshold: float,
) -> bool:
    if not enable_nlp_review:
        return False
    if source == "text-layer" and medical_strict and llm_enabled:
        return True
    if has_corruption_warning(warnings):
        return True
    if source == "text-layer":
        return confidence < cleanup_confidence_threshold and has_severe_structure_warning(warnings)
    return confidence < cleanup_confidence_threshold and has_severe_structure_warning(warnings)


def needs_reprocess_block(page_index: int, confidence: float, min_confidence: float) -> str:
    """Build explicit fail-closed text block for low-confidence pages."""
    return (
        f"\n[Page {page_index + 1} status: needs_reprocess; "
        f"confidence {confidence:.3f} below minimum {min_confidence:.3f}]\n"
    )
