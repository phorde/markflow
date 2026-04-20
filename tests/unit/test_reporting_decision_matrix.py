from __future__ import annotations

import pytest

from markflow.extraction.reporting import derive_document_status

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("summary", "medical_strict", "expected"),
    [
        ({"error_pages": 1}, False, "error"),
        ({"needs_reprocess_pages": 1}, False, "needs_reprocess"),
        ({"llm_review_required_pages": 2}, True, "llm_review_required"),
        ({"pages": 2, "accepted_pages": 2}, False, "accepted"),
        ({"pages": 1, "llm_review_passed_pages": 1}, True, "llm_review_passed"),
    ],
)
def test_derive_document_status_matrix(
    summary: dict[str, int], medical_strict: bool, expected: str
):
    report = {"summary": summary}
    assert derive_document_status(report, medical_strict=medical_strict) == expected
