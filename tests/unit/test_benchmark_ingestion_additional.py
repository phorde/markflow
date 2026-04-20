from __future__ import annotations

import urllib.error

import pytest

from markflow import benchmark_ingestion as ingestion

pytestmark = pytest.mark.unit


def test_collect_benchmark_signals_handles_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ingestion,
        "_fetch",
        lambda url, timeout_seconds: (_ for _ in ()).throw(urllib.error.URLError("down")),
    )
    signals, warnings = ingestion.collect_ocr_benchmark_signals(timeout_seconds=1)
    assert signals == []
    assert any("benchmark_unreachable" in item for item in warnings)
    assert any("benchmark_signals_missing" in item for item in warnings)


def test_collect_benchmark_signals_handles_parse_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingestion, "_fetch", lambda url, timeout_seconds: "<html>broken</html>")
    monkeypatch.setattr(
        ingestion,
        "_parse_ocrbench_v2",
        lambda content: (_ for _ in ()).throw(RuntimeError("parse fail")),
    )
    signals, warnings = ingestion.collect_ocr_benchmark_signals(timeout_seconds=1)
    assert signals == []
    assert any("benchmark_parse_failed" in item for item in warnings)
