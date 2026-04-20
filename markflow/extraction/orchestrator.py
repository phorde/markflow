"""Orchestration-level pure helpers (chunking, cache policy)."""

from __future__ import annotations

from typing import Iterator, Tuple


def iter_chunk_bounds(total: int, chunk_size: int) -> Iterator[Tuple[int, int]]:
    """Yield [start, stop) bounds for bounded parallel execution batches."""
    safe_total = max(0, int(total))
    safe_chunk = max(1, int(chunk_size))
    for start in range(0, safe_total, safe_chunk):
        yield start, min(safe_total, start + safe_chunk)


def resolve_effective_cache_enabled(
    *,
    cache_enabled: bool,
    medical_strict: bool,
    allow_sensitive_cache_persistence: bool,
) -> bool:
    """Apply fail-closed policy for sensitive persistent cache usage."""
    if not cache_enabled:
        return False
    if medical_strict and not allow_sensitive_cache_persistence:
        return False
    return True
