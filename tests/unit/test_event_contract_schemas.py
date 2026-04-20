"""Contract schema validation tests for event payloads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIRS = (
    REPO_ROOT / "services" / "api" / "contracts" / "events",
    REPO_ROOT / "services" / "worker" / "contracts" / "events",
)


def _load_schema(schema_dir: Path, filename: str) -> dict:
    return json.loads((schema_dir / filename).read_text(encoding="utf-8"))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("schema_dir", "schema_name", "valid_payload", "invalid_payload"),
    [
        (schema_dir, schema_name, valid_payload, invalid_payload)
        for schema_dir in SCHEMA_DIRS
        for schema_name, valid_payload, invalid_payload in [
            (
                "event-envelope.v1.schema.json",
                {
                    "event_id": "evt-100",
                    "event_type": "dispatch.command.v1",
                    "schema_version": "v1",
                    "job_id": "job-1",
                    "page_number": None,
                    "attempt": 1,
                    "emitted_at": "2026-04-19T12:00:00Z",
                    "correlation_id": "corr-1",
                    "causation_id": None,
                },
                {
                    "event_id": "evt-100",
                    "event_type": "dispatch.command.v1",
                    "schema_version": "v2",
                    "job_id": "job-1",
                    "page_number": None,
                    "attempt": 1,
                    "emitted_at": "2026-04-19T12:00:00Z",
                    "correlation_id": "corr-1",
                    "causation_id": None,
                },
            ),
            (
                "dispatch-command.v1.schema.json",
                {
                    "event_id": "evt-101",
                    "event_type": "dispatch.command.v1",
                    "schema_version": "v1",
                    "job_id": "job-2",
                    "page_number": None,
                    "attempt": 1,
                    "emitted_at": "2026-04-19T12:00:00Z",
                    "correlation_id": "corr-2",
                    "causation_id": None,
                    "stream": "mf.dispatch.v1",
                    "payload": {
                        "command": "process_job",
                        "source_document": "s3://bucket/doc.pdf",
                        "requested_by": "frontend-user",
                    },
                },
                {
                    "event_id": "evt-101",
                    "event_type": "dispatch.command.v1",
                    "schema_version": "v1",
                    "job_id": "job-2",
                    "page_number": None,
                    "attempt": 1,
                    "emitted_at": "2026-04-19T12:00:00Z",
                    "correlation_id": "corr-2",
                    "causation_id": None,
                    "stream": "mf.dispatch.v1",
                    "payload": {
                        "command": "process_job",
                        "source_document": "s3://bucket/doc.pdf",
                        "requested_by": "frontend-user",
                        "api_key": "must-not-be-here",
                    },
                },
            ),
            (
                "progress-event.v1.schema.json",
                {
                    "event_id": "evt-102",
                    "event_type": "progress.event.v1",
                    "schema_version": "v1",
                    "job_id": "job-3",
                    "page_number": 1,
                    "attempt": 1,
                    "emitted_at": "2026-04-19T12:00:00Z",
                    "correlation_id": "corr-3",
                    "causation_id": "evt-101",
                    "stream": "mf.progress.v1",
                    "payload": {
                        "status": "processing_page",
                        "progress_percent": 33.0,
                        "message": "Page 1 OCR in progress",
                    },
                },
                {
                    "event_id": "evt-102",
                    "event_type": "progress.event.v1",
                    "schema_version": "v1",
                    "job_id": "job-3",
                    "page_number": 1,
                    "attempt": 1,
                    "emitted_at": "2026-04-19T12:00:00Z",
                    "correlation_id": "corr-3",
                    "causation_id": "evt-101",
                    "stream": "mf.progress.v1",
                    "payload": {
                        "status": "processing_page",
                        "progress_percent": 120.0,
                        "message": "Invalid percent",
                    },
                },
            ),
            (
                "result-event.v1.schema.json",
                {
                    "event_id": "evt-103",
                    "event_type": "result.event.v1",
                    "schema_version": "v1",
                    "job_id": "job-4",
                    "page_number": None,
                    "attempt": 1,
                    "emitted_at": "2026-04-19T12:00:00Z",
                    "correlation_id": "corr-4",
                    "causation_id": "evt-102",
                    "stream": "mf.result.v1",
                    "payload": {
                        "status": "success",
                        "output_uri": "s3://bucket/job-4/output.canonical.md",
                        "metrics": {
                            "processed_pages": 12,
                            "accepted_pages": 10,
                            "needs_reprocess_pages": 2,
                        },
                    },
                },
                {
                    "event_id": "evt-103",
                    "event_type": "result.event.v1",
                    "schema_version": "v1",
                    "job_id": "job-4",
                    "page_number": None,
                    "attempt": 1,
                    "emitted_at": "2026-04-19T12:00:00Z",
                    "correlation_id": "corr-4",
                    "causation_id": "evt-102",
                    "stream": "mf.result.v1",
                    "payload": {
                        "status": "success",
                        "output_uri": "s3://bucket/job-4/output.canonical.md",
                        "metrics": {
                            "processed_pages": 12,
                            "accepted_pages": 10,
                        },
                    },
                },
            ),
        ]
    ],
)
def test_event_contract_schema_accepts_valid_and_rejects_invalid(
    schema_dir: Path,
    schema_name: str,
    valid_payload: dict,
    invalid_payload: dict,
) -> None:
    """Ensure each contract schema accepts valid payload and rejects invalid payload."""
    validator = Draft202012Validator(_load_schema(schema_dir, schema_name))
    validator.validate(valid_payload)

    with pytest.raises(ValidationError):
        validator.validate(invalid_payload)
