"""OCR-aware routing strategy inspired by route-based LLM orchestration."""

from __future__ import annotations

from typing import List

from .llm_types import BenchmarkSignal, DiscoveredModel, RoutingDecision
from .model_selection import select_best_model


def classify_task_kind(source: str, warnings: List[str], confidence: float) -> str:
    """Classify extraction workload into router task classes."""
    lowered_source = (source or "").lower()
    warning_set = set(warnings)

    if "text-layer" in lowered_source and confidence >= 0.86 and not warning_set:
        return "simple_text_extraction"

    if any("table" in warning for warning in warning_set):
        return "structured_document_extraction"

    if confidence < 0.72 or any(
        marker in warning_set
        for marker in ("very_short_output", "replacement_character_present", "isolated_table_row")
    ):
        return "complex_ocr_document"

    return "balanced_document_extraction"


def classify_complexity(page_has_text_layer: bool, image_count: int, word_count: int) -> str:
    """Classify PDF page complexity using low-cost heuristics."""
    if page_has_text_layer and image_count == 0 and word_count >= 100:
        return "low"
    if image_count >= 2 or word_count < 30:
        return "high"
    return "medium"


class OcrAwareRouter:
    """Route tasks to best-fit models with explainable fallback plans."""

    def route(
        self,
        task_kind: str,
        complexity: str,
        routing_mode: str,
        discovered_models: List[DiscoveredModel],
        benchmark_signals: List[BenchmarkSignal],
        require_vision: bool,
    ) -> RoutingDecision:
        """Return routing decision for a specific extraction task."""
        selector = select_best_model(
            discovered_models=discovered_models,
            benchmark_signals=benchmark_signals,
            routing_mode=routing_mode,
            require_vision=require_vision,
        )

        debug_lines = [
            f"task_kind={task_kind}",
            f"complexity={complexity}",
            f"routing_mode={routing_mode}",
            f"require_vision={require_vision}",
        ]
        debug_lines.extend(selector.reason_lines)
        debug_lines.extend(selector.tradeoff_lines)

        if selector.fallback_models:
            fallback_names = ", ".join(model.id for model in selector.fallback_models)
            debug_lines.append(f"fallback_candidates={fallback_names}")

        if (
            complexity == "high"
            and selector.selected_model is not None
            and selector.fallback_models
        ):
            debug_lines.append(
                "Escalation strategy active: retry with first fallback model on "
                "low confidence/failure."
            )

        return RoutingDecision(
            task_kind=task_kind,
            complexity=complexity,
            selected_model=selector.selected_model,
            fallback_models=selector.fallback_models,
            debug_lines=debug_lines,
            selector_result=selector,
        )
