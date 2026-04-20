"""Worker service runtime consuming dispatch stream and emitting worker events."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from .broker import (
    DISPATCH_STREAM,
    PROGRESS_STREAM,
    RESULT_STREAM,
    RedisStreamsBroker,
)


async def _publish_page_lifecycle(
    broker: RedisStreamsBroker,
    *,
    job_id: str,
    page_number: int,
    correlation_id: str,
) -> None:
    """Emit started -> processing -> completed for one page."""
    started_event = broker.build_envelope(
        event_type="progress.event.v1",
        job_id=job_id,
        stream=PROGRESS_STREAM,
        page_number=page_number,
        correlation_id=correlation_id,
        payload={
            "status": "started",
            "progress_percent": 0,
            "message": "started",
        },
    )
    await broker.publish_envelope(PROGRESS_STREAM, started_event)

    processing_event = broker.build_envelope(
        event_type="progress.event.v1",
        job_id=job_id,
        stream=PROGRESS_STREAM,
        page_number=page_number,
        correlation_id=correlation_id,
        causation_id=started_event["event_id"],
        payload={
            "status": "processing_page",
            "progress_percent": 50,
            "message": "processing",
        },
    )
    await broker.publish_envelope(PROGRESS_STREAM, processing_event)

    result_event = broker.build_envelope(
        event_type="result.event.v1",
        job_id=job_id,
        stream=RESULT_STREAM,
        page_number=page_number,
        correlation_id=correlation_id,
        causation_id=processing_event["event_id"],
        payload={
            "status": "success",
            "output_uri": f"job://{job_id}/page/{page_number}",
            "metrics": {
                "processed_pages": 1,
                "accepted_pages": 1,
                "needs_reprocess_pages": 0,
            },
        },
    )
    await broker.publish_envelope(RESULT_STREAM, result_event)


async def run_worker_forever() -> None:
    """Run worker loop that consumes dispatch events and emits progress/result events."""
    broker = RedisStreamsBroker.from_env()
    group = "mf.worker.v1"
    consumer = f"worker-{uuid4()}"
    await broker.connect()
    await broker.ensure_group(DISPATCH_STREAM, group)

    try:
        while True:
            batch = await broker.read_group(
                streams=[DISPATCH_STREAM],
                group=group,
                consumer=consumer,
                count=10,
                block_ms=1000,
            )
            for item in batch:
                envelope = item.envelope
                payload = envelope.get("payload") or {}
                job_id = str(envelope.get("job_id", ""))
                correlation_id = str(envelope.get("correlation_id") or job_id)
                _ = payload
                page_number = envelope.get("page_number")
                if not isinstance(page_number, int):
                    await broker.ack(stream=item.stream, group=group, message_id=item.message_id)
                    continue

                await _publish_page_lifecycle(
                    broker,
                    job_id=job_id,
                    page_number=page_number,
                    correlation_id=correlation_id,
                )
                await asyncio.sleep(0)

                await broker.ack(stream=item.stream, group=group, message_id=item.message_id)
    finally:
        await broker.close()


def main() -> None:
    """Entrypoint for worker process."""
    asyncio.run(run_worker_forever())


if __name__ == "__main__":
    main()
