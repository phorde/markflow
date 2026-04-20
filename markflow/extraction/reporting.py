"""Document-level reporting and status derivation."""

from __future__ import annotations

from typing import Any, Dict


def derive_document_status(report: Dict[str, Any], medical_strict: bool) -> str:
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    pages = report.get("pages", []) if isinstance(report, dict) else []
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(pages, list):
        pages = []

    error_pages = int(summary.get("error_pages", 0) or 0)
    needs_reprocess_pages = int(summary.get("needs_reprocess_pages", 0) or 0)
    llm_review_required_pages = int(summary.get("llm_review_required_pages", 0) or 0)
    llm_review_passed_pages = int(summary.get("llm_review_passed_pages", 0) or 0)
    accepted_pages = int(summary.get("accepted_pages", 0) or 0)
    total_pages = int(summary.get("pages", 0) or 0)

    if total_pages <= 0 and pages:
        total_pages = len(pages)
    if accepted_pages <= 0 and pages:
        accepted_pages = sum(
            1
            for page in pages
            if isinstance(page, dict) and str(page.get("status", "")).strip() == "accepted"
        )
    if llm_review_passed_pages <= 0 and pages:
        llm_review_passed_pages = sum(
            1
            for page in pages
            if isinstance(page, dict) and str(page.get("status", "")).strip() == "llm_review_passed"
        )

    if error_pages > 0:
        return "error"
    if needs_reprocess_pages > 0:
        return "needs_reprocess"
    if llm_review_required_pages > 0:
        return "llm_review_required"

    if total_pages > 0 and accepted_pages + llm_review_passed_pages >= total_pages:
        if llm_review_passed_pages > 0 and accepted_pages == 0:
            return "llm_review_passed"
        return "accepted"

    if medical_strict and llm_review_passed_pages > 0:
        return "llm_review_passed"
    return "accepted"


def document_success(status: str) -> bool:
    return status in {"accepted", "llm_review_passed"}


def add_summary_observability(
    report: Dict[str, Any], min_acceptable_confidence: float
) -> Dict[str, Any]:
    pages = report.get("pages", []) if isinstance(report, dict) else []
    if not isinstance(pages, list):
        return report

    elapsed_values = [
        float(page.get("elapsed_seconds", 0.0))
        for page in pages
        if isinstance(page, dict) and isinstance(page.get("elapsed_seconds", 0.0), (int, float))
    ]
    low_confidence_pages = [
        int(page.get("page", 0))
        for page in pages
        if isinstance(page, dict)
        and isinstance(page.get("confidence", 0.0), (int, float))
        and float(page.get("confidence", 0.0)) < min_acceptable_confidence
    ]

    fallback_events = 0
    for page in pages:
        if not isinstance(page, dict):
            continue
        warnings = page.get("warnings", [])
        if not isinstance(warnings, list):
            continue
        fallback_events += sum(
            1
            for warning in warnings
            if isinstance(warning, str)
            and (
                warning.startswith("remote_ocr_failed:")
                or warning.startswith("local_ocr_failed:")
                or warning.startswith("strict_recovery_failed:")
                or warning == "ocr_fallback_used"
            )
        )

    summary = report.setdefault("summary", {})
    if not isinstance(summary, dict):
        return report

    summary["mean_page_elapsed_seconds"] = (
        round(sum(elapsed_values) / len(elapsed_values), 3) if elapsed_values else 0.0
    )
    summary["max_page_elapsed_seconds"] = max(elapsed_values) if elapsed_values else 0.0
    summary["low_confidence_pages"] = low_confidence_pages
    summary["fallback_event_count"] = fallback_events
    return report
