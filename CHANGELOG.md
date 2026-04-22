# Changelog

All notable changes to this project are documented in this file.

## [1.1.0] - 2026-04-20

### Deployment Follow-up - 2026-04-22

- Added Render Blueprint deployment configuration for isolated API, frontend, worker, and Key Value services.
- Made production CORS configurable through `MARKFLOW_ALLOWED_ORIGINS`.
- Updated Docker entrypoints to respect Render-provided `PORT` values for web services.
- Documented the free-tier deployment constraint that Render background workers require a paid plan, so the zero-cost demo worker runs as an isolated web service with `/health`.

### CI Follow-up - 2026-04-21

- Fixed Linux `mypy` failures in the Python 3.10/3.11/3.12 CI matrix by avoiding direct type-checked access to platform-specific runtime attributes (`subprocess.CREATE_NEW_PROCESS_GROUP`, `ctypes.windll`, `signal.SIGKILL`).
- Improved POSIX timeout cleanup in `scripts/run_with_timeout.py` by terminating the process group before escalating to a stronger signal.

### Added

- Multi-service runtime structure under `services/frontend`, `services/api`, and `services/worker`.
- Versioned Redis event contract schemas for API and worker services.
- Deterministic service-boundary checker (`scripts/check_service_boundaries.py`) and CI integration.
- Frontend production build pipeline with Next.js 16.2.3 and typed API client integration.
- Copilot/Codex integration governance package:
- `.github/copilot-instructions.md`
- `.planning/SKILLS_FOR_COPILOT.md`
- `.planning/copilot-state.md`
- `.planning/COPILOT_HANDOFF_PROTOCOL.md`
- `.planning/CONTEXT_FOR_AGENTS.md`
- `.planning/AGENT_ROLES.md`
- `docs/INTEGRATION_COPILOT_CODEX.md`
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
- CI includes Copilot/Codex integration artifact validation prior to test matrix execution.
- Black CI invocation now uses `--no-cache` and a hard timeout to avoid Windows cache hangs.
- API stream processing behavior hardened for idempotent ACK and reducer commit semantics.
- Frontend job tracking improved with terminal-state handling and low-confidence page approval flow.
- Broker runtime checks now use explicit fail-fast guards instead of assert-based checks in service runtimes.
- Worker health endpoint now defaults to loopback bind (`127.0.0.1`) with env override support for containerized deployments.
- Timeout runner resolves executable paths deterministically before process launch and keeps bounded process-tree termination.

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
- Security audit hardening reduced Bandit findings to zero in project runtime sources.

## [1.0.0] - 2026-04-19

### Added

- GSD migration baseline:
- `.codex/` local runtime
- `.planning/` planning/spec/state artifacts
- Spec traceability tests and requirement matrix
- 100% coverage gate across core modules.
