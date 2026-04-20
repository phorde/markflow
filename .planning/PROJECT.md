# MarkFlow

## What This Is

MarkFlow is a provider-agnostic, OCR-first PDF extraction system that converts mixed-quality PDFs into structured Markdown, sanitized HTML, and auditable JSON reports. It is built for document workflows where extraction quality, traceability, and fail-closed behavior matter more than raw throughput.

## Core Value

Documents must never be reported as safely processed unless extraction status, confidence, and policy checks support that conclusion.

## Requirements

### Validated

- [x] Text-layer extraction and OCR fallback are available through CLI and library entry points.
- [x] Model discovery, benchmark-aware model selection, and OCR-aware routing are implemented.
- [x] Medical strict mode can fail closed when confidence is insufficient.
- [x] HTML exports are sanitized before persistence.
- [x] Unit, integration, functional, lint, typecheck, and coverage gates are automated.
- [x] API, worker, and frontend service boundaries are enforced with deterministic checks in CI.
- [x] Redis Streams event contracts are versioned and schema-validated.

### Active

- [x] GSD local runtime is installed under `.codex/`.
- [x] GSD planning context is tracked under `.planning/`.
- [x] Every documented v1 requirement has an explicit test mapping.
- [x] Spec traceability is enforced by pytest.
- [x] Change history and decision rationale are documented for cross-agent continuity.

### Out of Scope

- Running external paid LLM calls in automated CI - tests use stubs/mocks to keep gates deterministic.
- Real OCR binary availability in CI - local OCR engines are covered with mocked engine formats and fixtures.
- Running Docker orchestration checks locally without Docker installed on the workstation.

## Context

- Runtime: Python 3.10+, PowerShell/Windows-compatible development.
- Entrypoint: `app.py` delegates to `markflow.cli:main`.
- Core package: `markflow/`.
- Services: `services/api`, `services/worker`, `services/frontend`.
- Test runner: pytest with unit, integration, functional, network, slow, and spec markers.
- GSD runtime: local Codex installation in `.codex/`, project planning in `.planning/`.

## Constraints

- **Security**: Never persist sensitive cache content in `medical_strict` unless explicitly allowed.
- **Compatibility**: Preserve CLI compatibility for existing `python app.py` workflows.
- **Determinism**: CI tests must not require live provider credentials or network calls.
- **Auditability**: Final reports must expose document status, page status, cache policy, confidence, and warnings.
- **Service Isolation**: Runtime ownership must stay separated between frontend/API/worker.
- **Decision Traceability**: Architectural and operational decisions must be recoverable for future agents.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use local GSD install in `.codex/` | Keeps workflow/runtime versioned and reproducible per repository. | Complete |
| Track `.planning/` as source-of-truth | Maintains scoped planning and phase history as repo artifacts. | Complete |
| Enforce spec traceability with pytest | Prevents requirements, tests, and implementation from drifting. | Complete |
| Keep external OCR/LLM tests mocked | Real services and binaries are environment-dependent and non-deterministic. | Complete |
| Split runtime into API/worker/frontend services | Isolates ownership, improves deployment boundaries, and hardens production posture. | Complete |
| Version Redis contracts and check service boundaries in CI | Protects cross-service compatibility and import boundaries as code evolves. | Complete |
| Maintain a cross-agent decision ledger skill | Preserves rationale continuity across Codex/Claude/Gemini/Copilot sessions. | Complete |
| Formalize Copilot<->Codex handoff artifacts and CI validation | Ensures deterministic cross-agent continuity and prevents integration drift. | Complete |

---
*Last updated: 2026-04-20 after production hardening and governance updates.*
