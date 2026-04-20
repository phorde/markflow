"""Canonical state models for the API service runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    """Canonical lifecycle states for document jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PageProcessingStatus(str, Enum):
    """Page-level lifecycle states tracked by the API."""

    PENDING = "pending"
    STARTED = "started"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ArtifactStatus(str, Enum):
    """Lifecycle states for generated artifacts."""

    PENDING = "pending"
    READY = "ready"
    PURGED = "purged"


class RoutingDecisionTrace(BaseModel):
    """Explainable routing decision for a processed page."""

    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    task_kind: str = ""
    complexity: str = ""
    selected_model: str = ""
    fallback_models: List[str] = Field(default_factory=list)
    reason_lines: List[str] = Field(default_factory=list)
    benchmark_signal_summary: str = ""
    decision_timestamp: datetime = Field(default_factory=utc_now)


class PageState(BaseModel):
    """Canonical page-level processing state."""

    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    status: PageProcessingStatus = PageProcessingStatus.PENDING
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = ""
    warnings: List[str] = Field(default_factory=list)
    elapsed_seconds: float = Field(default=0.0, ge=0.0)
    qa_applied: bool = False
    cleanup_applied: bool = False
    llm_review_applied: bool = False
    routing_trace: RoutingDecisionTrace | None = None


class ReviewState(BaseModel):
    """Canonical review/edit lifecycle state prior to export."""

    model_config = ConfigDict(extra="forbid")

    markdown_draft: str = ""
    edited: bool = False
    low_confidence_pages: List[int] = Field(default_factory=list)
    reprocess_requests: List[int] = Field(default_factory=list)
    export_ready: bool = False


class ArtifactLifecycleState(BaseModel):
    """Canonical lifecycle state for uploaded/generated artifacts."""

    model_config = ConfigDict(extra="forbid")

    upload_state: ArtifactStatus = ArtifactStatus.PENDING
    markdown_state: ArtifactStatus = ArtifactStatus.PENDING
    report_state: ArtifactStatus = ArtifactStatus.PENDING
    expires_at: datetime | None = None
    last_purge_attempt_at: datetime | None = None


class JobState(BaseModel):
    """Canonical job state. Owned and mutated only by API."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    document_name: str
    page_count: int = Field(ge=1)
    execution_mode: str
    routing_mode: str
    status: JobStatus = JobStatus.QUEUED
    pages_completed: int = Field(default=0, ge=0)
    pages_failed: int = Field(default=0, ge=0)
    page_states: List[PageState] = Field(default_factory=list)
    review_state: ReviewState = Field(default_factory=ReviewState)
    artifact_state: ArtifactLifecycleState = Field(default_factory=ArtifactLifecycleState)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SseProgressEvent(BaseModel):
    """Required SSE event contract to keep UI/API aligned."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    page_number: int = Field(ge=1)
    status: PageProcessingStatus
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    routing_decision_summary: str = ""
    timestamp: datetime = Field(default_factory=utc_now)
