# Services Monorepo Layout

This repository uses isolated services inside one monorepo.

## Service Roots

- `services/frontend`: frontend runtime/build/deploy assets
- `services/api`: API runtime/build/deploy assets
- `services/worker`: worker runtime/build/deploy assets

## Source Ownership

- Frontend source code: `services/frontend/`
- API canonical state and HTTP/SSE layer: `services/api/`
- Worker runtime loop and broker adapter: `services/worker/`
- Legacy `markflow/*` modules remain for CLI/core compatibility, not for service runtime imports

## Isolation Rules

- No service may import runtime code from another service.
- Allowed integration paths only:
  - HTTP/SSE API contracts (`services/api/contracts/http`)
  - Broker event contracts (`services/api/contracts/events`, `services/worker/contracts/events`)

## Validation

Run boundary checks from repository root:

```bash
python scripts/check_service_boundaries.py
```
