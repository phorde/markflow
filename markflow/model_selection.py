"""OCR-aware model ranking and explainable selection logic."""

from __future__ import annotations

import math
from dataclasses import dataclass
from difflib import SequenceMatcher
from statistics import mean, pstdev
from typing import Dict, Iterable, List

from .llm_types import BenchmarkSignal, DiscoveredModel, ModelSelectionResult


@dataclass
class SelectionPolicy:
    """Policy weights for OCR-optimized model scoring."""

    ocr_weight: float
    structured_weight: float
    context_weight: float
    cost_weight: float
    latency_weight: float


_POLICY_BY_MODE = {
    "fast": SelectionPolicy(0.34, 0.16, 0.10, 0.22, 0.18),
    "balanced": SelectionPolicy(0.44, 0.22, 0.15, 0.11, 0.08),
    "high-accuracy-ocr": SelectionPolicy(0.54, 0.24, 0.15, 0.05, 0.02),
}


def _zscore(values: Iterable[float]) -> Dict[float, float]:
    numbers = list(values)
    if not numbers:
        return {}
    sigma = pstdev(numbers)
    if sigma <= 1e-9:
        return {value: 0.0 for value in numbers}
    mu = mean(numbers)
    return {value: (value - mu) / sigma for value in numbers}


def _normalize_z(value: float, mapping: Dict[float, float]) -> float:
    z = mapping.get(value, 0.0)
    # Squash z-score into [0, 1] with sigmoid.
    return 1.0 / (1.0 + math.exp(-z))


def _string_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    a_tokens = set(a.split("-"))
    b_tokens = set(b.split("-"))
    token_overlap = len(a_tokens.intersection(b_tokens)) / max(1, len(a_tokens.union(b_tokens)))
    return max(ratio, token_overlap)


def _match_signals(
    model: DiscoveredModel,
    signals: List[BenchmarkSignal],
) -> List[BenchmarkSignal]:
    matches: List[BenchmarkSignal] = []
    for signal in signals:
        score = _string_similarity(model.normalized_id, signal.normalized_model_name)
        if score >= 0.62:
            matches.append(signal)
    return matches


def _metric_from_signals(signals: List[BenchmarkSignal], field: str) -> float:
    values: List[float] = []
    weights: List[float] = []
    for signal in signals:
        raw = getattr(signal, field)
        if raw is None:
            continue
        values.append(float(raw))
        weights.append(max(0.1, signal.confidence))
    if not values:
        return -1.0
    weighted_sum = sum(value * weight for value, weight in zip(values, weights))
    total_weight = sum(weights)
    return weighted_sum / max(1e-9, total_weight)


def _heuristic_ocr_boost(model: DiscoveredModel) -> float:
    score = 0.35 if model.supports_vision else 0.15
    if model.context_window >= 128000:
        score += 0.12
    elif model.context_window >= 32000:
        score += 0.07
    if any(token in model.normalized_id for token in ("ocr", "vision", "vl", "omni")):
        score += 0.08
    return min(0.75, score)


def _cost_efficiency(model: DiscoveredModel) -> float:
    if model.input_cost_per_million is None and model.output_cost_per_million is None:
        return 0.5
    input_cost = model.input_cost_per_million or 0.0
    output_cost = model.output_cost_per_million or input_cost
    composite = input_cost * 0.4 + output_cost * 0.6
    # Lower is better; saturate around practical API pricing ranges.
    return max(0.0, min(1.0, 1.0 - (composite / 20.0)))


def _latency_proxy(model: DiscoveredModel) -> float:
    # In absence of provider telemetry, use model-scale proxy from identifier hints.
    if any(token in model.normalized_id for token in ("mini", "flash", "small", "nano")):
        return 0.85
    if any(token in model.normalized_id for token in ("pro", "large", "70b", "72b", "235b")):
        return 0.35
    return 0.6


def select_best_model(
    discovered_models: List[DiscoveredModel],
    benchmark_signals: List[BenchmarkSignal],
    routing_mode: str,
    require_vision: bool,
) -> ModelSelectionResult:
    """Select best model with OCR-first scoring and explainable rationale."""
    eligible_chat = [model for model in discovered_models if model.supports_chat]
    eligible = eligible_chat
    vision_requirement_degraded = False
    if require_vision:
        vision_eligible = [model for model in eligible_chat if model.supports_vision]
        if vision_eligible:
            eligible = vision_eligible
        else:
            # Some providers do not expose modality metadata in /models.
            # In that case, keep chat-capable models and score by benchmark/name heuristics.
            eligible = eligible_chat
            vision_requirement_degraded = True

    if not eligible:
        return ModelSelectionResult(
            selected_model=None,
            fallback_models=[],
            total_score=0.0,
            component_scores={},
            reason_lines=["No eligible chat models discovered from provider."],
            tradeoff_lines=["Verify API key, base URL, and /v1/models compatibility."],
            influencing_signals=[],
        )

    policy = _POLICY_BY_MODE.get(routing_mode, _POLICY_BY_MODE["balanced"])

    raw_ocr_values: List[float] = []
    raw_structured_values: List[float] = []
    raw_context_values: List[float] = []

    per_model_stats: Dict[str, Dict[str, float]] = {}
    matched_signals: Dict[str, List[BenchmarkSignal]] = {}

    for model in eligible:
        signals_for_model = _match_signals(model, benchmark_signals)
        matched_signals[model.id] = signals_for_model

        ocr_metric = _metric_from_signals(signals_for_model, "ocr_score")
        structured_metric = _metric_from_signals(signals_for_model, "structured_extraction_score")
        context_metric = _metric_from_signals(signals_for_model, "context_stability_score")

        if ocr_metric < 0:
            ocr_metric = _heuristic_ocr_boost(model)
        if structured_metric < 0:
            structured_metric = min(0.95, ocr_metric + 0.04)
        if context_metric < 0:
            if model.context_window > 0:
                context_metric = min(1.0, math.log10(model.context_window + 10) / 6.0)
            else:
                context_metric = 0.45

        raw_ocr_values.append(ocr_metric)
        raw_structured_values.append(structured_metric)
        raw_context_values.append(context_metric)

        per_model_stats[model.id] = {
            "ocr": ocr_metric,
            "structured": structured_metric,
            "context": context_metric,
            "cost": _cost_efficiency(model),
            "latency": _latency_proxy(model),
            "benchmark_coverage": float(len(signals_for_model)),
        }

    ocr_norm = _zscore(raw_ocr_values)
    structured_norm = _zscore(raw_structured_values)
    context_norm = _zscore(raw_context_values)

    ranked: List[tuple[DiscoveredModel, float, Dict[str, float]]] = []
    for model in eligible:
        stats = per_model_stats[model.id]

        ocr = _normalize_z(stats["ocr"], ocr_norm)
        structured = _normalize_z(stats["structured"], structured_norm)
        context = _normalize_z(stats["context"], context_norm)
        cost = stats["cost"]
        latency = stats["latency"]

        total = (
            policy.ocr_weight * ocr
            + policy.structured_weight * structured
            + policy.context_weight * context
            + policy.cost_weight * cost
            + policy.latency_weight * latency
        )

        components = {
            "ocr": round(ocr, 4),
            "structured_extraction": round(structured, 4),
            "context_stability": round(context, 4),
            "cost_efficiency": round(cost, 4),
            "latency_proxy": round(latency, 4),
            "benchmark_matches": round(stats["benchmark_coverage"], 2),
        }
        ranked.append((model, total, components))

    ranked.sort(key=lambda item: item[1], reverse=True)
    selected_model, best_score, component_scores = ranked[0]
    fallback_models = [item[0] for item in ranked[1:3]]

    coverage = len(matched_signals[selected_model.id])
    reasons = [
        f"Selected '{selected_model.id}' with OCR-first weighted score {best_score:.3f}.",
        (
            f"Benchmark evidence matched {coverage} signal(s) across OCRBench sources."
            if coverage > 0
            else "No direct benchmark match; selection used metadata heuristics and normalization fallback."
        ),
        (
            f"OCR/structured/context components: {component_scores['ocr']:.3f} / "
            f"{component_scores['structured_extraction']:.3f} / "
            f"{component_scores['context_stability']:.3f}."
        ),
    ]

    if vision_requirement_degraded:
        reasons.append(
            "Provider did not expose explicit vision capability flags; ranking used benchmark/name heuristics for chat-capable models."
        )

    tradeoffs = [
        (
            "Higher OCR accuracy favored over cost due to routing mode."
            if routing_mode == "high-accuracy-ocr"
            else "Balanced tradeoff between OCR quality, cost, and latency."
        ),
        f"Estimated cost efficiency: {component_scores['cost_efficiency']:.3f}.",
        f"Latency proxy score: {component_scores['latency_proxy']:.3f}.",
    ]

    return ModelSelectionResult(
        selected_model=selected_model,
        fallback_models=fallback_models,
        total_score=round(best_score, 4),
        component_scores=component_scores,
        reason_lines=reasons,
        tradeoff_lines=tradeoffs,
        influencing_signals=matched_signals[selected_model.id],
    )
