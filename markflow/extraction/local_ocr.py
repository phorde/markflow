"""Local OCR normalization and scoring helpers."""

from __future__ import annotations

import re
from typing import Any, List

import numpy as np

from .review import score_markdown_confidence


def normalize_ocr_confidence(raw_confidence: Any) -> float:
    """Normalize engine confidence to canonical [0.0, 1.0]."""
    try:
        if raw_confidence is None:
            return 0.0
        value = float(raw_confidence)
    except (TypeError, ValueError):
        return 0.0

    if not np.isfinite(value) or value < 0:
        return 0.0
    if value <= 1.0:
        return round(value, 3)
    if value <= 100.0:
        return round(value / 100.0, 3)
    return 0.0


def normalize_local_ocr_language_token(token: str) -> str:
    """Normalize local OCR language aliases to canonical short codes."""
    normalized = (token or "").strip().lower().replace("-", "_")
    aliases = {
        "": "",
        "pt": "pt",
        "por": "pt",
        "pt_br": "pt",
        "ptbr": "pt",
        "portuguese": "pt",
        "en": "en",
        "eng": "en",
        "english": "en",
    }
    return aliases.get(normalized, normalized)


def local_ocr_language_tokens(lang: str) -> List[str]:
    """Split and normalize language config into unique tokens."""
    raw_tokens = [token for token in re.split(r"[,+;|\s/]+", (lang or "").strip()) if token]
    normalized_tokens: List[str] = []
    for token in raw_tokens:
        normalized = normalize_local_ocr_language_token(token)
        if normalized and normalized not in normalized_tokens:
            normalized_tokens.append(normalized)
    if not normalized_tokens:
        return ["pt", "en"]
    return normalized_tokens


def easyocr_language_list(lang: str) -> List[str]:
    """Return EasyOCR-compatible language list from config string."""
    language_list = [token for token in local_ocr_language_tokens(lang) if token in {"pt", "en"}]
    if not language_list:
        return ["pt", "en"]
    return language_list


def tesseract_language(lang: str) -> str:
    """Convert normalized language tokens to Tesseract code string."""
    tokens = local_ocr_language_tokens(lang)
    if not tokens:  # pragma: no cover - local_ocr_language_tokens always returns defaults
        tokens = ["pt", "en"]
    mapped: List[str] = []
    for token in tokens:
        if token == "pt":
            mapped.append("por")
        elif token == "en":
            mapped.append("eng")
        else:
            mapped.append(token)
    return "+".join(mapped)


def score_local_ocr_confidence(text: str, local_confidence: float, warnings: List[str]) -> float:
    """Blend heuristic and provider confidence into bounded score."""
    heuristic = score_markdown_confidence(text, "local-ocr", warnings)
    if local_confidence <= 0:
        return heuristic
    return round(max(0.0, min(0.99, heuristic * 0.6 + local_confidence * 0.4)), 3)
