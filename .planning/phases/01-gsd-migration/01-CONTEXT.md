# Phase 1: GSD Migration and Traceability - Context

**Gathered:** 2026-04-19
**Status:** Ready for execution
**Source:** User request to migrate the full project to GSD and enforce specs/tests for all functionality.

<domain>
## Phase Boundary

This phase integrates GSD into the existing MarkFlow repository and adds enforceable requirement-to-test traceability. It does not require rewriting the application runtime around a GSD SDK; GSD is a planning and context-engineering framework for agent workflows.
</domain>

<decisions>
## Implementation Decisions

### GSD Runtime
- Install GSD locally for Codex under `.codex/`.
- Track GSD-generated runtime files because the request is a project migration, not a developer-only local preference.

### Planning
- Store project state under `.planning/`.
- Use `.planning/specs/features.json` as the machine-readable source for traceability checks.

### Testing
- Add pytest tests that parse `.planning/REQUIREMENTS.md` and `.planning/specs/features.json`.
- Fail the suite if a requirement is missing from the spec inventory or references non-existent test files.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/PROJECT.md` - project context and constraints.
- `.planning/REQUIREMENTS.md` - checkable v1 requirements.
- `.planning/ROADMAP.md` - phased execution plan.
- `.planning/specs/features.json` - machine-readable spec/test map.
- `tests/spec/test_gsd_spec_traceability.py` - automated traceability gate.
</canonical_refs>

<deferred>
## Deferred Ideas

- Raising global coverage to 95 percent is tracked in Phase 2 because it requires broad branch-specific tests across the large pipeline and TUI surfaces.
</deferred>
