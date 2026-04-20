# AGENTS for MarkFlow

This file defines baseline behavior for agent sessions that start from Codex surfaces.

## Load Order

Always read these files first:

1. .planning/PROJECT.md
2. .planning/STATE.md
3. .planning/REQUIREMENTS.md
4. .planning/decisions/DECISION_LOG.md
5. docs/architecture/service-isolation-policy.md
6. docs/architecture/event-contracts.md

## Hard Constraints

1. Keep service isolation intact between services/frontend, services/api, and services/worker.
2. API remains canonical state authority.
3. Maintain v1 requirement/spec/test traceability.
4. Preserve CI coverage gate at 100 percent.
5. Avoid non-deterministic external dependencies in default tests.

## Cross-Agent Continuity

Use these artifacts for Copilot and Codex continuity:

- .planning/COPILOT_HANDOFF_PROTOCOL.md
- .planning/copilot-state.md
- .planning/CONTEXT_FOR_AGENTS.md
- docs/INTEGRATION_COPILOT_CODEX.md

If a handoff occurs, ensure checkpoint and evidence are updated before yield.

## Decision Governance

Record meaningful architecture or process decisions in:

- .planning/decisions/DECISION_LOG.md
- docs/CHANGELOG_DECISOES.md (when rationale narrative changes)
- CHANGELOG.md (when behavior/release surface changes)

Use $gsd-decision-ledger when possible.

## Completion Gate

Before concluding a task:

1. Run relevant tests and checks.
2. Confirm no boundary violations.
3. Verify docs and decision artifacts are synchronized.
