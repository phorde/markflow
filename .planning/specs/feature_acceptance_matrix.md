# Feature Acceptance Matrix

**Purpose:** define acceptance criteria and test evidence for every MarkFlow v1
feature. This file is intentionally requirement-oriented rather than
line-coverage-oriented: GSD requires every user-visible and policy-relevant
capability to have a specification and automated evidence.

## CLI and Configuration

### CLI-01
Acceptance Criteria:
- The CLI accepts a single PDF path and a directory containing PDFs.
- The CLI delegates document execution to the pipeline for every discovered PDF.
Test Evidence:
- `tests/unit/test_cli_behavior.py`
- `tests/integration/test_document_flow.py`

### CLI-02
Acceptance Criteria:
- `auto`, `fast`, `quality`, `local`, and `remote` modes apply deterministic defaults.
- Mode-derived settings remain bounded and do not silently enable unsafe behavior.
Test Evidence:
- `tests/unit/test_cli_behavior.py`

### CLI-03
Acceptance Criteria:
- CLI arguments normalize into a valid `PipelineConfig`.
- Numeric thresholds, cache options, provider settings, and review flags are bounded.
Test Evidence:
- `tests/unit/test_cli_behavior.py`

### CLI-04
Acceptance Criteria:
- CLI exit code `0` represents full operational success.
- CLI exit code `1` represents document-level failure.
- CLI exit code `2` represents discovery/configuration failure.
Test Evidence:
- `tests/unit/test_cli_behavior.py`
- `tests/integration/test_document_flow.py`

## Pipeline and Extraction

### PIPE-01
Acceptance Criteria:
- Native text-layer pages are detected before OCR fallback.
- Extracted text is normalized, scored, and emitted as Markdown.
Test Evidence:
- `tests/unit/test_pipeline_core.py`
- `tests/unit/test_extraction_submodules.py`
- `tests/functional/test_golden_regressions.py`

### PIPE-02
Acceptance Criteria:
- EasyOCR, RapidOCR, and Tesseract result shapes are normalized into one OCR contract.
- OCR confidence accepts `[0..1]`, `[0..100]`, missing, and invalid values safely.
Test Evidence:
- `tests/unit/test_pipeline_core.py`
- `tests/unit/test_pipeline_review_and_ocr_helpers.py`
- `tests/unit/test_pipeline_phase2_coverage.py`
- `tests/unit/test_extraction_submodules.py`

### PIPE-03
Acceptance Criteria:
- Remote OCR uses provider-agnostic routing for vision-capable models.
- Fallback model selection remains deterministic when discovery data is partial.
Test Evidence:
- `tests/unit/test_pipeline_review_and_ocr_helpers.py`
- `tests/unit/test_pipeline_phase2_coverage.py`
- `tests/unit/test_selection_routing_additional.py`
- `tests/unit/test_llm_and_selection.py`

### PIPE-04
Acceptance Criteria:
- Visual QA runs only when confidence, warnings, and policy permit it.
- NLP cleanup runs only when cleanup policy permits it.
Test Evidence:
- `tests/unit/test_pipeline_core.py`
- `tests/unit/test_pipeline_review_and_ocr_helpers.py`
- `tests/unit/test_extraction_submodules.py`

### PIPE-05
Acceptance Criteria:
- `medical_strict` fails closed on low confidence, missing review, or reprocess states.
- Strict review states are reflected in document status.
Test Evidence:
- `tests/unit/test_pipeline_review_and_ocr_helpers.py`
- `tests/unit/test_reporting_decision_matrix.py`
- `tests/integration/test_document_flow.py`

### PIPE-06
Acceptance Criteria:
- Reports include deterministic page status, document status, warnings, confidence, and cache policy.
- Summary observability includes fallback, low-confidence, and fail-closed signals.
Test Evidence:
- `tests/unit/test_extraction_modules.py`
- `tests/unit/test_reporting_decision_matrix.py`
- `tests/integration/test_document_flow.py`

### PIPE-07
Acceptance Criteria:
- HTML output removes active content, event handlers, dangerous URLs, and unsafe embeds.
- Safe Markdown structures remain renderable.
Test Evidence:
- `tests/unit/test_pipeline_core.py`
- `tests/unit/test_extraction_submodules.py`
- `tests/functional/test_end_to_end.py`
- `tests/functional/test_golden_regressions.py`

### PIPE-08
Acceptance Criteria:
- Cache entries are versioned by schema and payload signature.
- Cache TTL invalidates stale artifacts.
- Strict sensitive mode disables persistent cache unless explicitly enabled.
Test Evidence:
- `tests/unit/test_extraction_modules.py`
- `tests/unit/test_pipeline_core.py`
- `tests/integration/test_document_flow.py`

### PIPE-09
Acceptance Criteria:
- CPU-bound rendering and OCR are moved off the async event loop.
- Page processing respects bounded concurrency.
Test Evidence:
- `tests/unit/test_pipeline_async_behavior.py`
- `tests/unit/test_extraction_modules.py`

## LLM, Routing, and Selection

### LLM-01
Acceptance Criteria:
- OpenAI-compatible clients reject insecure remote URLs.
- Localhost development URLs remain allowed.
Test Evidence:
- `tests/unit/test_llm_client_additional.py`
- `tests/unit/test_llm_client_error_paths.py`

### LLM-02
Acceptance Criteria:
- Provider auth headers are derived consistently.
- Endpoint candidates, redirects, and response bodies are normalized.
Test Evidence:
- `tests/unit/test_llm_client_additional.py`
- `tests/unit/test_llm_client_error_paths.py`
- `tests/unit/test_llm_and_selection.py`

### LLM-03
Acceptance Criteria:
- Model IDs normalize across providers.
- Discovery captures chat/vision capability, context window, and pricing metadata.
Test Evidence:
- `tests/unit/test_llm_client_additional.py`
- `tests/unit/test_llm_and_selection.py`

### LLM-04
Acceptance Criteria:
- OpenAI-compatible chat and Anthropic messages responses normalize into shared result types.
- Error responses are redacted and surfaced without leaking secrets.
Test Evidence:
- `tests/unit/test_llm_client_additional.py`
- `tests/unit/test_llm_client_error_paths.py`

### LLM-05
Acceptance Criteria:
- API keys, bearer tokens, and token-like payloads are redacted in errors and reports.
- Redaction is robust against generated secret-like input.
Test Evidence:
- `tests/unit/test_security_redaction.py`
- `tests/unit/test_llm_client_error_paths.py`

### SEL-01
Acceptance Criteria:
- OCR benchmark ingestion accepts valid Markdown, valid HTML, partial payloads, and invalid payloads.
- Invalid upstream content degrades to safe empty signals.
Test Evidence:
- `tests/unit/test_benchmark_ingestion_additional.py`
- `tests/unit/test_llm_and_selection.py`

### SEL-02
Acceptance Criteria:
- OCR-aware ranking is deterministic for equivalent inputs.
- Ties and missing metadata are resolved predictably.
Test Evidence:
- `tests/unit/test_selection_routing_additional.py`
- `tests/unit/test_llm_and_selection.py`

### SEL-03
Acceptance Criteria:
- Routing uses task kind, complexity, benchmark signal, and vision requirements.
- Non-vision models are filtered when vision is required.
Test Evidence:
- `tests/unit/test_selection_routing_additional.py`
- `tests/unit/test_llm_and_selection.py`

## TUI and User Workflow

### TUI-01
Acceptance Criteria:
- Interactive setup applies provider presets and discovered model choices to CLI args.
- Manual fallback remains available when discovery cannot run.
Test Evidence:
- `tests/unit/test_tui_setup_flow.py`
- `tests/unit/test_tui_helpers.py`
- `tests/unit/test_tui_phase2_paths.py`

### TUI-02
Acceptance Criteria:
- TUI helpers are testable without an interactive terminal.
- Cancellation and fallback paths are deterministic.
Test Evidence:
- `tests/unit/test_tui_helpers.py`
- `tests/unit/test_tui_setup_flow.py`
- `tests/unit/test_tui_phase2_paths.py`

## Output and Security

### SEC-01
Acceptance Criteria:
- Sanitized HTML preserves legitimate Markdown headings and tables.
- Active content and unsafe attributes are removed.
Test Evidence:
- `tests/unit/test_pipeline_core.py`
- `tests/unit/test_extraction_submodules.py`
- `tests/functional/test_end_to_end.py`
- `tests/functional/test_golden_regressions.py`

### SEC-02
Acceptance Criteria:
- Strict regulated workflows do not persist sensitive cache artifacts by default.
- Reports disclose cache policy and sensitive persistence state.
Test Evidence:
- `tests/integration/test_document_flow.py`
- `tests/unit/test_extraction_modules.py`

### SEC-03
Acceptance Criteria:
- Redaction handles explicit secrets and generated token-like values.
- Redacted output never contains the original sensitive value.
Test Evidence:
- `tests/unit/test_security_redaction.py`

## Testing and GSD Governance

### QA-01
Acceptance Criteria:
- Unit, integration, functional, and spec suites are selectable by pytest markers.
- Marker configuration is committed in project configuration.
Test Evidence:
- `tests/spec/test_gsd_spec_traceability.py`

## Phase 5 Coverage Evidence

The following files provide additional structural branch coverage for already
specified v1 behavior. They are listed here so the GSD traceability gate can
verify that new coverage work remains attached to acceptance evidence:

- `tests/unit/test_coverage_phase5_small_modules.py`
- `tests/unit/test_pipeline_phase5_coverage.py`
- `tests/unit/test_llm_client_phase5_coverage.py`
- `tests/unit/test_tui_phase5_coverage.py`
- `tests/unit/test_coverage_phase5_remaining_small.py`
- `tests/unit/test_pipeline_phase5_runtime_adapters.py`

### QA-02
Acceptance Criteria:
- CI runs compile, lint, format, typecheck, test, spec, and coverage gates.
- Coverage gate is explicit and reproducible locally.
Test Evidence:
- `tests/spec/test_gsd_spec_traceability.py`

### GSD-01
Acceptance Criteria:
- GSD runtime files are installed under `.codex/`.
- The GSD file manifest exists and is versioned.
Test Evidence:
- `tests/spec/test_gsd_spec_traceability.py`

### GSD-02
Acceptance Criteria:
- Planning artifacts exist under `.planning/`.
- Codebase maps, roadmap, state, requirements, and config are present.
Test Evidence:
- `tests/spec/test_gsd_spec_traceability.py`

### GSD-03
Acceptance Criteria:
- Every v1 requirement has exactly one machine-readable feature spec.
- Every feature spec references implementation and test evidence.
Test Evidence:
- `tests/spec/test_gsd_spec_traceability.py`

### GSD-04
Acceptance Criteria:
- Missing requirements, missing test files, missing acceptance entries, or unmapped production modules fail CI.
- The spec suite is part of the normal CI workflow.
Test Evidence:
- `tests/spec/test_gsd_spec_traceability.py`

### GSD-05
Acceptance Criteria:
- Project-level changelog is maintained with dated, auditable entries.
- Decision rationale is captured in a dedicated cross-agent document.
- A reusable skill exists to append and maintain the decision ledger.
Test Evidence:
- `tests/spec/test_decision_context_governance.py`

## Service Runtime and Contracts

### API-01
Acceptance Criteria:
- API reducer applies progress/result stream events idempotently by `event_id`.
- Page/document state transitions are monotonic and do not regress terminal states.
- API acknowledges stream events only after successful reducer application.
Test Evidence:
- `tests/unit/test_web_foundation.py`

### EVT-01
Acceptance Criteria:
- Redis stream event envelopes and payloads are versioned (`v1`) and schema-validated.
- API and worker contracts remain aligned for dispatch/progress/result event types.
Test Evidence:
- `tests/unit/test_event_contract_schemas.py`
- `tests/unit/test_web_foundation.py`

### SVC-01
Acceptance Criteria:
- Frontend/API/worker service boundaries are validated by deterministic import-edge checks.
- Forbidden cross-service imports fail CI.
Test Evidence:
- `tests/unit/test_service_boundary_checker.py`
- `tests/spec/test_gsd_spec_traceability.py`

### OPS-01
Acceptance Criteria:
- CI validates service boundary checks, service runtime readiness, and full quality gates.
- Frontend build and Python quality gates run as part of normal pull-request validation.
Test Evidence:
- `tests/spec/test_gsd_spec_traceability.py`
- `tests/spec/test_decision_context_governance.py`
- `tests/unit/test_run_with_timeout.py`
