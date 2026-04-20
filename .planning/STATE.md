# State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-04-20)

**Core value:** Documents must never be reported as safely processed unless extraction status, confidence, and policy checks support that conclusion.
**Current focus:** Phase 6 service runtime hardening and decision-governance artifacts complete.

## Current Phase

- Phase: Phase 6
- Status: complete pending final user review
- Last gate run: pytest full suite, spec traceability, service boundary checks, frontend build, and dependency audits

## Working Agreements

- Use GSD planning artifacts as the source of truth for scope and traceability.
- Every v1 requirement in `.planning/REQUIREMENTS.md` must appear in `.planning/specs/features.json`.
- Every requirement in `.planning/specs/features.json` must list at least one existing test file with executable tests.
- Every v1 requirement must have acceptance criteria and test evidence in `.planning/specs/feature_acceptance_matrix.md`.
- Every production module under `markflow/` must be mapped to at least one feature spec.
- Implementation can use mocks/stubs for external LLM/OCR systems where live dependencies would make CI unstable.
- Architectural decisions and changelog rationale must be recorded in `docs/CHANGELOG_DECISOES.md` and `.planning/decisions/DECISION_LOG.md`.

## Completed GSD Phases

- Phase 1: GSD migration and traceability.
- Phase 2: Coverage expansion with critical modules at or above 95 percent.
- Phase 3: Golden functional regression pack.
- Phase 4: Strict GSD feature contract.
- Phase 5: Coverage hardening to 100 percent.
- Phase 6: Service runtime hardening and governance/documentation updates.

## Active GSD Phase

- Phase 6: Service runtime hardening and governance updates.
- Completed gates: global coverage `>=100%`, v1 spec traceability, service boundary checker, frontend build/TypeScript checks, and dependency vulnerability audits for runtime/dev manifests.

## Next Suggested Work

- Maintain the 100 percent coverage and service-boundary gates as non-negotiable CI requirements.
- Keep the decision ledger updated for every meaningful architectural or operational decision.
- Replace deterministic generated fixture PDFs with curated real-world samples if the project can safely store non-sensitive documents.
