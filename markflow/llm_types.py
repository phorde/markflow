"""Shared datatypes for provider-agnostic LLM orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DiscoveredModel:
    """Canonical representation for models discovered from /v1/models."""

    id: str
    normalized_id: str
    supports_chat: bool
    supports_vision: bool
    context_window: int = 0
    input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkSignal:
    """Benchmark evidence for OCR and document-understanding model quality."""

    source: str
    model_name: str
    normalized_model_name: str
    ocr_score: Optional[float] = None
    structured_extraction_score: Optional[float] = None
    context_stability_score: Optional[float] = None
    latency_score: Optional[float] = None
    cost_score: Optional[float] = None
    confidence: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelSelectionResult:
    """Selection result with explainable scoring breakdown."""

    selected_model: Optional[DiscoveredModel]
    fallback_models: List[DiscoveredModel]
    total_score: float
    component_scores: Dict[str, float]
    reason_lines: List[str]
    tradeoff_lines: List[str]
    influencing_signals: List[BenchmarkSignal]


@dataclass
class RoutingDecision:
    """Router output for one extraction task."""

    task_kind: str
    complexity: str
    selected_model: Optional[DiscoveredModel]
    fallback_models: List[DiscoveredModel]
    debug_lines: List[str]
    selector_result: Optional[ModelSelectionResult]


@dataclass
class LlmCallResult:
    """Normalized call result from OpenAI-compatible responses."""

    text: str
    model: str
    usage: Dict[str, Any] = field(default_factory=dict)
