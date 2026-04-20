"""Neutral dispatch contracts owned by the API service runtime."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DispatchRequest:
    """Minimal worker dispatch request payload."""

    job_id: str
    page_count: int
    execution_mode: str
    routing_mode: str
