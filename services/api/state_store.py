"""API-owned canonical job state store."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List
from uuid import uuid4

from state_models import (
    ArtifactStatus,
    JobState,
    JobStatus,
    PageProcessingStatus,
    PageState,
    RoutingDecisionTrace,
    ReviewState,
    SseProgressEvent,
    utc_now,
)


@dataclass
class EventCursor:
    """Track streamed event offset per subscriber."""

    index: int = 0


class JobStateStore:
    """In-memory state store where API owns all job mutations."""

    def __init__(self) -> None:
        self._jobs: Dict[str, JobState] = {}
        self._events: Dict[str, List[SseProgressEvent]] = {}
        self._conditions: Dict[str, asyncio.Condition] = {}
        self._applied_event_ids: set[str] = set()

    @staticmethod
    def _status_rank(status: PageProcessingStatus) -> int:
        """Rank statuses to enforce monotonic lifecycle progression."""
        ranking = {
            PageProcessingStatus.PENDING: 0,
            PageProcessingStatus.STARTED: 1,
            PageProcessingStatus.PROCESSING: 2,
            PageProcessingStatus.COMPLETED: 3,
            PageProcessingStatus.FAILED: 3,
        }
        return ranking[status]

    def _recompute_job_aggregates(self, job: JobState) -> None:
        """Recompute deterministic aggregates from page states."""
        job.pages_completed = sum(
            1 for p in job.page_states if p.status == PageProcessingStatus.COMPLETED
        )
        job.pages_failed = sum(
            1 for p in job.page_states if p.status == PageProcessingStatus.FAILED
        )
        job.updated_at = utc_now()

        if job.pages_failed > 0:
            job.status = JobStatus.FAILED
        elif job.pages_completed == job.page_count:
            job.status = JobStatus.COMPLETED
            job.artifact_state.markdown_state = ArtifactStatus.READY
            job.artifact_state.report_state = ArtifactStatus.READY
            job.review_state.low_confidence_pages = [
                p.page_number for p in job.page_states if p.confidence < 0.7
            ]
            job.review_state.export_ready = len(job.review_state.low_confidence_pages) == 0
        else:
            any_active = any(
                p.status in (PageProcessingStatus.STARTED, PageProcessingStatus.PROCESSING)
                for p in job.page_states
            )
            job.status = JobStatus.RUNNING if any_active else JobStatus.QUEUED

    async def _notify_job_update(self, job_id: str) -> None:
        """Wake SSE subscribers waiting on job events."""
        condition = self._conditions[job_id]
        async with condition:
            condition.notify_all()

    async def _apply_sse_event(self, event: SseProgressEvent) -> JobState:
        """Apply a single SSE event with monotonic transition checks."""
        job = self._jobs.get(event.job_id)
        if job is None:
            raise KeyError(f"job_not_found:{event.job_id}")

        page = next((p for p in job.page_states if p.page_number == event.page_number), None)
        if page is None:
            raise KeyError(f"page_not_found:{event.page_number}")

        if self._status_rank(event.status) < self._status_rank(page.status):
            return job

        page.status = event.status
        page.confidence = event.confidence
        page.routing_trace = RoutingDecisionTrace(
            page_number=event.page_number,
            benchmark_signal_summary=event.routing_decision_summary,
        )

        if event.status == PageProcessingStatus.COMPLETED:
            page.source = page.source or "worker"
        if event.status == PageProcessingStatus.FAILED:
            page.warnings = list(set(page.warnings + ["page_failed"]))

        self._recompute_job_aggregates(job)
        self._events[event.job_id].append(event)
        await self._notify_job_update(event.job_id)
        return job

    async def apply_stream_event(self, envelope: dict) -> JobState | None:
        """Reduce stream event envelope into canonical state with idempotency."""
        event_id = str(envelope.get("event_id", "")).strip()
        if not event_id:
            raise ValueError("missing_event_id")
        if event_id in self._applied_event_ids:
            return None

        event_type = envelope.get("event_type")
        job_id = envelope.get("job_id")
        page_number = envelope.get("page_number")
        payload = envelope.get("payload") or {}
        if not isinstance(payload, dict):
            raise ValueError("invalid_payload")

        if not isinstance(page_number, int):
            return None

        if event_type == "progress.event.v1":
            raw_status = str(payload.get("status", ""))
            confidence = float(payload.get("confidence", 0.0))
            routing = str(payload.get("message", ""))
            mapping = {
                "accepted": PageProcessingStatus.STARTED,
                "started": PageProcessingStatus.STARTED,
                "processing_page": PageProcessingStatus.PROCESSING,
                "retrying": PageProcessingStatus.PROCESSING,
                "completed_page": PageProcessingStatus.COMPLETED,
            }
            target_status = mapping.get(raw_status)
        elif event_type == "result.event.v1":
            raw_status = str(payload.get("status", ""))
            confidence = float(payload.get("confidence", 1.0))
            routing = str(payload.get("output_uri", ""))
            mapping = {
                "success": PageProcessingStatus.COMPLETED,
                "partial": PageProcessingStatus.COMPLETED,
                "failed": PageProcessingStatus.FAILED,
            }
            target_status = mapping.get(raw_status)
        else:
            return None

        if target_status is None:
            return None

        event = SseProgressEvent(
            job_id=str(job_id),
            page_number=page_number,
            status=target_status,
            confidence=max(0.0, min(1.0, confidence)),
            routing_decision_summary=routing,
        )
        updated = await self._apply_sse_event(event)
        self._applied_event_ids.add(event_id)
        return updated

    def create_job(
        self,
        document_name: str,
        page_count: int,
        execution_mode: str,
        routing_mode: str,
    ) -> JobState:
        """Create canonical job state in queued state."""
        job_id = str(uuid4())
        page_states = [PageState(page_number=n) for n in range(1, page_count + 1)]
        job = JobState(
            job_id=job_id,
            document_name=document_name,
            page_count=page_count,
            execution_mode=execution_mode,
            routing_mode=routing_mode,
            page_states=page_states,
        )
        self._jobs[job_id] = job
        self._events[job_id] = []
        self._conditions[job_id] = asyncio.Condition()
        return job

    def get_job(self, job_id: str) -> JobState | None:
        """Get canonical job state."""
        return self._jobs.get(job_id)

    async def apply_worker_event(self, event: SseProgressEvent) -> JobState:
        """Apply worker event into canonical state and enqueue SSE event."""
        return await self._apply_sse_event(event)

    async def wait_for_events(
        self,
        job_id: str,
        cursor: EventCursor,
        timeout_seconds: float = 15.0,
    ) -> List[SseProgressEvent]:
        """Wait for new events after cursor position and return batch."""
        if job_id not in self._jobs:
            raise KeyError(f"job_not_found:{job_id}")
        current = self._events[job_id]
        if cursor.index < len(current):
            batch = current[cursor.index :]
            cursor.index = len(current)
            return batch

        condition = self._conditions[job_id]
        try:
            async with condition:
                await asyncio.wait_for(condition.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return []

        updated = self._events[job_id]
        if cursor.index < len(updated):
            batch = updated[cursor.index :]
            cursor.index = len(updated)
            return batch
        return []

    def get_page_state(self, job_id: str, page_number: int) -> PageState | None:
        """Return a single page state for inspection."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return next((page for page in job.page_states if page.page_number == page_number), None)

    def update_review_state(
        self,
        job_id: str,
        markdown_draft: str | None = None,
        edited: bool | None = None,
        reprocess_requests: List[int] | None = None,
        low_confidence_pages: List[int] | None = None,
        export_ready: bool | None = None,
    ) -> JobState:
        """Update canonical review state owned by the API."""
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"job_not_found:{job_id}")

        review = ReviewState.model_validate(job.review_state.model_dump())
        if markdown_draft is not None:
            review.markdown_draft = markdown_draft
        if edited is not None:
            review.edited = edited
        if reprocess_requests is not None:
            review.reprocess_requests = list(reprocess_requests)
        if low_confidence_pages is not None:
            review.low_confidence_pages = list(low_confidence_pages)
        if export_ready is not None:
            review.export_ready = export_ready

        job.review_state = review
        job.updated_at = utc_now()
        return job
