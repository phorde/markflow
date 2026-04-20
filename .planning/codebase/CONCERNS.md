# Concerns

**Mapped:** 2026-04-19

## Technical Debt

- `markflow/pipeline.py` remains large despite extracted helper modules. More branch-level tests are needed before further decomposition.
- `markflow/tui.py` is interactive and partially covered; additional non-interactive tests should target cancellation and provider discovery errors.
- Coverage hard gate is currently 70 percent, not the aspirational 95 percent from the remediation roadmap.

## Security

- HTML sanitization depends on `bleach` with a regex fallback; fallback behavior should remain tested.
- Provider errors must always be redacted before user-visible output.
- Strict mode cache policy must remain fail-closed by default.

## Performance

- CPU-heavy rendering/OCR is moved to threads, but real throughput should be benchmarked with representative scanned PDFs.
- Routing and discovery caches are in-memory; long-running process invalidation policy should be revisited if MarkFlow becomes a service.

## Operations

- Live provider tests require credentials and should stay behind explicit `network` markers.
- Native OCR availability differs by platform; CI should avoid assuming binaries are installed.
