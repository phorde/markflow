# Roadmap: MarkFlow

This roadmap preserves completed GSD phase history and adds current/future work from `.planning/STATE.md`, `.planning/AUDIT.md`, README/docs, and existing TODO/task signals.

## Phase 1: GSD Migration and Traceability

**Status:** Complete
**Goal:** Make the repository operable through local GSD context and enforce requirement/spec/test traceability.

### Scope

- Install GSD for Codex locally under `.codex/`.
- Create `.planning/PROJECT.md`, `.planning/config.json`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`.
- Create `.planning/codebase/` map documents for architecture, structure, stack, integrations, conventions, testing, and concerns.
- Create `.planning/specs/features.json` as the machine-readable feature and test inventory.
- Add pytest coverage for spec traceability.

### Gates

- `python -m compileall -q app.py markflow tests`
- `python -m ruff check .`
- `python -m black --check .`
- `python -m flake8 app.py markflow tests`
- `python -m mypy markflow`
- `pytest -m unit -q --no-cov`
- `pytest -m "integration and not slow" -q --no-cov`
- `pytest -m functional -q --no-cov`
- `pytest -q`
- `python -m coverage report --fail-under=70`

## Phase 2: Coverage Expansion to Critical 95 Percent

**Status:** Complete
**Goal:** Raise coverage for `pipeline.py`, `tui.py`, and extraction submodules with targeted tests around branches and failure states.

### Scope

- Add decision-table tests for `_process_page` text-layer, cache-hit, OCR fallback, strict review, and error paths.
- Add non-interactive TUI tests for cancellation/error paths.
- Add HTML sanitizer fallback tests by monkeypatching unavailable `bleach`.
- Add local OCR branch tests for unsupported engines and Tesseract fallback behavior.

### Result

- Global coverage increased from 74 percent to 81 percent.
- `pipeline.py` increased from 57 percent to 70 percent.
- `tui.py` increased from 63 percent to 82 percent.
- `reporting.py` reached 100 percent.
- Coverage gate raised to 80 percent.

## Phase 3: Golden Fixtures and Real-World Regression Pack

**Status:** Complete
**Goal:** Add stable fixture PDFs and golden outputs for representative document classes.

### Scope

- Text-native PDF fixture.
- Scanned-image fixture with local OCR stub.
- Table-heavy fixture.
- Corrupted/invalid page fixture.
- Malicious HTML/Markdown payload fixture.

### Result

- Added deterministic functional golden regressions for text-native, table, local OCR stub, invalid page, and malicious HTML payload scenarios.
- Golden tests use generated PDFs and deterministic page-processing stubs to avoid live OCR/LLM dependencies.

## Phase 4: Strict GSD Feature Contract

**Status:** Complete
**Goal:** Make "all functionality has specification and tests" enforceable as an automated GSD contract.

### Scope

- Add `.planning/specs/feature_acceptance_matrix.md` with acceptance criteria and test evidence for every v1 requirement.
- Extend spec tests to validate that every v1 requirement has an acceptance section.
- Extend spec tests to validate that every referenced test file contains executable tests.
- Extend spec tests to validate that every production module under `markflow/` is mapped to at least one feature spec.
- Map `markflow/extraction/types.py` into the feature inventory after the stricter gate identified it as uncovered.

### Result

- The spec suite verifies requirement coverage, acceptance criteria, test evidence, GSD artifacts, CI wiring, and production-module mapping.
- `pytest -m spec -q --no-cov` passes with 7 spec checks.

## Phase 5: Coverage Hardening Toward 100 Percent

**Status:** Complete
**Goal:** Raise structural test coverage from 81 percent toward 100 percent without adding brittle tests or hiding meaningful production code.

### Strategy

- Add tests for real branches first: pure helpers, deterministic failure paths, mocked external services, and non-interactive TUI flows.
- Use `pragma: no cover` only for technically justified runtime-only paths that cannot be exercised deterministically without reducing test quality.
- Increase the enforced gate progressively: `80 -> 90 -> 95 -> 100`.
- Keep GSD functional traceability separate from line/branch coverage so test design remains behavior-oriented.

### Result

- Added small-module, pipeline, LLM client, TUI, and runtime-adapter branch tests.
- Added explicit coverage exclusions only for defensive or runtime-only paths.
- Global coverage increased from 81 percent to 100 percent.
- Coverage gate raised to 100 percent.

## Phase 6: Service Runtime Hardening and Governance

**Status:** Complete
**Goal:** Make the repository production-ready for multi-service operation while preserving strict GSD traceability and cross-agent continuity.

### Scope

- Establish and validate service runtime boundaries (`frontend`, `api`, `worker`) with deterministic CI checks.
- Version Redis event contracts and assert schema validity in automated tests.
- Harden API reducer semantics for idempotent ACK flow and monotonic state evolution.
- Upgrade and pin dependencies to resolve known security and compatibility issues.
- Add CI jobs for service-boundary validation, service-runtime checks, and frontend build verification.
- Add governance artifacts: project changelog, decision changelog/rationale, decision ledger, and dedicated decision-ledger skill.

### Result

- API/worker/frontend structure is enforced by policy and automated checks.
- Event envelopes/contracts are documented and validated as versioned artifacts.
- CI validates service boundaries, runtime build checks, and full quality gates.
- Security and packaging hardening completed.
- Governance package added: `CHANGELOG.md`, `docs/CHANGELOG_DECISOES.md`, `.planning/decisions/DECISION_LOG.md`, and `.codex/skills/gsd-decision-ledger/`.

## Phase 7: GSD Core Documentation Restructure

**Status:** Active
**Goal:** Align project documentation to GSD Core format while preserving all existing content, validated requirements, decisions, constraints, and roadmap history.

### Scope

- Restructure `.planning/PROJECT.md` into GSD Core sections:
  - What This Is
  - Core Value
  - Requirements: Validated, Active, Out of Scope
  - Context
  - Constraints
  - Key Decisions
  - Evolution protocol
- Create/update `.planning/REQUIREMENTS.md` with explicit REQ-IDs, active requirements, out-of-scope boundaries, and a traceability table.
- Create/update `.planning/STATE.md` in GSD format with active phase, current task, gates, and continuity notes.
- Create/update `.planning/ROADMAP.md` from existing completed phases, STATE follow-ups, and audit TODOs/tasks.
- Update decision artifacts for the process decision.

### Exit Criteria

- Planning docs preserve previous validated content and are aligned with the reference GSD Core format.
- `python -m pytest -m spec -q --no-cov` passes.
- `python scripts/check_service_boundaries.py` passes.
- Decision ledger and rationale docs are synchronized when process rationale changes.
- Commit created with message `chore: restructure to GSD Core format`.

## Phase 8: Workstation and Fixture Hygiene

**Status:** Proposed
**Goal:** Resolve known local environment cleanup friction and improve regression realism without compromising privacy or deterministic CI.

### Scope

- Investigate ACL constraints blocking cleanup of `.pytest-tmp`, `test-tmp`, `manual-tmp`, and `.tmp`.
- Document the workstation-specific fix if the problem is environmental rather than code-owned.
- Define criteria for safe curated real-world PDF fixtures.
- Add curated fixtures only when they are non-sensitive, license-safe, and deterministic.

### Exit Criteria

- Temp-folder cleanup constraints are either fixed or documented with exact owner/environment cause.
- Fixture policy is documented before adding any real-world samples.
- Default tests remain deterministic and do not require live OCR binaries or network providers.

## Phase 9: Publication and Deployment Review

**Status:** Proposed
**Goal:** Evaluate publication follow-ups from `.planning/AUDIT.md` while preserving service isolation and security posture.

### Candidate Scope

- Review Dokploy deployment feasibility using existing service Dockerfiles/compose artifacts.
- Evaluate Cloudflare Tunnel routing for `markflow.phorde.com.br` or related subdomains.
- Decide whether public publication should expose the existing frontend/API or a lightweight documentation/landing surface.
- Reconcile Render Blueprint deployment with any Dokploy/Cloudflare deployment model.
- Ensure API, worker, frontend, and Redis boundaries remain explicit.

### Exit Criteria

- Deployment target and topology are documented.
- Secrets, CORS, worker health, Redis Streams, and service ownership constraints are reviewed.
- Any deployment change has tests/checks or documented manual verification.
- Decision ledger entry records the chosen deployment path.

## Phase 10: Documentation Freshness Review

**Status:** Proposed
**Goal:** Review possibly stale or overlapping documentation before the next release.

### Scope

- Check `EXECUTION_MODES.md` against README and CLI behavior.
- Review `.codex/`, `.claude/`, Copilot, and GSD docs for overlap, runtime drift, and portability.
- Reconcile `.planning/codebase/*` maps with current service architecture and coverage reality.
- Update README only if user-facing behavior, setup, or deployment guidance changed.

### Exit Criteria

- Documentation drift is either fixed or tracked as explicit follow-up.
- No service-boundary or traceability assumptions conflict across docs.
- Decision/changelog artifacts are updated if process guidance changes.

---
*Last updated: 2026-06-07 after GSD Core documentation restructuring.*
