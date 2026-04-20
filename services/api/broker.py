"""Redis Streams broker utilities owned by the API service runtime."""

from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from dispatch import DispatchRequest

DISPATCH_STREAM = "mf.dispatch.v1"
PROGRESS_STREAM = "mf.progress.v1"
RESULT_STREAM = "mf.result.v1"

EVENT_FIELD = "event"
SCHEMA_VERSION = "v1"


def redis_client_class() -> Any:
    """Load Redis lazily so tests can import this module without redis installed."""
    try:
        from redis.asyncio import Redis
    except Exception as exc:  # pragma: no cover - allows tests without redis package installed
        raise RuntimeError("redis_dependency_missing") from exc
    return Redis


def utc_now_iso() -> str:
    """Return RFC3339 UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()


class EventIdempotencyCache:
    """Bounded in-memory event id cache used for deduplication."""

    def __init__(self, capacity: int = 10000) -> None:
        self._capacity = capacity
        self._seen: set[str] = set()
        self._order: deque[str] = deque()

    def seen(self, event_id: str) -> bool:
        """Return True if event_id was already seen, else record it and return False."""
        if self.contains(event_id):
            return True
        self.record(event_id)
        return False

    def contains(self, event_id: str) -> bool:
        """Return whether event_id is already recorded."""
        return event_id in self._seen

    def record(self, event_id: str) -> None:
        """Record event_id while enforcing bounded memory usage."""
        self._seen.add(event_id)
        self._order.append(event_id)
        if len(self._order) > self._capacity:
            oldest = self._order.popleft()
            self._seen.discard(oldest)


@dataclass(frozen=True)
class ConsumedEvent:
    """One event consumed from a stream with enough metadata for acking."""

    stream: str
    message_id: str
    envelope: dict[str, Any]


class RedisStreamsBroker:
    """Thin Redis Streams helper with explicit envelope semantics."""

    def __init__(self, redis_url: str, stream_maxlen: int = 10000) -> None:
        self._redis_url = redis_url
        self._stream_maxlen = stream_maxlen
        self._redis: Any | None = None

    @classmethod
    def from_env(cls) -> "RedisStreamsBroker":
        """Create broker from REDIS_URL env with a local default."""
        return cls(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    async def connect(self) -> None:
        """Initialize Redis client lazily."""
        if self._redis is not None:
            return
        self._redis = redis_client_class().from_url(self._redis_url, decode_responses=True)

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._redis is None:
            return
        await self._redis.aclose()
        self._redis = None

    def _redis_client(self) -> Any:
        """Return initialized Redis client after connect lifecycle."""
        if self._redis is None:  # pragma: no cover - defensive after connect()
            raise RuntimeError("redis_client_uninitialized")
        return self._redis

    async def ensure_group(self, stream: str, group: str) -> None:
        """Create consumer group if missing."""
        await self.connect()
        redis = self._redis_client()
        try:
            await redis.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
        except Exception as exc:  # pragma: no cover - branch varies by redis server error text
            if "BUSYGROUP" not in str(exc):
                raise

    def build_envelope(
        self,
        *,
        event_type: str,
        job_id: str,
        stream: str,
        payload: dict[str, Any],
        page_number: int | None,
        attempt: int = 1,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> dict[str, Any]:
        """Build an event envelope aligned with v1 contracts."""
        return {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "page_number": page_number,
            "attempt": attempt,
            "emitted_at": utc_now_iso(),
            "correlation_id": correlation_id or job_id,
            "causation_id": causation_id,
            "stream": stream,
            "payload": payload,
        }

    async def publish_envelope(self, stream: str, envelope: dict[str, Any]) -> str:
        """Publish a pre-built envelope to a stream and return message id."""
        await self.connect()
        redis = self._redis_client()
        payload = json.dumps(envelope, separators=(",", ":"))
        message_id = await redis.xadd(
            name=stream,
            fields={EVENT_FIELD: payload},
            maxlen=self._stream_maxlen,
            approximate=True,
        )
        return str(message_id)

    async def publish_dispatch_command(self, request: DispatchRequest) -> str:
        """Publish per-page dispatch commands. API key must never be included."""
        last_message_id = ""
        for page_number in range(1, request.page_count + 1):
            envelope = self.build_envelope(
                event_type="dispatch.command.v1",
                job_id=request.job_id,
                stream=DISPATCH_STREAM,
                page_number=page_number,
                payload={
                    "command": "process_job",
                    "source_document": request.job_id,
                    "requested_by": "api",
                },
            )
            last_message_id = await self.publish_envelope(DISPATCH_STREAM, envelope)
        return last_message_id

    async def read_group(
        self,
        *,
        streams: list[str],
        group: str,
        consumer: str,
        count: int = 20,
        block_ms: int = 1000,
    ) -> list[ConsumedEvent]:
        """Read events from a consumer group for one or more streams."""
        await self.connect()
        redis = self._redis_client()
        stream_map: dict[Any, Any] = {stream: ">" for stream in streams}
        reply = await redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams=stream_map,
            count=count,
            block=block_ms,
        )
        consumed: list[ConsumedEvent] = []
        for stream_name, messages in reply:
            for message_id, fields in messages:
                raw = fields.get(EVENT_FIELD)
                if not raw:
                    continue
                envelope = json.loads(raw)
                consumed.append(
                    ConsumedEvent(
                        stream=str(stream_name),
                        message_id=str(message_id),
                        envelope=envelope,
                    )
                )
        return consumed

    async def ack(self, *, stream: str, group: str, message_id: str) -> None:
        """Ack a processed message id."""
        await self.connect()
        redis = self._redis_client()
        await redis.xack(stream, group, message_id)


class RedisDispatchPublisher:
    """Dispatch interface adapter used by API create_job route."""

    def __init__(self, broker: RedisStreamsBroker) -> None:
        self._broker = broker

    async def dispatch(self, request: DispatchRequest, api_key: str | None = None) -> None:
        """Publish dispatch commands only after Redis confirms the write."""
        _ = api_key
        await self._broker.publish_dispatch_command(request)
