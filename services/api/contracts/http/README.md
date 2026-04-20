# HTTP Contract Authority

This directory is the explicit HTTP contract boundary for isolated services.

## Source of Truth

- Runtime authority: API service OpenAPI exposed by FastAPI (`/openapi.json`)
- Ownership: `services/api`

## Contract Rules

- Frontend communicates with backend only via HTTP/SSE endpoints defined by the API.
- Worker must not call frontend internals or API runtime internals directly.
- No service may import another service's runtime code.

## Optional Snapshot Workflow

When needed, generate a versioned snapshot from a running API service:

```bash
curl http://127.0.0.1:8000/openapi.json -o services/api/contracts/http/openapi.v1.json
```

Keep snapshots versioned and non-breaking for consumers.
