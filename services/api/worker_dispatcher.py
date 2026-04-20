"""Worker dispatch boundary for API service tests and local wiring."""

from __future__ import annotations

import asyncio

from dispatch import DispatchRequest
from state_models import PageProcessingStatus, SseProgressEvent
from state_store import JobStateStore


class InProcessWorkerDispatcher:
    """Local dispatcher used to bootstrap API/worker integration."""

    def __init__(self, state_store: JobStateStore) -> None:
        self._state_store = state_store

    def dispatch(self, request: DispatchRequest, api_key: str | None = None) -> None:
        """Dispatch processing task asynchronously without persisting API key."""
        asyncio.create_task(self._run(request, api_key))

    async def _run(self, request: DispatchRequest, api_key: str | None) -> None:
        routing = "local" if not api_key else "provider-configured"
        for page in range(1, request.page_count + 1):
            await self._state_store.apply_worker_event(
                SseProgressEvent(
                    job_id=request.job_id,
                    page_number=page,
                    status=PageProcessingStatus.STARTED,
                    confidence=0.0,
                    routing_decision_summary=f"{routing}:started",
                )
            )
            await asyncio.sleep(0)
            await self._state_store.apply_worker_event(
                SseProgressEvent(
                    job_id=request.job_id,
                    page_number=page,
                    status=PageProcessingStatus.PROCESSING,
                    confidence=0.5,
                    routing_decision_summary=f"{routing}:processing",
                )
            )
            await asyncio.sleep(0)
            await self._state_store.apply_worker_event(
                SseProgressEvent(
                    job_id=request.job_id,
                    page_number=page,
                    status=PageProcessingStatus.COMPLETED,
                    confidence=0.92,
                    routing_decision_summary=f"{routing}:completed",
                )
            )
            await asyncio.sleep(0)
