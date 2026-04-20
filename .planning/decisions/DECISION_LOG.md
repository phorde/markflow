# Decision Log

## Purpose

Canonical ledger for architectural, operational, and governance decisions.
Each entry must identify the deciding agent, rationale, and evidence.

## Entry Template

| Date (UTC) | Agent | Scope | Decision | Rationale | Evidence | Impact | Status |
|------------|-------|-------|----------|-----------|----------|--------|--------|
| YYYY-MM-DD | Codex/Claude/Gemini/Copilot/etc | component or workflow | concise decision statement | why this was chosen | file paths, tests, PR/commit refs | expected effect | active/superseded |

## Ledger

| Date (UTC) | Agent | Scope | Decision | Rationale | Evidence | Impact | Status |
|------------|-------|-------|----------|-----------|----------|--------|--------|
| 2026-04-19 | GitHub Copilot | architecture | Split runtime into `services/frontend`, `services/api`, `services/worker`. | Strong ownership and deploy isolation across UI/control-plane/processing-plane. | `services/*`, `docker-compose.yml` | Enables service-level hardening and scaling boundaries. | active |
| 2026-04-19 | Carver | frontend/runtime | Harden terminal-state handling and low-confidence approval UX. | Avoid infinite polling and unblock review/export workflows. | `services/frontend/app/page.tsx` | Improves job lifecycle reliability in UI. | active |
| 2026-04-19 | Averroes | event-processing | ACK stream events only after API reducer commit. | Preserve canonical-state correctness with at-least-once delivery. | `services/api/api.py`, `services/api/state_store.py` | Prevents state divergence under replay/duplicates. | active |
| 2026-04-19 | Herschel | llm-adapter | Preserve Anthropic multimodal image blocks. | Restore parity between providers and keep OCR multimodal path functional. | `markflow/llm_client.py`, `tests/unit/test_llm_client_additional.py` | Correct remote vision pipeline behavior. | active |
| 2026-04-19 | Pascal | architecture-governance | Tighten boundary checker regex and ignored dirs. | Reduce false positives and ensure stable CI checks. | `scripts/check_service_boundaries.py`, `tests/unit/test_service_boundary_checker.py` | Reliable enforcement of service isolation policy. | active |
| 2026-04-19 | Locke | dependencies | Resolve test stack conflicts and vulnerable pins. | Keep audit clean and avoid resolver instability. | `pyproject.toml`, `requirements-dev.txt`, `requirements.txt` | Reproducible and safer installs. | active |
| 2026-04-20 | Codex | packaging/governance | Add explicit package discovery for editable installs and decision-governance docs/skill. | Avoid setuptools flat-layout ambiguity and preserve cross-agent continuity. | `pyproject.toml`, `CHANGELOG.md`, `docs/CHANGELOG_DECISOES.md`, `.codex/skills/gsd-decision-ledger/SKILL.md` | Stable local/CI installs plus auditable decision context. | active |
| 2026-04-20 | Codex | ci-tooling | Run Black through `scripts/run_with_timeout.py` with `--no-cache`. | `black 26.3.1` hung on cache/temp-file behavior in this Windows workspace, while `--no-cache` passed immediately. | `scripts/run_with_timeout.py`, `.github/workflows/ci.yml`, `tests/unit/test_run_with_timeout.py` | Converts formatting hangs into bounded failures and prevents orphaned child processes. | active |
