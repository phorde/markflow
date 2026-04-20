"""Ingestion and normalization of OCR-related benchmark evidence.

Canonical benchmark policy:
- The system uses OCRBench v2 as the single benchmark source.
- Other benchmark URLs are documented for feasibility context only, not runtime scoring.
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from statistics import mean
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .llm_client import normalize_model_identifier
from .llm_types import BenchmarkSignal

CANONICAL_OCR_BENCHMARK_URL = "https://99franklin.github.io/ocrbench_v2/"


@dataclass
class _AggregatedSignal:
    model_name: str
    ocr_scores: List[float] = field(default_factory=list)
    structured_scores: List[float] = field(default_factory=list)
    context_scores: List[float] = field(default_factory=list)
    metric_counts: List[float] = field(default_factory=list)


def _fetch(url: str, timeout_seconds: int) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "ExtratorLaudos/2.0"})
    with urllib.request.urlopen(request, timeout=max(3, timeout_seconds)) as response:  # nosec B310
        return response.read().decode("utf-8", errors="ignore")


def _parse_ocrbench_v2(content: str) -> List[BenchmarkSignal]:
    """Parse OCRBench v2 leaderboard from HTML tables or legacy markdown rows."""
    signals = _parse_ocrbench_v2_html(content)
    if signals:
        return signals
    return _parse_ocrbench_v2_markdown_rows(content)


def _parse_ocrbench_v2_markdown_rows(content: str) -> List[BenchmarkSignal]:
    """Legacy parser for markdown-like leaderboard rows."""
    signals: List[BenchmarkSignal] = []
    # OCRBench v2 legacy rows expose many metrics; we aggregate available floats per row.
    row_pattern = re.compile(r"\|\s*\d+\s*\|\s*([^|]{2,100})\|([^\n]+)")
    float_pattern = re.compile(r"\b\d{1,3}(?:\.\d+)?\b")

    for model_name, rest in row_pattern.findall(content):
        metrics = [float(value) for value in float_pattern.findall(rest) if float(value) <= 100.0]
        if len(metrics) < 3:
            continue
        avg_metric = mean(metrics) / 100.0
        structured = mean(metrics[-3:]) / 100.0 if len(metrics) >= 3 else avg_metric
        signals.append(
            BenchmarkSignal(
                source="ocrbench_v2",
                model_name=model_name.strip(),
                normalized_model_name=normalize_model_identifier(model_name),
                ocr_score=avg_metric,
                structured_extraction_score=structured,
                context_stability_score=metrics[0] / 100.0,
                confidence=0.75,
                metadata={"url": CANONICAL_OCR_BENCHMARK_URL, "metric_count": len(metrics)},
            )
        )
    return signals


def _parse_ocrbench_v2_html(content: str) -> List[BenchmarkSignal]:
    """Parse OCRBench v2 from HTML leaderboard tables.

    The website currently renders leaderboard rows as HTML <tr>/<td> blocks,
    not markdown pipe tables. This parser extracts rows and aggregates repeated
    model entries across sections/periods.
    """
    row_blocks = re.findall(r"<tr\b[^>]*>(.*?)</tr>", content, flags=re.IGNORECASE | re.DOTALL)
    if not row_blocks:
        return []

    by_model: Dict[str, _AggregatedSignal] = {}

    for row_html in row_blocks:
        cell_blocks = re.findall(
            r"<td\b[^>]*>(.*?)</td>",
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if len(cell_blocks) < 6:
            continue

        cell_texts: List[str] = []
        for raw_cell in cell_blocks:
            # Remove HTML tags and decode entities for robust plain-text parsing.
            text = re.sub(r"<[^>]+>", " ", raw_cell)
            text = html.unescape(text)
            text = re.sub(r"\s+", " ", text).strip()
            cell_texts.append(text)

        rank_cell = cell_texts[0]
        if not re.fullmatch(r"\d{1,3}", rank_cell):
            continue

        model_name = re.sub(r"[🥇🥈🥉]", "", cell_texts[1]).strip()
        if not model_name:
            continue

        numeric_metrics: List[float] = []
        for value in cell_texts[2:]:
            if not re.fullmatch(r"\d{1,3}(?:\.\d+)?", value):
                continue
            numeric_value = float(value)
            if 0.0 <= numeric_value <= 100.0:
                numeric_metrics.append(numeric_value)

        if len(numeric_metrics) < 3:
            continue

        normalized = normalize_model_identifier(model_name)
        entry = by_model.setdefault(normalized, _AggregatedSignal(model_name=model_name))
        avg_metric = mean(numeric_metrics) / 100.0
        structured = mean(numeric_metrics[-3:]) / 100.0
        context = numeric_metrics[0] / 100.0
        entry.ocr_scores.append(avg_metric)
        entry.structured_scores.append(structured)
        entry.context_scores.append(context)
        entry.metric_counts.append(float(len(numeric_metrics)))

    signals: List[BenchmarkSignal] = []
    for normalized, entry in by_model.items():
        ocr_scores = entry.ocr_scores
        structured_scores = entry.structured_scores
        context_scores = entry.context_scores
        metric_counts = entry.metric_counts
        if not ocr_scores:  # pragma: no cover - entries are only created after a score append
            continue

        signals.append(
            BenchmarkSignal(
                source="ocrbench_v2",
                model_name=entry.model_name,
                normalized_model_name=normalized,
                ocr_score=mean(ocr_scores),
                structured_extraction_score=mean(structured_scores),
                context_stability_score=mean(context_scores),
                confidence=0.78,
                metadata={
                    "url": CANONICAL_OCR_BENCHMARK_URL,
                    "row_count": len(ocr_scores),
                    "avg_metric_count": round(mean(metric_counts), 2),
                    "parser": "html_table",
                },
            )
        )
    return signals


def collect_ocr_benchmark_signals(
    timeout_seconds: int = 8,
) -> Tuple[List[BenchmarkSignal], List[str]]:
    """Collect and normalize OCR benchmark signals from canonical OCRBench v2.

    Returns:
        Tuple of signals list and ingestion warnings.
    """
    warnings: List[str] = []
    signals: List[BenchmarkSignal] = []

    try:
        raw = _fetch(CANONICAL_OCR_BENCHMARK_URL, timeout_seconds)
        signals = _parse_ocrbench_v2(raw)
        if not signals:  # pragma: no branch - empty and non-empty paths are covered separately
            warnings.append(f"benchmark_empty:{CANONICAL_OCR_BENCHMARK_URL}")
    except urllib.error.URLError as exc:
        warnings.append(f"benchmark_unreachable:{CANONICAL_OCR_BENCHMARK_URL}:{exc}")
    except Exception as exc:
        warnings.append(f"benchmark_parse_failed:{CANONICAL_OCR_BENCHMARK_URL}:{exc}")

    if not signals:  # pragma: no branch - warning-only branch is covered by ingestion tests
        warnings.append("benchmark_signals_missing:falling_back_to_metadata_heuristics")

    return signals, warnings
