# State: MarkFlow

## Project Reference

- Project: `.planning/PROJECT.md`
- Requirements: `.planning/REQUIREMENTS.md`
- Roadmap: `.planning/ROADMAP.md`
- Decision ledger: `.planning/decisions/DECISION_LOG.md`
- Service policy: `docs/architecture/service-isolation-policy.md`
- Event contracts: `docs/architecture/event-contracts.md`

**Core value:** Documents must never be reported as safely processed unless extraction status, confidence, and policy checks support that conclusion.

## Current Snapshot

| Field | Value |
|-------|-------|
| Date | 2026-06-07 |
| GSD state | GSD Core documentation restructuring complete; full pytest spec gate blocked by missing local pytest |
| Product baseline | v1/v1.1 mature OCR-first extraction system with service-isolated web runtime |
| Previous completed phase | Phase 6: Service runtime hardening and governance |
| Active phase | Phase 7: GSD Core documentation restructure and governance sync |
| Current task | Restructure `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, and `.planning/ROADMAP.md` to GSD Core format without deleting existing content |
| Last known full gate | Phase 6 full suite: pytest, spec traceability, service boundary checks, frontend build, and dependency audits |

## Active Phase

### Phase 7: GSD Core Documentation Restructure

**Status:** complete pending full spec-gate rerun in an environment with pytest installed

**Goal:** Align MarkFlow planning artifacts to the GSD Core reference format while preserving existing validated requirements, roadmap history, constraints, decision context, and audit follow-ups.

**Scope:**

- Restructure `.planning/PROJECT.md` with What This Is, Core Value, Requirements, Context, Constraints, Key Decisions, and Evolution.
- Create/update `.planning/REQUIREMENTS.md` with REQ-IDs and a traceability table.
- Create/update `.planning/STATE.md` in GSD format.
- Create/update `.planning/ROADMAP.md` from existing completed phases, STATE follow-ups, and audit TODOs/tasks.
- Update decision-governance artifacts for the documentation process decision.

**Validation evidence:**

- `python3 scripts/check_service_boundaries.py` passed.
- Lightweight REQ/spec parser check confirmed 37 v1 IDs match 37 feature specs.
- `python3 -m pytest -m spec -q --no-cov` was attempted but blocked locally because pytest is not installed.
- Documentation and decision artifacts were synchronized.

## Working Agreements

- Use GSD planning artifacts as the source of truth for scope and traceability.
- Every v1 requirement in `.planning/REQUIREMENTS.md` must appear in `.planning/specs/features.json`.
- Every requirement in `.planning/specs/features.json` must list at least one existing test file with executable tests.
- Every v1 requirement must have acceptance criteria and test evidence in `.planning/specs/feature_acceptance_matrix.md`.
- Every production module under `markflow/` must be mapped to at least one feature spec.
- Implementation can use mocks/stubs for external LLM/OCR systems where live dependencies would make CI unstable.
- Architectural decisions and changelog rationale must be recorded in `docs/CHANGELOG_DECISOES.md` and `.planning/decisions/DECISION_LOG.md`.
- Service isolation remains mandatory across `services/frontend`, `services/api`, and `services/worker`.
- API remains canonical state authority.
- Coverage gate remains 100 percent in CI.

## Completed GSD Phases

| Phase | Status | Result |
|-------|--------|--------|
| Phase 1: GSD migration and traceability | Complete | Local GSD context and spec traceability baseline created. |
| Phase 2: Coverage expansion | Complete | Critical module coverage expanded and gate raised. |
| Phase 3: Golden functional regression pack | Complete | Deterministic generated PDF regression fixtures added. |
| Phase 4: Strict GSD feature contract | Complete | Acceptance matrix and stricter spec gates added. |
| Phase 5: Coverage hardening to 100 percent | Complete | Global coverage gate raised to 100 percent. |
| Phase 6: Service runtime hardening and governance | Complete | Service boundaries, Redis contracts, CI hardening, and cross-agent governance added. |

## Active Requirements

| REQ-ID | Status | Source |
|--------|--------|--------|
| GSD-06 | Active | GSD Core restructure request |
| GOV-01 | Active | Decision-governance hard constraint |
| OPS-02 | Active | Previous STATE workstation cleanup note |
| QA-04 | Active | Previous fixture follow-up |
| DEPLOY-01 | Active | `.planning/AUDIT.md` publication roadmap |
| DOC-01 | Active | `.planning/AUDIT.md` documentation cleanup note |

## Next Suggested Work

1. Rerun `python3 -m pytest -m spec -q --no-cov` in an environment with pytest installed.
2. Keep the 100 percent coverage and service-boundary gates as non-negotiable CI requirements.
3. Keep the decision ledger updated for every meaningful architectural or operational decision.
4. Investigate ACL constraints on local temp folders (`.pytest-tmp`, `test-tmp`, `manual-tmp`, `.tmp`) because cleanup is currently blocked by filesystem permissions in this workstation profile.
5. Replace deterministic generated fixture PDFs with curated real-world samples if the project can safely store non-sensitive documents.
6. Evaluate Dokploy plus Cloudflare Tunnel publication only if service isolation, secret handling, and deterministic test constraints remain intact.
7. Review potentially stale execution/runtime docs before the next release.

## Continuity Notes

- Start every agent session by reading the load-order files listed in `AGENTS.md`.
- Use `.planning/COPILOT_HANDOFF_PROTOCOL.md` for Copilot/Codex handoffs.
- Reconcile `.planning/copilot-state.md` with this STATE file before resuming cross-agent work.
- STATE wins if checkpoint files are stale.
- Existing workspace status before this documentation task included a deleted `.codex/config.toml` and untracked `.claude/` plus `.planning/AUDIT.md`; these were treated as pre-existing user/workspace changes.

---
*Last updated: 2026-06-07 after GSD Core documentation restructuring.*
