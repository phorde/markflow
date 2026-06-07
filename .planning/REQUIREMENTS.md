# Requirements: MarkFlow

**Defined:** 2026-04-19
**Core Value:** Documents must never be reported as safely processed unless extraction status, confidence, and policy checks support that conclusion.
**Source of Truth:** This file owns human-readable REQ-IDs. Machine-readable traceability lives in `.planning/specs/features.json`; acceptance evidence lives in `.planning/specs/feature_acceptance_matrix.md`.

## Requirement Status Model

| Status | Meaning |
|--------|---------|
| Validated | Implemented, tested, and useful in the current v1/v1.1 baseline. |
| Active | Accepted project direction that still needs work, validation, or periodic maintenance. |
| Out of Scope | Explicitly excluded to preserve constraints, determinism, security, or product focus. |

## v1 Requirements

The following requirements are **Validated** in the current baseline.

### CLI and Configuration

| REQ-ID | Requirement | Phase | Evidence |
|--------|-------------|-------|----------|
| **CLI-01** | User can process one PDF file or a directory of PDF files from the CLI. | Phase 1 | `markflow/cli.py`; `.planning/specs/features.json`; pytest spec gate |
| **CLI-02** | User can select execution modes (`auto`, `fast`, `quality`, `local`, `remote`) with deterministic config effects. | Phase 1 | `markflow/cli.py`; `EXECUTION_MODES.md`; pytest spec gate |
| **CLI-03** | CLI inputs are normalized into bounded `PipelineConfig` values. | Phase 1 | `markflow/cli.py`; `markflow/pipeline.py`; pytest spec gate |
| **CLI-04** | CLI exit codes distinguish discovery errors, all-success runs, and document-level failures. | Phase 1 | `markflow/cli.py`; pytest spec gate |

### Pipeline and Extraction

| REQ-ID | Requirement | Phase | Evidence |
|--------|-------------|-------|----------|
| **PIPE-01** | Native PDF text-layer content is detected, normalized, scored, and emitted as Markdown. | Phase 1 | `markflow/pipeline.py`; `markflow/extraction/page_analysis.py`; functional golden tests |
| **PIPE-02** | Local OCR supports EasyOCR, RapidOCR, and Tesseract result formats with confidence normalized to `0.0..1.0`. | Phase 1 | `markflow/extraction/local_ocr.py`; unit tests |
| **PIPE-03** | Remote multimodal OCR routes through provider-agnostic model selection and fallback models. | Phase 1 | `markflow/llm_client.py`; `markflow/routing.py`; unit/integration tests |
| **PIPE-04** | Visual QA and NLP cleanup run only when policy thresholds and warning rules require them. | Phase 1 | `markflow/extraction/review.py`; pipeline tests |
| **PIPE-05** | `medical_strict` mode fails closed for low-confidence pages, unavailable LLM review, or reprocess-required states. | Phase 1 | `markflow/pipeline.py`; strict policy tests |
| **PIPE-06** | Document reports expose deterministic final status, page status, warnings, confidence, elapsed time, and cache policy. | Phase 1 | `markflow/extraction/reporting.py`; integration/functional tests |
| **PIPE-07** | HTML output is sanitized against script tags, event attributes, dangerous URLs, and unsafe embedded content. | Phase 1 | `markflow/extraction/rendering.py`; security tests |
| **PIPE-08** | Cache entries are versioned, optionally TTL-bound, and disabled by default for sensitive strict mode. | Phase 1 | `markflow/extraction/cache.py`; integration tests |
| **PIPE-09** | CPU-bound rendering and local OCR work do not block the async event loop. | Phase 1 | `markflow/pipeline.py`; adapter tests |

### LLM, Routing, and Selection

| REQ-ID | Requirement | Phase | Evidence |
|--------|-------------|-------|----------|
| **LLM-01** | OpenAI-compatible clients reject insecure remote base URLs while allowing localhost development URLs. | Phase 1 | `markflow/llm_client.py`; URL validation tests |
| **LLM-02** | Provider auth headers, endpoint candidates, redirects, and response parsing are normalized. | Phase 1 | `markflow/llm_client.py`; provider tests |
| **LLM-03** | Model discovery normalizes model IDs, chat/vision capabilities, context windows, and pricing metadata. | Phase 1 | `markflow/llm_client.py`; discovery tests |
| **LLM-04** | OpenAI-compatible and Anthropic message APIs normalize text responses into a shared result type. | Phase 1 | `markflow/llm_client.py`; multimodal/client tests |
| **LLM-05** | API keys, bearer tokens, and long token-like values are redacted from errors and reports. | Phase 1 | `markflow/security.py`; property/security tests |
| **SEL-01** | OCR benchmark ingestion accepts valid, partial, and invalid upstream benchmark payloads safely. | Phase 1 | `markflow/benchmark_ingestion.py`; ingestion tests |
| **SEL-02** | OCR-aware model ranking and recommendation are deterministic for equivalent inputs. | Phase 1 | `markflow/model_selection.py`; model-selection tests |
| **SEL-03** | Task-aware routing selects model candidates based on OCR task kind, complexity, benchmark signal, and vision needs. | Phase 1 | `markflow/routing.py`; routing tests |

### TUI and User Workflow

| REQ-ID | Requirement | Phase | Evidence |
|--------|-------------|-------|----------|
| **TUI-01** | Interactive setup applies provider presets, model discovery, and routing recommendations to CLI args. | Phase 1 | `markflow/tui.py`; non-interactive TUI tests |
| **TUI-02** | TUI helper behavior is testable without requiring an interactive terminal. | Phase 1 | `markflow/tui.py`; TUI unit tests |

### Output and Security

| REQ-ID | Requirement | Phase | Evidence |
|--------|-------------|-------|----------|
| **SEC-01** | Sanitized HTML preserves legitimate Markdown tables and headings while removing active content. | Phase 1 | `markflow/extraction/rendering.py`; sanitizer tests |
| **SEC-02** | Strict regulated workflows never persist sensitive cache artifacts unless explicitly opted in. | Phase 1 | `markflow/extraction/cache.py`; strict cache tests |
| **SEC-03** | Security redaction is property-tested against secret leakage. | Phase 1 | `markflow/security.py`; Hypothesis/property tests |

### Testing and GSD Governance

| REQ-ID | Requirement | Phase | Evidence |
|--------|-------------|-------|----------|
| **QA-01** | Unit, integration, and functional test suites are discoverable by pytest markers. | Phase 1 | `pyproject.toml`; pytest marker tests |
| **QA-02** | CI runs compile, lint, formatting, typecheck, unit, integration, functional, and coverage gates. | Phase 1 | `.github/workflows/ci.yml`; `.planning/config.json` |
| **GSD-01** | GSD is installed locally for Codex in `.codex/`. | Phase 1 | `.codex/`; GSD workflow docs |
| **GSD-02** | GSD planning artifacts exist under `.planning/`. | Phase 1 | `.planning/PROJECT.md`; `.planning/STATE.md`; `.planning/ROADMAP.md` |
| **GSD-03** | Every v1 requirement has a machine-readable spec entry with implementation and test references. | Phase 1 | `.planning/specs/features.json`; spec tests |
| **GSD-04** | Pytest fails if requirement/spec/test traceability becomes incomplete. | Phase 1 | `tests/spec/test_gsd_spec_traceability.py` |
| **GSD-05** | Decision ledger, changelog, and cross-agent rationale docs are maintained as first-class artifacts. | Phase 6 | `.planning/decisions/DECISION_LOG.md`; `docs/CHANGELOG_DECISOES.md` |

### Service Runtime and Contracts

| REQ-ID | Requirement | Phase | Evidence |
|--------|-------------|-------|----------|
| **API-01** | API-owned canonical reducer applies worker stream events with idempotency and monotonic page-state progression. | Phase 6 | `services/api/state_store.py`; web foundation tests |
| **EVT-01** | Redis Streams envelopes and event payloads are versioned (`v1`) and schema-validated in tests. | Phase 6 | `docs/architecture/event-contracts.md`; event schema tests |
| **SVC-01** | Service isolation boundaries are enforced by deterministic checks and fail CI on forbidden imports. | Phase 6 | `docs/architecture/service-isolation-policy.md`; `scripts/check_service_boundaries.py` |
| **OPS-01** | CI validates multi-service runtime readiness including dependency install, frontend build, service checks, and coverage gate. | Phase 6 | `.github/workflows/ci.yml`; frontend build; service checks |

## v2 Requirements

The following requirements are **Active** or future-facing. They are intentionally outside the current v1 traceability parser until promoted into a validated spec.

| REQ-ID | Requirement | Target | Notes |
|--------|-------------|--------|-------|
| GSD-06 | Planning docs remain aligned to GSD Core format across PROJECT, REQUIREMENTS, STATE, and ROADMAP. | Phase 7 | Introduced by 2026-06-07 restructuring request. |
| GOV-01 | Decision ledger and decision rationale changelog stay synchronized after meaningful process or architecture changes. | Phase 7 | Extends GSD-05 as ongoing governance. |
| OPS-02 | Local temp-folder ACL cleanup issue is investigated and resolved when workstation permissions allow. | Phase 7 | Existing STATE note: `.pytest-tmp`, `test-tmp`, `manual-tmp`, `.tmp`. |
| QA-04 | Add curated non-sensitive real-world PDF samples if storage and privacy constraints allow. | Future | Replaces earlier generated-fixture-only follow-up. |
| DEPLOY-01 | Evaluate Dokploy deployment and Cloudflare Tunnel publication path from `.planning/AUDIT.md`. | Future | Must preserve service isolation and secrets posture. |
| DOC-01 | Review stale/legacy execution and assistant-runtime documentation before next release. | Future | Includes `EXECUTION_MODES.md`, `.codex/`, Copilot/Codex docs, and audit notes. |

## Out of Scope

| Feature | Reason |
|---------|--------|
| Live network LLM calls in normal test gates | Non-deterministic, credential-dependent, and expensive. |
| Real OCR binary execution in CI | Depends on native binaries and host image details. |
| Production secret management backends such as Vault/KMS | Current baseline uses environment-driven secret provisioning. |
| Service-boundary collapse into one shared runtime | Violates the service-isolation policy and deployment ownership model. |
| Worker or frontend canonical-state mutation | API-owned reducer is the canonical state authority. |
| Sensitive sample PDFs in the repository | Data privacy and compliance risk. |
| Public persistence of API keys or provider credentials | Violates security invariants and credential lifecycle rules. |
| Stack migration from Python OCR/ML core to TypeScript/Bun by default | Python is the correct domain stack for OCR/ML integration. |

## Traceability Table

| REQ-ID | Status | Phase | Spec Source | Acceptance Evidence |
|--------|--------|-------|-------------|---------------------|
| CLI-01 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| CLI-02 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| CLI-03 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| CLI-04 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| PIPE-01 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| PIPE-02 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| PIPE-03 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| PIPE-04 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| PIPE-05 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| PIPE-06 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| PIPE-07 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| PIPE-08 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| PIPE-09 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| LLM-01 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| LLM-02 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| LLM-03 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| LLM-04 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| LLM-05 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| SEL-01 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| SEL-02 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| SEL-03 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| TUI-01 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| TUI-02 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| SEC-01 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| SEC-02 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| SEC-03 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| QA-01 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| QA-02 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| GSD-01 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| GSD-02 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| GSD-03 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| GSD-04 | Validated | Phase 1 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| GSD-05 | Validated | Phase 6 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| API-01 | Validated | Phase 6 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| EVT-01 | Validated | Phase 6 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| SVC-01 | Validated | Phase 6 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| OPS-01 | Validated | Phase 6 | `.planning/specs/features.json` | `.planning/specs/feature_acceptance_matrix.md` |
| GSD-06 | Active | Phase 7 | `.planning/PROJECT.md`; `.planning/STATE.md`; `.planning/ROADMAP.md` | Documentation review and spec/service-boundary checks |
| GOV-01 | Active | Phase 7 | `.planning/decisions/DECISION_LOG.md`; `docs/CHANGELOG_DECISOES.md` | Decision ledger entry and synchronized rationale docs |
| OPS-02 | Active | Phase 7 | `.planning/STATE.md`; `.planning/ROADMAP.md` | Workstation cleanup investigation |
| QA-04 | Active | Future | `.planning/ROADMAP.md` | Curated fixture policy and deterministic tests |
| DEPLOY-01 | Active | Future | `.planning/AUDIT.md`; `.planning/ROADMAP.md` | Deployment plan preserving service isolation |
| DOC-01 | Active | Future | `.planning/AUDIT.md`; `.planning/ROADMAP.md` | Documentation review before release |

## Coverage Summary

| Metric | Count |
|--------|-------|
| Validated v1/v1.1 requirements | 37 |
| Active requirements | 6 |
| Validated requirements mapped to phases | 37 |
| Validated requirements with spec/acceptance traceability | 37 |
| Unmapped validated requirements | 0 |

---
*Requirements defined: 2026-04-19*
*Last updated: 2026-06-07 after GSD Core documentation restructuring.*
