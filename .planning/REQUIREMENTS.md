# Requirements: MarkFlow

**Defined:** 2026-04-19
**Core Value:** Documents must never be reported as safely processed unless extraction status, confidence, and policy checks support that conclusion.

## v1 Requirements

### CLI and Configuration

- [x] **CLI-01**: User can process one PDF file or a directory of PDF files from the CLI.
- [x] **CLI-02**: User can select execution modes (`auto`, `fast`, `quality`, `local`, `remote`) with deterministic config effects.
- [x] **CLI-03**: CLI inputs are normalized into bounded `PipelineConfig` values.
- [x] **CLI-04**: CLI exit codes distinguish discovery errors, all-success runs, and document-level failures.

### Pipeline and Extraction

- [x] **PIPE-01**: Native PDF text-layer content is detected, normalized, scored, and emitted as Markdown.
- [x] **PIPE-02**: Local OCR supports EasyOCR, RapidOCR, and Tesseract result formats with confidence normalized to `0.0..1.0`.
- [x] **PIPE-03**: Remote multimodal OCR routes through provider-agnostic model selection and fallback models.
- [x] **PIPE-04**: Visual QA and NLP cleanup run only when policy thresholds and warning rules require them.
- [x] **PIPE-05**: `medical_strict` mode fails closed for low-confidence pages, unavailable LLM review, or reprocess-required states.
- [x] **PIPE-06**: Document reports expose deterministic final status, page status, warnings, confidence, elapsed time, and cache policy.
- [x] **PIPE-07**: HTML output is sanitized against script tags, event attributes, dangerous URLs, and unsafe embedded content.
- [x] **PIPE-08**: Cache entries are versioned, optionally TTL-bound, and disabled by default for sensitive strict mode.
- [x] **PIPE-09**: CPU-bound rendering and local OCR work do not block the async event loop.

### LLM, Routing, and Selection

- [x] **LLM-01**: OpenAI-compatible clients reject insecure remote base URLs while allowing localhost development URLs.
- [x] **LLM-02**: Provider auth headers, endpoint candidates, redirects, and response parsing are normalized.
- [x] **LLM-03**: Model discovery normalizes model IDs, chat/vision capabilities, context windows, and pricing metadata.
- [x] **LLM-04**: OpenAI-compatible and Anthropic message APIs normalize text responses into a shared result type.
- [x] **LLM-05**: API keys, bearer tokens, and long token-like values are redacted from errors and reports.
- [x] **SEL-01**: OCR benchmark ingestion accepts valid, partial, and invalid upstream benchmark payloads safely.
- [x] **SEL-02**: OCR-aware model ranking and recommendation are deterministic for equivalent inputs.
- [x] **SEL-03**: Task-aware routing selects model candidates based on OCR task kind, complexity, benchmark signal, and vision needs.

### TUI and User Workflow

- [x] **TUI-01**: Interactive setup applies provider presets, model discovery, and routing recommendations to CLI args.
- [x] **TUI-02**: TUI helper behavior is testable without requiring an interactive terminal.

### Output and Security

- [x] **SEC-01**: Sanitized HTML preserves legitimate Markdown tables and headings while removing active content.
- [x] **SEC-02**: Strict regulated workflows never persist sensitive cache artifacts unless explicitly opted in.
- [x] **SEC-03**: Security redaction is property-tested against secret leakage.

### Testing and GSD Governance

- [x] **QA-01**: Unit, integration, and functional test suites are discoverable by pytest markers.
- [x] **QA-02**: CI runs compile, lint, formatting, typecheck, unit, integration, functional, and coverage gates.
- [x] **GSD-01**: GSD is installed locally for Codex in `.codex/`.
- [x] **GSD-02**: GSD planning artifacts exist under `.planning/`.
- [x] **GSD-03**: Every v1 requirement has a machine-readable spec entry with implementation and test references.
- [x] **GSD-04**: Pytest fails if requirement/spec/test traceability becomes incomplete.

## v2 Requirements

### Coverage Expansion

- **QA-03**: Raise global coverage gate toward 95 percent once real-world fixtures and stable OCR mocks are expanded.
- **QA-04**: Add golden-file regression fixtures for stable PDF samples.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Live network LLM calls in normal test gates | Non-deterministic, credential-dependent, and expensive. |
| Real OCR binary execution in CI | Depends on native binaries and host image details. |
| Shipping a hosted web UI | Current product is CLI/TUI/library oriented. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLI-01 | Phase 1 | Complete |
| CLI-02 | Phase 1 | Complete |
| CLI-03 | Phase 1 | Complete |
| CLI-04 | Phase 1 | Complete |
| PIPE-01 | Phase 1 | Complete |
| PIPE-02 | Phase 1 | Complete |
| PIPE-03 | Phase 1 | Complete |
| PIPE-04 | Phase 1 | Complete |
| PIPE-05 | Phase 1 | Complete |
| PIPE-06 | Phase 1 | Complete |
| PIPE-07 | Phase 1 | Complete |
| PIPE-08 | Phase 1 | Complete |
| PIPE-09 | Phase 1 | Complete |
| LLM-01 | Phase 1 | Complete |
| LLM-02 | Phase 1 | Complete |
| LLM-03 | Phase 1 | Complete |
| LLM-04 | Phase 1 | Complete |
| LLM-05 | Phase 1 | Complete |
| SEL-01 | Phase 1 | Complete |
| SEL-02 | Phase 1 | Complete |
| SEL-03 | Phase 1 | Complete |
| TUI-01 | Phase 1 | Complete |
| TUI-02 | Phase 1 | Complete |
| SEC-01 | Phase 1 | Complete |
| SEC-02 | Phase 1 | Complete |
| SEC-03 | Phase 1 | Complete |
| QA-01 | Phase 1 | Complete |
| QA-02 | Phase 1 | Complete |
| GSD-01 | Phase 1 | Complete |
| GSD-02 | Phase 1 | Complete |
| GSD-03 | Phase 1 | Complete |
| GSD-04 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 32 total
- Mapped to phases: 32
- Unmapped: 0

---
*Requirements defined: 2026-04-19*
*Last updated: 2026-04-19 after GSD migration.*
