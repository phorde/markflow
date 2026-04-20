# State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-04-19)

**Core value:** Documents must never be reported as safely processed unless extraction status, confidence, and policy checks support that conclusion.
**Current focus:** Phase 5 coverage hardening complete at 100 percent.

## Current Phase

- Phase: Phase 5
- Status: complete pending final user review
- Last gate run: full pytest coverage at 100 percent

## Working Agreements

- Use GSD planning artifacts as the source of truth for scope and traceability.
- Every v1 requirement in `.planning/REQUIREMENTS.md` must appear in `.planning/specs/features.json`.
- Every requirement in `.planning/specs/features.json` must list at least one existing test file with executable tests.
- Every v1 requirement must have acceptance criteria and test evidence in `.planning/specs/feature_acceptance_matrix.md`.
- Every production module under `markflow/` must be mapped to at least one feature spec.
- Implementation can use mocks/stubs for external LLM/OCR systems where live dependencies would make CI unstable.

## Completed GSD Phases

- Phase 1: GSD migration and traceability.
- Phase 2: Coverage expansion with critical modules at or above 95 percent.
- Phase 3: Golden functional regression pack.
- Phase 4: Strict GSD feature contract.
- Phase 5: Coverage hardening to 100 percent.

## Active GSD Phase

- Phase 5: Coverage hardening toward 100 percent.
- Completed gate: global coverage `>=100%`.
- Next gate: maintain 100 percent while avoiding untested public behavior and documenting any new exclusion.

## Next Suggested Work

- Maintain the 100 percent gate and review new `pragma: no cover` / `pragma: no branch` usage during code review.
- Replace deterministic generated fixture PDFs with curated real-world samples if the project can safely store non-sensitive documents.
