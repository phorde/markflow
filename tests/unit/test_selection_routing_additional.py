from __future__ import annotations

import pytest

from markflow.llm_types import BenchmarkSignal, DiscoveredModel
from markflow.model_selection import select_best_model
from markflow.routing import OcrAwareRouter, classify_complexity, classify_task_kind

pytestmark = pytest.mark.unit


def test_select_best_model_no_eligible_chat_models() -> None:
    models = [
        DiscoveredModel("embed-1", "embed-1", False, False),
        DiscoveredModel("audio-1", "audio-1", False, False),
    ]
    result = select_best_model(models, [], "balanced", require_vision=False)
    assert result.selected_model is None
    assert result.fallback_models == []


def test_select_best_model_with_vision_requirement_degraded() -> None:
    models = [
        DiscoveredModel("generic-pro", "generic-pro", True, False, context_window=64000),
        DiscoveredModel("generic-mini", "generic-mini", True, False, context_window=32000),
    ]
    result = select_best_model(models, [], "balanced", require_vision=True)
    assert result.selected_model is not None
    assert any("vision capability flags" in line for line in result.reason_lines)


def test_classification_branches() -> None:
    assert classify_task_kind("text-layer", [], 0.9) == "simple_text_extraction"
    assert (
        classify_task_kind("vision-ocr", ["isolated_table_row"], 0.8)
        == "structured_document_extraction"
    )
    assert classify_task_kind("vision-ocr", ["very_short_output"], 0.4) == "complex_ocr_document"
    assert classify_complexity(True, 0, 120) == "low"
    assert classify_complexity(False, 3, 20) == "high"
    assert classify_complexity(False, 1, 80) == "medium"


def test_router_adds_high_complexity_escalation_debug_line() -> None:
    models = [
        DiscoveredModel("gpt-4o", "gpt-4o", True, True, context_window=128000),
        DiscoveredModel("gpt-4o-mini", "gpt-4o-mini", True, True, context_window=128000),
    ]
    signals = [
        BenchmarkSignal(
            source="ocrbench_v2",
            model_name="gpt-4o",
            normalized_model_name="gpt-4o",
            ocr_score=0.9,
            structured_extraction_score=0.9,
            context_stability_score=0.9,
            confidence=0.8,
        )
    ]
    decision = OcrAwareRouter().route(
        task_kind="remote_ocr",
        complexity="high",
        routing_mode="high-accuracy-ocr",
        discovered_models=models,
        benchmark_signals=signals,
        require_vision=True,
    )
    assert decision.selected_model is not None
    assert any("Escalation strategy active" in line for line in decision.debug_lines)
