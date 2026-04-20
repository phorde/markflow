"""FastAPI layer owned by the API service runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, AsyncGenerator
from contextlib import asynccontextmanager, suppress
from inspect import isawaitable
import json
from typing import Literal, Protocol
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from broker import (
    PROGRESS_STREAM,
    RESULT_STREAM,
    EventIdempotencyCache,
    RedisDispatchPublisher,
    RedisStreamsBroker,
)
from dispatch import DispatchRequest
from state_models import JobState, JobStatus, PageState, SseProgressEvent
from state_store import EventCursor, JobStateStore


class CreateJobRequest(BaseModel):
    """Client request to enqueue a document processing job."""

    model_config = ConfigDict(extra="forbid")

    document_name: str = Field(min_length=1)
    page_count: int = Field(ge=1, le=500)
    execution_mode: Literal["auto", "fast", "quality", "local", "remote"] = "auto"
    routing_mode: Literal["fast", "balanced", "high-accuracy-ocr"] = "balanced"


class CreateJobResponse(BaseModel):
    """Job creation response."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: str


class ReviewUpdateRequest(BaseModel):
    """Update request for editable review state."""

    model_config = ConfigDict(extra="forbid")

    markdown_draft: str | None = None
    edited: bool | None = None
    reprocess_requests: list[int] | None = None
    low_confidence_pages: list[int] | None = None
    export_ready: bool | None = None


class ExportResponse(BaseModel):
    """Export payload returned by the API."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    export_ready: bool
    markdown_draft: str
    json_snapshot: dict


class DispatcherProtocol(Protocol):
    """Minimal dispatch interface to preserve test DI support."""

    def dispatch(
        self, request: DispatchRequest, api_key: str | None = None
    ) -> Awaitable[None] | None:
        """Dispatch a newly created job."""


def create_app(
    state_store: JobStateStore | None = None,
    dispatcher: DispatcherProtocol | None = None,
) -> FastAPI:
    """Create FastAPI application with API-owned canonical state."""
    store = state_store or JobStateStore()
    broker = RedisStreamsBroker.from_env()
    dedupe = EventIdempotencyCache()
    active_dispatcher: DispatcherProtocol = dispatcher or RedisDispatchPublisher(broker)

    consumer_stop = asyncio.Event()
    consumer_task: asyncio.Task[None] | None = None

    async def _consume_worker_streams() -> None:
        group = "mf.api.reducer.v1"
        consumer = f"api-{uuid4()}"
        await broker.connect()
        await broker.ensure_group(PROGRESS_STREAM, group)
        await broker.ensure_group(RESULT_STREAM, group)

        while not consumer_stop.is_set():
            consumed = await broker.read_group(
                streams=[PROGRESS_STREAM, RESULT_STREAM],
                group=group,
                consumer=consumer,
                count=20,
                block_ms=1000,
            )
            for item in consumed:
                try:
                    event_id = str(item.envelope.get("event_id", "")).strip()
                    if event_id and dedupe.contains(event_id):
                        await broker.ack(
                            stream=item.stream,
                            group=group,
                            message_id=item.message_id,
                        )
                        continue
                    await store.apply_stream_event(item.envelope)
                    if event_id:
                        dedupe.record(event_id)
                    await broker.ack(stream=item.stream, group=group, message_id=item.message_id)
                except Exception as exc:
                    print(f"[WARN] stream_event_reduce_failed:{item.message_id}:{exc}")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        nonlocal consumer_task
        if dispatcher is None:
            consumer_stop.clear()
            consumer_task = asyncio.create_task(_consume_worker_streams())
        try:
            yield
        finally:
            consumer_stop.set()
            if consumer_task is not None:
                consumer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await consumer_task
            if dispatcher is None:
                await broker.close()

    app = FastAPI(title="MarkFlow API", version="1.0.0-web-foundation", lifespan=lifespan)

    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/api/jobs", response_model=CreateJobResponse)
    async def create_job(
        request: CreateJobRequest,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> CreateJobResponse:
        job = store.create_job(
            document_name=request.document_name,
            page_count=request.page_count,
            execution_mode=request.execution_mode,
            routing_mode=request.routing_mode,
        )

        dispatch_result = active_dispatcher.dispatch(
            DispatchRequest(
                job_id=job.job_id,
                page_count=job.page_count,
                execution_mode=job.execution_mode,
                routing_mode=job.routing_mode,
            ),
            api_key=x_api_key,
        )
        if isawaitable(dispatch_result):
            await dispatch_result
        return CreateJobResponse(job_id=job.job_id, status=job.status.value)

    @app.get("/api/jobs/{job_id}", response_model=JobState)
    async def get_job(job_id: str) -> JobState:
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        return job

    @app.get("/api/jobs/{job_id}/pages/{page_number}", response_model=PageState)
    async def get_page(job_id: str, page_number: int) -> PageState:
        page = store.get_page_state(job_id, page_number)
        if page is None:
            raise HTTPException(status_code=404, detail="page_not_found")
        return page

    @app.patch("/api/jobs/{job_id}/review", response_model=JobState)
    async def update_review(job_id: str, request: ReviewUpdateRequest) -> JobState:
        try:
            return store.update_review_state(
                job_id=job_id,
                markdown_draft=request.markdown_draft,
                edited=request.edited,
                reprocess_requests=request.reprocess_requests,
                low_confidence_pages=request.low_confidence_pages,
                export_ready=request.export_ready,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/jobs/{job_id}/export", response_model=ExportResponse)
    async def export_job(job_id: str) -> ExportResponse:
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        if job.status != JobStatus.COMPLETED or not job.review_state.export_ready:
            raise HTTPException(status_code=409, detail="job_not_ready_for_export")

        markdown_draft = job.review_state.markdown_draft or ""
        snapshot = job.model_dump(mode="json")
        return ExportResponse(
            job_id=job.job_id,
            export_ready=job.review_state.export_ready,
            markdown_draft=markdown_draft,
            json_snapshot=snapshot,
        )

    @app.post("/api/internal/jobs/{job_id}/events", response_model=JobState)
    async def ingest_worker_event(job_id: str, event: SseProgressEvent) -> JobState:
        if event.job_id != job_id:
            raise HTTPException(status_code=400, detail="job_id_mismatch")
        try:
            return await store.apply_worker_event(event)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/jobs/{job_id}/events")
    async def stream_job_events(job_id: str) -> StreamingResponse:
        if store.get_job(job_id) is None:
            raise HTTPException(status_code=404, detail="job_not_found")

        async def event_generator() -> AsyncGenerator[str, None]:
            cursor = EventCursor()
            while True:
                batch = await store.wait_for_events(job_id, cursor)
                if not batch:
                    job = store.get_job(job_id)
                    if job and job.status.value in {"completed", "failed"}:
                        break
                    yield ": keepalive\n\n"
                    continue
                for event in batch:
                    payload = json.dumps(event.model_dump(mode="json"))
                    yield f"data: {payload}\\n\\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return app
