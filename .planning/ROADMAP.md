# Roadmap

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

### Exit Criteria

- Critical modules (`security`, `reporting`, `cache`, `routing`, `provider_presets`) remain at or above 95 percent.
- `pipeline.py` and `tui.py` coverage meaningfully increases without relying on live services.

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

### Exit Criteria

- Golden markdown/report comparisons are deterministic.
- Functional tests cover the core user workflows listed in `.planning/specs/features.json`.

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

- The spec suite now verifies requirement coverage, acceptance criteria, test evidence, GSD artifacts, CI wiring, and production-module mapping.
- `pytest -m spec -q --no-cov` passes with 7 spec checks.

## Phase 5: Coverage Hardening Toward 100 Percent

**Status:** Complete
**Goal:** Raise structural test coverage from 81 percent toward 100 percent without adding brittle tests or hiding meaningful production code.

### Strategy

- Add tests for real branches first: pure helpers, deterministic failure paths, mocked external services, and non-interactive TUI flows.
- Use `pragma: no cover` only for technically justified runtime-only paths that cannot be exercised deterministically without reducing test quality.
- Increase the enforced gate progressively: `80 -> 90 -> 95 -> 100`.
- Keep GSD functional traceability separate from line/branch coverage so test design remains behavior-oriented.

### Completed Scope

- Added small-module branch tests for benchmark ingestion, extraction helpers, rendering fallback, review policy, local OCR normalization, and model selection.
- Added pipeline tests for discovery/route caching, remote OCR errors, strict fail-closed review, local OCR fallback/cache paths, and page-level errors.
- Added LLM client tests for URL validation, endpoint normalization, model payload filtering, Anthropic request normalization, redaction, and sync discovery.
- Added TUI tests for prompt fallbacks, disabled LLM setup, Z.AI selection, discovery failures, no-recommendation flows, and rejected recommendations.
- Added runtime-adapter tests for dotenv fallback parsing, RAM autotune, fake PyMuPDF rendering, fake OCR reader factories, Tesseract command handling, `process_document`, and `run_pipeline`.
- Added explicit `pragma: no cover` / `pragma: no branch` only for defensive or runtime-only paths whose behavior is covered by contract/integration tests but whose alternate branch depends on environment state, native binaries, platform-specific APIs, or combinatorial recovery paths.

### Current Result

- Global coverage increased from 81 percent to 100 percent.
- `pipeline.py` measured coverage reached 100 percent after runtime-only exclusions and additional adapter tests.
- `llm_client.py`, `tui.py`, benchmark ingestion, extraction modules, routing, security, provider presets, and CLI reached 100 percent measured coverage.
- Coverage gate raised to 100 percent.

### Exclusion Policy

- Exclusions are allowed only for defensive or runtime-only branches.
- Exclusions must not replace tests for public behavior.
- Contract tests must still cover the behavior around excluded adapters.
- CI enforces `python -m coverage report --fail-under=100`.

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

### Exit Criteria

- Boundary checker passes locally and in CI.
- Service contract schema tests and web foundation tests pass.
- Dependency audits (`pip_audit`, `npm audit`) report no known vulnerabilities for pinned manifests.
- GSD specs, acceptance matrix, and requirements remain in sync and verified by `pytest -m spec`.
- Decision context is documented for cross-agent handoff (Codex, Claude, Gemini, Copilot).

### Result

- API/worker/frontend structure is enforced by policy and automated checks.
- Event envelopes/contracts are documented and validated as versioned artifacts.
- CI pipeline now validates service boundaries, runtime build checks, and full quality gates.
- Security and packaging hardening completed (including dependency pinning and editable-install package discovery fixes).
- Governance package added: `CHANGELOG.md`, `docs/CHANGELOG_DECISOES.md`, `.planning/decisions/DECISION_LOG.md`, and `.codex/skills/gsd-decision-ledger/`.
