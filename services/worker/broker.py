"""Redis Streams broker utilities owned by the worker service runtime."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

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

    async def ensure_group(self, stream: str, group: str) -> None:
        """Create consumer group if missing."""
        await self.connect()
        assert self._redis is not None
        try:
            await self._redis.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
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
        assert self._redis is not None
        payload = json.dumps(envelope, separators=(",", ":"))
        message_id = await self._redis.xadd(
            name=stream,
            fields={EVENT_FIELD: payload},
            maxlen=self._stream_maxlen,
            approximate=True,
        )
        return str(message_id)

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
        assert self._redis is not None
        stream_map: dict[Any, Any] = {stream: ">" for stream in streams}
        reply = await self._redis.xreadgroup(
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
        assert self._redis is not None
        await self._redis.xack(stream, group, message_id)
