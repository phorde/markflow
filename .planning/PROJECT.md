# MarkFlow

## What This Is

MarkFlow is a provider-agnostic, OCR-first PDF extraction system that converts mixed-quality PDFs into structured Markdown, sanitized HTML, and auditable JSON reports. It supports CLI, TUI, API, worker, and frontend workflows while preserving a strict service-isolated architecture for production use.

It is built for document workflows where extraction quality, traceability, confidence reporting, and fail-closed behavior matter more than raw throughput.

## Core Value

Documents must never be reported as safely processed unless extraction status, confidence, and policy checks support that conclusion.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. Full REQ-ID traceability lives in .planning/REQUIREMENTS.md. -->

- [x] CLI and library entry points process single PDFs and directories with bounded execution modes.
- [x] Native text-layer extraction, local OCR fallback, and remote multimodal OCR routing are available.
- [x] EasyOCR, RapidOCR, and Tesseract result formats normalize confidence to `0.0..1.0`.
- [x] Provider-agnostic LLM clients support OpenAI-compatible, Anthropic, Gemini, OpenRouter, and Z.AI flows.
- [x] Model discovery, OCRBench-aware ranking, and task-aware routing are deterministic for equivalent inputs.
- [x] Medical strict mode fails closed for low-confidence, unavailable-review, or reprocess-required states.
- [x] Final reports expose document/page status, confidence, warnings, elapsed time, cache policy, and routing context.
- [x] HTML exports are sanitized before persistence.
- [x] API key handling rejects insecure remote URLs, redacts secrets, and prevents credential persistence in reports.
- [x] Unit, integration, functional, spec, lint, typecheck, frontend build, dependency, and coverage gates are automated.
- [x] Global coverage gate is preserved at 100 percent.
- [x] v1 requirement/spec/test traceability is enforced by pytest.
- [x] API, worker, and frontend service boundaries are enforced by deterministic checks in CI.
- [x] Redis Streams event contracts are versioned as `v1` and schema-validated.
- [x] API-owned reducer is the canonical state authority for worker event observations.
- [x] Copilot/Codex continuity artifacts and decision-governance docs are first-class project artifacts.

### Active

<!-- Current scope. Building toward these. -->

- [ ] Keep GSD Core documentation current across `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, and `.planning/ROADMAP.md`.
- [ ] Maintain decision ledger entries for meaningful architecture, process, deployment, or governance decisions.
- [ ] Preserve the 100 percent coverage gate and v1 traceability gate during all implementation work.
- [ ] Keep service-isolation policy and event-contract docs synchronized with API/worker/frontend behavior.
- [ ] Resolve local temp-folder ACL cleanup constraints for `.pytest-tmp`, `test-tmp`, `manual-tmp`, and `.tmp` when workstation permissions allow.
- [ ] Replace generated fixture PDFs with curated non-sensitive real-world samples if the project can safely store them.
- [ ] Evaluate the audit backlog for Dokploy/Cloudflare Tunnel deployment and public publication needs.
- [ ] Review potentially stale execution-mode and assistant-runtime docs before the next release.

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Running external paid LLM calls in automated CI - tests use stubs/mocks to keep gates deterministic.
- Requiring real OCR binary availability in CI - local OCR engines are covered with mocked engine formats and fixtures.
- Persisting sensitive cache artifacts in strict regulated workflows unless the user explicitly opts in.
- Collapsing API, worker, and frontend into one runtime - service isolation is a hard production constraint.
- Letting frontend or worker mutate canonical state directly - API remains the state authority.
- Exposing API keys through Redis Streams, canonical state, logs, error traces, reports, or dead-letter records.
- Adding non-deterministic network/provider dependencies to default tests.
- Migrating the core OCR/ML stack away from Python solely to match generic portfolio conventions.

## Context

- Runtime: Python 3.10+ package named `markflow`.
- Entrypoints: `app.py` delegates to `markflow.cli:main`; web API runs from `services/api`; worker runs from `services/worker/entrypoint.py`; frontend runs from `services/frontend`.
- Core package: `markflow/` contains CLI, TUI, pipeline orchestration, LLM abstraction, benchmark ingestion, model selection, routing, security, and extraction helpers.
- Services: `services/frontend`, `services/api`, and `services/worker` are independent runtime/build/deploy units.
- Contracts: HTTP/SSE boundary lives under `services/api/contracts/http`; event schemas live under `services/api/contracts/events` and `services/worker/contracts/events`.
- Outputs: `*.canonical.md`, `*.canonical.html`, and `*.canonical.report.json`.
- Test runner: pytest with `unit`, `integration`, `functional`, `network`, `slow`, and `spec` markers.
- GSD runtime: local Codex installation in `.codex/`; project planning and traceability in `.planning/`.
- Cross-agent continuity: `.planning/COPILOT_HANDOFF_PROTOCOL.md`, `.planning/copilot-state.md`, `.planning/CONTEXT_FOR_AGENTS.md`, `.planning/AGENT_ROLES.md`, `.planning/SKILLS_FOR_COPILOT.md`, and `docs/INTEGRATION_COPILOT_CODEX.md`.
- Deployment history: Render Blueprint exists for isolated API, frontend, worker, and Redis-compatible Key Value services; free-tier worker runs as an isolated web service with `/health`.
- Audit context: `.planning/AUDIT.md` classifies MarkFlow as mature and suggests Dokploy/Cloudflare publication follow-ups plus documentation cleanup review.

## Constraints

- **Security**: Never persist sensitive cache content in `medical_strict` unless explicitly allowed.
- **Compatibility**: Preserve CLI compatibility for existing `python app.py` and `markflow` workflows.
- **Determinism**: Default tests must not require live provider credentials, real paid LLM calls, external network calls, or host-installed OCR binaries.
- **Auditability**: Final reports must expose document status, page status, cache policy, confidence, elapsed time, warnings, and routing/review evidence.
- **Service Isolation**: Runtime ownership must stay separated between frontend, API, and worker.
- **Canonical State**: API is the only canonical state authority; worker publishes observations; frontend submits commands and renders API state.
- **Contract Compatibility**: Redis Streams envelopes and HTTP/SSE contracts must remain versioned and schema/test validated.
- **Traceability**: Every v1 requirement must remain mapped to specs, implementation paths, acceptance criteria, and executable tests.
- **Coverage**: CI coverage gate remains at 100 percent.
- **Decision Traceability**: Architectural and operational decisions must be recoverable for future agents.
- **Data Privacy**: Do not commit sensitive or personal sample documents.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. Canonical ledger: .planning/decisions/DECISION_LOG.md. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use local GSD install in `.codex/` | Keeps workflow/runtime versioned and reproducible per repository. | [x] Good |
| Track `.planning/` as source of truth | Maintains scoped planning, state, specs, and phase history as repo artifacts. | [x] Good |
| Enforce spec traceability with pytest | Prevents requirements, tests, implementation paths, and acceptance criteria from drifting. | [x] Good |
| Preserve 100 percent coverage gate | Keeps the mature v1 baseline from regressing silently. | [x] Good |
| Keep external OCR/LLM tests mocked by default | Real services and binaries are environment-dependent, credential-dependent, and non-deterministic. | [x] Good |
| Split runtime into API/worker/frontend services | Isolates ownership, improves deployment boundaries, and hardens production posture. | [x] Good |
| Make API canonical state authority | Prevents frontend/worker state divergence and centralizes reducer semantics. | [x] Good |
| Use Redis Streams with versioned envelopes | Enables at-least-once worker/API event flow with schema compatibility checks. | [x] Good |
| ACK worker events only after reducer commit | Preserves canonical-state correctness during replay, duplicate delivery, and failure recovery. | [x] Good |
| Enforce service boundaries in CI | Converts architecture policy into deterministic regression protection. | [x] Good |
| Sanitize HTML before persistence | Prevents active-content payloads from surviving Markdown/HTML export. | [x] Good |
| Disable sensitive strict-mode cache by default | Keeps regulated workflows fail-closed unless persistence is explicit. | [x] Good |
| Maintain Copilot/Codex handoff artifacts | Preserves rationale continuity across agents and prevents stale context. | [x] Good |
| Record decisions in ledger and rationale changelog | Makes architecture/process changes auditable beyond commit messages. | [x] Good |
| Render free-tier worker runs as web service | Render Free does not support background workers, so the demo preserves isolation through a health-checked web service. | [x] Good |
| Restructure documentation to GSD Core format | Aligns PROJECT/REQUIREMENTS/STATE/ROADMAP with the current GSD reference while preserving existing content. | - Pending validation |

## Evolution

This document evolves at phase transitions, milestone boundaries, and meaningful architecture/process changes.

**After each phase transition**:

1. Requirements invalidated? Move them to Out of Scope with the reason.
2. Requirements validated? Move them to Validated and reference the phase in `.planning/REQUIREMENTS.md`.
3. New requirements emerged? Add them to Active with a future roadmap phase.
4. Decisions to log? Add them to Key Decisions and `.planning/decisions/DECISION_LOG.md`.
5. "What This Is" and "Core Value" still accurate? Update if product direction drifted.
6. Service boundaries or contracts changed? Synchronize `docs/architecture/service-isolation-policy.md`, `docs/architecture/event-contracts.md`, and contract schemas/tests.

**After each milestone**:

1. Review all sections for drift against README, docs, code, and tests.
2. Confirm the Core Value is still the right priority.
3. Audit Out of Scope entries and keep reasons explicit.
4. Update Context with current runtime, deployment, and handoff state.
5. Confirm `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, and `.planning/ROADMAP.md` agree.
6. Run relevant quality gates and record evidence in STATE or the decision ledger.

**Before concluding documentation or governance work**:

1. Run spec traceability and service-boundary checks when feasible.
2. Confirm docs and decision artifacts are synchronized.
3. Commit documentation changes with traceability preserved.

---
*Last updated: 2026-06-07 after GSD Core documentation restructuring.*
