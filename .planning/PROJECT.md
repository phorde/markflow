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

### Active

- [x] GSD local runtime is installed under `.codex/`.
- [x] GSD planning context is tracked under `.planning/`.
- [x] Every documented v1 requirement has an explicit test mapping.
- [x] Spec traceability is enforced by pytest.

### Out of Scope

- Running external paid LLM calls in automated CI - tests use stubs/mocks to keep gates deterministic.
- Real OCR binary availability in CI - local OCR engines are covered with mocked engine formats and fixtures.
- Guaranteeing 95 percent global coverage in this migration step - current hard gate remains 70 percent while critical contracts are mapped and tested.

## Context

- Runtime: Python 3.10+, PowerShell/Windows-compatible development.
- Entrypoint: `app.py` delegates to `markflow.cli:main`.
- Core package: `markflow/`.
- Test runner: pytest with unit, integration, functional, network, slow, and spec markers.
- GSD runtime: local Codex installation in `.codex/`, project planning in `.planning/`.

## Constraints

- **Security**: Never persist sensitive cache content in `medical_strict` unless explicitly allowed.
- **Compatibility**: Preserve CLI compatibility for existing `python app.py` workflows.
- **Determinism**: CI tests must not require live provider credentials or network calls.
- **Auditability**: Final reports must expose document status, page status, cache policy, confidence, and warnings.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use local GSD install in `.codex/` | Keeps GSD workflow versioned with this repo and available to Codex. | Pending |
| Track `.planning/` | The user requested full GSD migration, so specs and state should be repo artifacts. | Pending |
| Enforce spec traceability with pytest | Prevents requirements from drifting away from tests. | Pending |
| Keep external OCR/LLM tests mocked | Real services and binaries are environment-dependent. | Good |

---
*Last updated: 2026-04-19 after GSD migration.*
