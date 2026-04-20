"""Unit tests for MarkFlow web foundation modules."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Service-owned API runtime modules live under services/api.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from api import create_app  # noqa: E402
from broker import DISPATCH_STREAM, EventIdempotencyCache, RedisStreamsBroker  # noqa: E402
from dispatch import DispatchRequest  # noqa: E402
from state_models import (  # noqa: E402
    JobStatus,
    PageProcessingStatus,
    SseProgressEvent,
    utc_now,
)  # noqa: E402
from state_store import EventCursor, JobStateStore  # noqa: E402
from worker_dispatcher import InProcessWorkerDispatcher  # noqa: E402


@pytest.mark.unit
def test_utc_now_timezone_aware() -> None:
    assert utc_now().tzinfo is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_state_store_completes_job_and_marks_review_ready() -> None:
    store = JobStateStore()
    job = store.create_job("doc.pdf", page_count=2, execution_mode="auto", routing_mode="balanced")

    for page in (1, 2):
        await store.apply_worker_event(
            SseProgressEvent(
                job_id=job.job_id,
                page_number=page,
                status=PageProcessingStatus.COMPLETED,
                confidence=0.95,
                routing_decision_summary="ok",
            )
        )

    updated = store.get_job(job.job_id)
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED
    assert updated.pages_completed == 2
    assert updated.pages_failed == 0
    assert updated.review_state.export_ready is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_state_store_failed_event_sets_failed_status() -> None:
    store = JobStateStore()
    job = store.create_job("doc.pdf", page_count=1, execution_mode="auto", routing_mode="balanced")

    await store.apply_worker_event(
        SseProgressEvent(
            job_id=job.job_id,
            page_number=1,
            status=PageProcessingStatus.FAILED,
            confidence=0.1,
            routing_decision_summary="failed-route",
        )
    )

    updated = store.get_job(job.job_id)
    assert updated is not None
    assert updated.status == JobStatus.FAILED
    assert updated.pages_failed == 1
    assert "page_failed" in updated.page_states[0].warnings


@pytest.mark.unit
@pytest.mark.asyncio
async def test_state_store_event_for_unknown_job_raises() -> None:
    store = JobStateStore()

    with pytest.raises(KeyError):
        await store.apply_worker_event(
            SseProgressEvent(
                job_id="missing-job",
                page_number=1,
                status=PageProcessingStatus.STARTED,
                confidence=0.0,
                routing_decision_summary="start",
            )
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_state_store_event_for_unknown_page_raises() -> None:
    store = JobStateStore()
    job = store.create_job("doc.pdf", page_count=1, execution_mode="auto", routing_mode="balanced")

    with pytest.raises(KeyError):
        await store.apply_worker_event(
            SseProgressEvent(
                job_id=job.job_id,
                page_number=99,
                status=PageProcessingStatus.STARTED,
                confidence=0.0,
                routing_decision_summary="start",
            )
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_state_store_started_event_transitions_job_to_running() -> None:
    store = JobStateStore()
    job = store.create_job("doc.pdf", page_count=1, execution_mode="auto", routing_mode="balanced")

    assert store.get_job(job.job_id) is not None
    assert store.get_job(job.job_id).status == JobStatus.QUEUED

    await store.apply_worker_event(
        SseProgressEvent(
            job_id=job.job_id,
            page_number=1,
            status=PageProcessingStatus.STARTED,
            confidence=0.0,
            routing_decision_summary="start",
        )
    )

    updated = store.get_job(job.job_id)
    assert updated is not None
    assert updated.status == JobStatus.RUNNING


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_for_events_cursor_and_timeout() -> None:
    store = JobStateStore()
    job = store.create_job("doc.pdf", page_count=1, execution_mode="auto", routing_mode="balanced")
    cursor = EventCursor()

    empty = await store.wait_for_events(job.job_id, cursor, timeout_seconds=0.001)
    assert empty == []

    await store.apply_worker_event(
        SseProgressEvent(
            job_id=job.job_id,
            page_number=1,
            status=PageProcessingStatus.STARTED,
            confidence=0.0,
            routing_decision_summary="start",
        )
    )

    batch = await store.wait_for_events(job.job_id, cursor, timeout_seconds=0.001)
    assert len(batch) == 1
    assert batch[0].status == PageProcessingStatus.STARTED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_for_events_unknown_job_raises() -> None:
    store = JobStateStore()
    cursor = EventCursor()

    with pytest.raises(KeyError):
        await store.wait_for_events("missing-job", cursor, timeout_seconds=0.001)


class CapturingDispatcher:
    """Test helper dispatcher that captures dispatch payload."""

    def __init__(self) -> None:
        self.calls: list[tuple[DispatchRequest, str | None]] = []

    def dispatch(self, request: DispatchRequest, api_key: str | None = None) -> None:
        self.calls.append((request, api_key))


@pytest.mark.unit
def test_api_create_job_dispatches_without_persisting_api_key() -> None:
    store = JobStateStore()
    dispatcher = CapturingDispatcher()
    app = create_app(state_store=store, dispatcher=dispatcher)  # type: ignore[arg-type]
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        json={
            "document_name": "a.pdf",
            "page_count": 1,
            "execution_mode": "auto",
            "routing_mode": "balanced",
        },
        headers={"X-API-Key": "top-secret"},
    )

    assert response.status_code == 200
    body = response.json()
    job_id = body["job_id"]
    assert dispatcher.calls
    request, key = dispatcher.calls[0]
    assert request.job_id == job_id
    assert key == "top-secret"

    state = store.get_job(job_id)
    assert state is not None
    dumped = state.model_dump_json()
    assert "top-secret" not in dumped
    assert "api_key" not in dumped


@pytest.mark.unit
def test_api_get_job_and_internal_event_validation() -> None:
    store = JobStateStore()
    dispatcher = CapturingDispatcher()
    app = create_app(state_store=store, dispatcher=dispatcher)  # type: ignore[arg-type]
    client = TestClient(app)

    create = client.post(
        "/api/jobs",
        json={
            "document_name": "a.pdf",
            "page_count": 1,
            "execution_mode": "auto",
            "routing_mode": "balanced",
        },
    )
    job_id = create.json()["job_id"]

    fetched = client.get(f"/api/jobs/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["job_id"] == job_id

    mismatch = client.post(
        f"/api/internal/jobs/{job_id}/events",
        json={
            "job_id": "other",
            "page_number": 1,
            "status": "started",
            "confidence": 0.2,
            "routing_decision_summary": "r",
            "timestamp": utc_now().isoformat(),
        },
    )
    assert mismatch.status_code == 400


@pytest.mark.unit
def test_api_get_job_and_stream_not_found_return_404() -> None:
    store = JobStateStore()
    dispatcher = CapturingDispatcher()
    app = create_app(state_store=store, dispatcher=dispatcher)  # type: ignore[arg-type]
    client = TestClient(app)

    assert client.get("/api/jobs/missing").status_code == 404
    assert client.get("/api/jobs/missing/events").status_code == 404


@pytest.mark.unit
def test_api_internal_event_for_missing_job_returns_404() -> None:
    store = JobStateStore()
    dispatcher = CapturingDispatcher()
    app = create_app(state_store=store, dispatcher=dispatcher)  # type: ignore[arg-type]
    client = TestClient(app)

    response = client.post(
        "/api/internal/jobs/missing/events",
        json={
            "job_id": "missing",
            "page_number": 1,
            "status": "started",
            "confidence": 0.2,
            "routing_decision_summary": "r",
            "timestamp": utc_now().isoformat(),
        },
    )
    assert response.status_code == 404


@pytest.mark.unit
def test_api_sse_stream_emits_required_contract_fields() -> None:
    store = JobStateStore()
    dispatcher = CapturingDispatcher()
    app = create_app(state_store=store, dispatcher=dispatcher)  # type: ignore[arg-type]
    client = TestClient(app)

    created = client.post(
        "/api/jobs",
        json={
            "document_name": "a.pdf",
            "page_count": 1,
            "execution_mode": "auto",
            "routing_mode": "balanced",
        },
    )
    job_id = created.json()["job_id"]

    event = {
        "job_id": job_id,
        "page_number": 1,
        "status": "completed",
        "confidence": 0.99,
        "routing_decision_summary": "done",
        "timestamp": utc_now().isoformat(),
    }
    pushed = client.post(f"/api/internal/jobs/{job_id}/events", json=event)
    assert pushed.status_code == 200

    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        lines = list(response.iter_lines())
        payload_line = next((line for line in lines if line.startswith("data: ")), None)
        assert payload_line is not None
        payload = payload_line.removeprefix("data: ")
        assert '"job_id"' in payload
        assert '"page_number"' in payload
        assert '"status"' in payload
        assert '"confidence"' in payload
        assert '"routing_decision_summary"' in payload
        assert '"timestamp"' in payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_process_dispatcher_run_emits_events() -> None:
    store = JobStateStore()
    job = store.create_job("x.pdf", page_count=1, execution_mode="auto", routing_mode="balanced")
    dispatcher = InProcessWorkerDispatcher(store)
    await dispatcher._run(
        DispatchRequest(
            job_id=job.job_id,
            page_count=1,
            execution_mode="auto",
            routing_mode="balanced",
        ),
        api_key=None,
    )

    state = store.get_job(job.job_id)
    assert state is not None
    assert state.status == JobStatus.COMPLETED


@pytest.mark.unit
def test_in_process_dispatcher_dispatch_uses_create_task(monkeypatch: pytest.MonkeyPatch) -> None:
    store = JobStateStore()
    dispatcher = InProcessWorkerDispatcher(store)
    called = {"value": False}

    def _fake_create_task(coro: object) -> object:
        called["value"] = True
        if asyncio.iscoroutine(coro):
            coro.close()
        return object()

    monkeypatch.setattr(asyncio, "create_task", _fake_create_task)
    dispatcher.dispatch(
        DispatchRequest(
            job_id="id",
            page_count=1,
            execution_mode="auto",
            routing_mode="balanced",
        ),
        api_key="abc",
    )
    assert called["value"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_broker_publish_dispatch_command_emits_contract_envelopes_per_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = RedisStreamsBroker("redis://unused")
    published: list[tuple[str, dict]] = []

    async def _fake_publish(stream: str, envelope: dict) -> str:
        published.append((stream, envelope))
        return "1-0"

    monkeypatch.setattr(broker, "publish_envelope", _fake_publish)

    await broker.publish_dispatch_command(
        DispatchRequest(
            job_id="job-123",
            page_count=2,
            execution_mode="auto",
            routing_mode="balanced",
        )
    )

    assert len(published) == 2
    page_numbers = [env["page_number"] for _, env in published]
    assert page_numbers == [1, 2]
    for stream, envelope in published:
        assert stream == DISPATCH_STREAM
        assert envelope["stream"] == DISPATCH_STREAM
        assert envelope["event_type"] == "dispatch.command.v1"
        assert envelope["schema_version"] == "v1"
        assert envelope["payload"]["command"] == "process_job"
        dumped = json.dumps(envelope)
        assert "api_key" not in dumped
        assert "top-secret" not in dumped


@pytest.mark.unit
@pytest.mark.asyncio
async def test_state_store_stream_reducer_is_idempotent_and_monotonic() -> None:
    store = JobStateStore()
    job = store.create_job("doc.pdf", page_count=1, execution_mode="auto", routing_mode="balanced")

    started = {
        "event_id": "evt-1",
        "event_type": "progress.event.v1",
        "schema_version": "v1",
        "job_id": job.job_id,
        "page_number": 1,
        "attempt": 1,
        "emitted_at": utc_now().isoformat(),
        "correlation_id": job.job_id,
        "causation_id": None,
        "stream": "mf.progress.v1",
        "payload": {
            "status": "started",
            "progress_percent": 0,
            "message": "started",
        },
    }
    duplicate_started = dict(started)

    completed = {
        "event_id": "evt-2",
        "event_type": "result.event.v1",
        "schema_version": "v1",
        "job_id": job.job_id,
        "page_number": 1,
        "attempt": 1,
        "emitted_at": utc_now().isoformat(),
        "correlation_id": job.job_id,
        "causation_id": "evt-1",
        "stream": "mf.result.v1",
        "payload": {
            "status": "success",
            "output_uri": "job://output/page/1",
            "metrics": {
                "processed_pages": 1,
                "accepted_pages": 1,
                "needs_reprocess_pages": 0,
            },
        },
    }

    regressive_processing = {
        "event_id": "evt-3",
        "event_type": "progress.event.v1",
        "schema_version": "v1",
        "job_id": job.job_id,
        "page_number": 1,
        "attempt": 1,
        "emitted_at": utc_now().isoformat(),
        "correlation_id": job.job_id,
        "causation_id": "evt-2",
        "stream": "mf.progress.v1",
        "payload": {
            "status": "processing_page",
            "progress_percent": 50,
            "message": "late-processing",
        },
    }

    first = await store.apply_stream_event(started)
    second = await store.apply_stream_event(duplicate_started)
    third = await store.apply_stream_event(completed)
    fourth = await store.apply_stream_event(regressive_processing)

    assert first is not None
    assert second is None
    assert third is not None
    assert fourth is not None

    state = store.get_job(job.job_id)
    assert state is not None
    page = state.page_states[0]
    assert page.status == PageProcessingStatus.COMPLETED
    assert state.status == JobStatus.COMPLETED


@pytest.mark.unit
def test_broker_event_idempotency_cache_detects_duplicates() -> None:
    cache = EventIdempotencyCache(capacity=2)
    assert cache.seen("evt-1") is False
    assert cache.seen("evt-1") is True
    assert cache.seen("evt-2") is False
    assert cache.seen("evt-3") is False
    assert cache.seen("evt-1") is False
