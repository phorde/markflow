# Phase 5 Context: Coverage Hardening Toward 100 Percent

## Objective

Raise structural coverage toward 100 percent while preserving meaningful,
behavior-oriented tests. The phase treats 100 percent as an end target and uses
progressive gates to avoid replacing quality with metric gaming.

## Starting Point

- Global coverage before this phase: 81 percent.
- Primary gaps: `pipeline.py`, `tui.py`, `llm_client.py`, extraction helper branches,
  benchmark ingestion edge cases.

## Constraints

- No live LLM or live OCR dependency in normal gates.
- External integrations must be covered through deterministic fakes/stubs.
- `pragma: no cover` requires technical justification.
- GSD feature completeness remains governed by the spec traceability gate.

## Final Gate

- Target: global coverage `>=100%`.
- Status: complete.
