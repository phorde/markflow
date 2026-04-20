# Context for Cross-Agent Continuity

This file gives Copilot and Codex a shared context baseline.

## Current Product Focus

MarkFlow is an OCR-first extraction pipeline with auditable outputs and strict service isolation.

Primary reference files:

1. .planning/PROJECT.md
2. .planning/STATE.md
3. .planning/REQUIREMENTS.md
4. .planning/specs/features.json
5. .planning/specs/feature_acceptance_matrix.md
6. .planning/decisions/DECISION_LOG.md

## Hard Constraints

1. Service isolation is mandatory across services/frontend, services/api, and services/worker.
2. API is canonical state authority; workers do not mutate canonical state directly.
3. Requirement/spec/test traceability must remain complete.
4. Coverage gate remains at 100 percent in CI.
5. Sensitive/strict workflows must preserve fail-closed behavior.

## Working Agreements

1. Record meaningful architecture/process decisions in DECISION_LOG.md.
2. Keep changelog rationale synchronized in docs/CHANGELOG_DECISOES.md when major shifts occur.
3. Prefer deterministic tests and avoid adding default test dependencies on external providers.

## Current Phase Snapshot

Read .planning/STATE.md for the live phase and gate status.

## Handoff Artifacts

1. Session checkpoint: .planning/copilot-state.md
2. Handoff protocol: .planning/COPILOT_HANDOFF_PROTOCOL.md
3. Role boundaries: .planning/AGENT_ROLES.md
4. Operational runbook: docs/INTEGRATION_COPILOT_CODEX.md
