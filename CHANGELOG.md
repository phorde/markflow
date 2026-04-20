# Changelog

All notable changes to this project are documented in this file.

## [1.1.0] - 2026-04-20

### Added

- Multi-service runtime structure under `services/frontend`, `services/api`, and `services/worker`.
- Versioned Redis event contract schemas for API and worker services.
- Deterministic service-boundary checker (`scripts/check_service_boundaries.py`) and CI integration.
- Frontend production build pipeline with Next.js 16.2.3 and typed API client integration.
- Governance artifacts:
- `docs/CHANGELOG_DECISOES.md`
- `.planning/decisions/DECISION_LOG.md`
- `.codex/skills/gsd-decision-ledger/SKILL.md`
- Timeout runner for CI/dev commands (`scripts/run_with_timeout.py`).

### Changed

- Consolidated dependencies and packaging:
- Editable-install package discovery now includes both `markflow*` and `services*`.
- Runtime and dev dependency pins updated for compatibility and security.
- CI expanded to include service runtime checks, frontend build checks, and boundary enforcement.
- Black CI invocation now uses `--no-cache` and a hard timeout to avoid Windows cache hangs.
- API stream processing behavior hardened for idempotent ACK and reducer commit semantics.
- Frontend job tracking improved with terminal-state handling and low-confidence page approval flow.

### Fixed

- Anthropic multimodal image content handling in `markflow/llm_client.py`.
- Service boundary checker regex and scan exclusions (`.next`, `node_modules`, caches).
- URL redaction and route-cache key scoping in `markflow/pipeline.py`.
- Worker entrypoint import/runtime bootstrap behavior for service execution.
- Black verification hang caused by cache/temp-file behavior in this Windows workspace.

### Security

- Removed known vulnerable dependency combinations in development/runtime manifests.
- Enforced explicit safe pins for FastAPI/Starlette test/runtime stack.
- Preserved fail-closed and redaction guarantees across CLI/core/service paths.

## [1.0.0] - 2026-04-19

### Added

- GSD migration baseline:
- `.codex/` local runtime
- `.planning/` planning/spec/state artifacts
- Spec traceability tests and requirement matrix
- 100% coverage gate across core modules.
