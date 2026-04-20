# Service Isolation Policy

This policy defines mandatory service boundaries for MarkFlow v1.

## Hard Rules

1. Frontend, API, and Worker are isolated services.
2. Cross-service code imports are forbidden.
3. Allowed cross-service communication is only:
   - HTTP APIs
   - Redis Streams events
4. API is the canonical state authority.
5. Worker must never mutate canonical state.
6. Frontend must never write canonical state.

## Monorepo Service Structure

- `services/frontend`: frontend runtime/build/deploy assets
- `services/api`: API runtime/build/deploy assets
- `services/worker`: worker runtime/build/deploy assets
- `services/api/contracts/http`: explicit HTTP contract boundary
- `services/api/contracts/events`: API-side versioned event schemas
- `services/worker/contracts/events`: worker-side versioned event schemas

## Shared Core Allowlist

Shared code is allowed only when it is neutral and service-agnostic.

- Allowed: `markflow.*` modules that are core utilities/contracts
- Forbidden for worker: importing API namespace modules (`markflow.web.*`)
- Forbidden for all services: importing another service runtime module under `services/*`

## Canonical State Ownership

- Canonical job state transitions are applied only inside API-owned reducer/state logic.
- Worker publishes execution observations only (progress/result events).
- Frontend submits commands and renders API state only.

## API Key Lifecycle Invariants

1. API keys are request-scope only.
2. API keys must never be written to Redis Streams payloads.
3. API keys must never be written to canonical state.
4. API keys must never appear in logs, error traces, or dead-letter records.
5. Worker credentials come from worker runtime secrets, never from cross-service payloads.

## Enforcement

- Deterministic boundary checks run via `python scripts/check_service_boundaries.py`.
- CI fails when forbidden import edges are detected.
- Required roots (`services/*`, `services/api/contracts/*`, `services/worker/contracts/events`) are validated in boundary checks.
