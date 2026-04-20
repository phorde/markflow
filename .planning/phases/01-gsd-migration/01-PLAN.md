# Phase 1 Plan: GSD Migration and Traceability

## Objective

Migrate MarkFlow into the GSD workflow by installing the local Codex runtime, adding planning artifacts, and enforcing 100 percent requirement/spec/test traceability through pytest.

## Tasks

- [x] Install GSD locally with `npx get-shit-done-cc@latest --codex --local`.
- [x] Create `.planning/config.json`.
- [x] Create `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`.
- [x] Create `.planning/codebase/` map documents.
- [x] Create `.planning/specs/features.json`.
- [x] Add `tests/spec/test_gsd_spec_traceability.py`.
- [x] Add `spec` pytest marker.
- [x] Update README with GSD workflow commands.
- [x] Run all quality gates.

## Verification

- GSD runtime files exist under `.codex/`.
- Planning files exist under `.planning/`.
- Every v1 requirement ID in `.planning/REQUIREMENTS.md` exists in `.planning/specs/features.json`.
- Every spec entry lists at least one implementation path and one test path.
- Every listed implementation/test path exists.
- CI includes a spec traceability gate.

## Status

Complete.
