# Testing

**Mapped:** 2026-04-19

## Test Runner

- Official runner: `pytest`.
- Markers: `unit`, `integration`, `functional`, `network`, `slow`, `spec`.

## Current Suites

- Unit tests cover confidence scoring, sanitization, routing, model selection, benchmark ingestion, LLM client behavior, CLI, TUI helpers, strict policy, and extraction helpers.
- Integration tests cover pipeline/report behavior, strict cache policy, process output writing, and CLI failure counting.
- Functional tests cover end-to-end PDF output generation with deterministic page processing.
- Spec tests cover GSD requirement/spec/test traceability.

## Gates

- Fast unit gate: `pytest -m unit -q --no-cov`
- Integration gate: `pytest -m "integration and not slow" -q --no-cov`
- Functional gate: `pytest -m functional -q --no-cov`
- Full gate: `pytest -q`
- Coverage gate: `python -m coverage report --fail-under=100`

## Known Gaps

- `pipeline.py` and `tui.py` still have significant branch coverage gaps.
- Real OCR binaries and paid LLM providers are intentionally mocked in normal gates.
- Golden PDF fixtures are planned but not yet expanded beyond generated sample PDFs.
