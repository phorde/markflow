# Conventions

**Mapped:** 2026-04-19

## Python Style

- Formatting uses `black` with line length 100.
- Linting uses `ruff` and `flake8`.
- Type checking uses `mypy` with `check_untyped_defs`.
- Tests use pytest markers and fixtures.

## Design Patterns

- Public CLI behavior is kept in `markflow/cli.py`.
- Large orchestration remains in `markflow/pipeline.py`, while pure reusable helpers are extracted into `markflow/extraction/`.
- Compatibility wrappers in `pipeline.py` preserve existing test imports and external usage.
- External services are abstracted behind `OpenAICompatibleClient`.

## Error Handling

- Document/page failures are represented in structured status fields rather than only exceptions.
- Provider errors are folded into warning tokens where possible.
- Sensitive strings must be passed through `markflow.security.redact_sensitive_text`.

## Testing Patterns

- Use mocks/stubs for live LLM and OCR dependencies.
- Use generated small PDFs from fixtures for integration/functional tests.
- Use property tests for redaction and fuzz-prone helpers.
- Use spec traceability tests to keep `.planning` aligned with test files.
