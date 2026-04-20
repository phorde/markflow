from __future__ import annotations

from pathlib import Path
import time

import pytest

from markflow.extraction.cache import (
    is_cache_entry_valid,
    page_cache_path,
    render_profile_payload,
    rendered_cache_path,
)
from markflow.extraction.orchestrator import (
    iter_chunk_bounds,
    resolve_effective_cache_enabled,
)
from markflow.extraction.reporting import (
    add_summary_observability,
    derive_document_status,
    document_success,
)

pytestmark = pytest.mark.unit


def test_cache_paths_and_render_payload(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".cache"
    payload = render_profile_payload("doc", 1.5, 1700, True, True, True, False, 120)
    assert payload == "v1:doc:1.500:1700:1:1:1:0:120"
    page_path = page_cache_path(cache_dir, "ocr", 2, "abc123")
    render_path = rendered_cache_path(cache_dir, 2, "def456")
    assert str(page_path).endswith("0003.ocr.abc123.txt")
    assert str(render_path).endswith("0003.render.def456.b64")


def test_reporting_status_and_success() -> None:
    assert derive_document_status({"summary": {"error_pages": 1}}, medical_strict=False) == "error"
    assert (
        derive_document_status({"summary": {"needs_reprocess_pages": 1}}, medical_strict=True)
        == "needs_reprocess"
    )
    assert (
        derive_document_status({"summary": {"llm_review_required_pages": 1}}, medical_strict=True)
        == "llm_review_required"
    )
    assert derive_document_status({"summary": {}}, medical_strict=False) == "accepted"
    assert document_success("accepted")
    assert document_success("llm_review_passed")
    assert not document_success("error")


def test_reporting_status_llm_review_passed_and_page_fallback() -> None:
    report = {
        "pages": [
            {"status": "llm_review_passed"},
            {"status": "llm_review_passed"},
        ],
        "summary": {"pages": 2},
    }
    assert derive_document_status(report, medical_strict=True) == "llm_review_passed"


def test_reporting_status_handles_malformed_summary_and_pages() -> None:
    malformed = {"summary": "bad", "pages": "bad"}
    assert derive_document_status(malformed, medical_strict=False) == "accepted"

    mixed_pages = {
        "pages": [
            {"status": "accepted"},
            {"status": "llm_review_passed"},
            object(),
        ],
        "summary": {},
    }
    assert derive_document_status(mixed_pages, medical_strict=True) == "llm_review_passed"

    all_counted = {
        "pages": [
            {"status": "accepted"},
            {"status": "llm_review_passed"},
        ],
        "summary": {},
    }
    assert derive_document_status(all_counted, medical_strict=True) == "accepted"

    strict_partial = {
        "summary": {"pages": 3, "llm_review_passed_pages": 1},
        "pages": [],
    }
    assert derive_document_status(strict_partial, medical_strict=True) == "llm_review_passed"


def test_reporting_observability_metrics() -> None:
    report = {
        "pages": [
            {
                "page": 1,
                "confidence": 0.5,
                "elapsed_seconds": 1.2,
                "warnings": ["ocr_fallback_used"],
            },
            {
                "page": 2,
                "confidence": 0.95,
                "elapsed_seconds": 2.8,
                "warnings": ["remote_ocr_failed:timeout"],
            },
        ],
        "summary": {},
    }
    updated = add_summary_observability(report, 0.88)
    summary = updated["summary"]
    assert summary["mean_page_elapsed_seconds"] == 2.0
    assert summary["max_page_elapsed_seconds"] == 2.8
    assert summary["low_confidence_pages"] == [1]
    assert summary["fallback_event_count"] == 2


def test_reporting_observability_handles_malformed_inputs() -> None:
    report = {"pages": "not-a-list", "summary": {}}
    assert add_summary_observability(report, 0.88) is report

    report = {
        "pages": [
            object(),
            {"page": 1, "confidence": "bad", "elapsed_seconds": "bad", "warnings": "bad"},
            {"page": 2, "confidence": 0.1, "elapsed_seconds": 0.0, "warnings": [123]},
        ],
        "summary": "bad",
    }
    updated = add_summary_observability(report, 0.88)
    assert updated["summary"] == "bad"


def test_cache_entry_valid_with_ttl(tmp_path: Path) -> None:
    cache_file = tmp_path / "cache.txt"
    cache_file.write_text("ok", encoding="utf-8")
    assert is_cache_entry_valid(cache_file, ttl_seconds=0)
    assert is_cache_entry_valid(cache_file, ttl_seconds=5, now=time.time())
    assert not is_cache_entry_valid(cache_file, ttl_seconds=1, now=time.time() + 5)


def test_orchestrator_chunk_bounds_and_cache_policy() -> None:
    bounds = list(iter_chunk_bounds(total=10, chunk_size=4))
    assert bounds == [(0, 4), (4, 8), (8, 10)]
    assert not resolve_effective_cache_enabled(
        cache_enabled=False,
        medical_strict=False,
        allow_sensitive_cache_persistence=True,
    )
    assert not resolve_effective_cache_enabled(
        cache_enabled=True,
        medical_strict=True,
        allow_sensitive_cache_persistence=False,
    )
    assert resolve_effective_cache_enabled(
        cache_enabled=True,
        medical_strict=False,
        allow_sensitive_cache_persistence=False,
    )
