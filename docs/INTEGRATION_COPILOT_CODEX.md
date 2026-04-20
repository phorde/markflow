# GitHub Copilot and Codex Integration Runbook

This runbook defines day-to-day operation for cross-agent continuity.

## Startup Checklist

1. Read .github/copilot-instructions.md.
2. Read .planning/PROJECT.md.
3. Read .planning/STATE.md.
4. Read latest entries in .planning/decisions/DECISION_LOG.md.
5. Read .planning/CONTEXT_FOR_AGENTS.md.

## Copilot Session Flow

1. Assess task scope and constraints.
2. If local execution is enough, implement directly and validate.
3. If orchestration is needed, hand off to Codex.

## Copilot -> Codex Handoff Steps

1. Update .planning/copilot-state.md.
2. Record any relevant decision in DECISION_LOG.md.
3. Request Codex execution with expected output and validation commands.
4. Wait for CODEX CHECKPOINT block.

## Codex -> Copilot Resume Steps

1. Re-read .planning/copilot-state.md and .planning/STATE.md.
2. Reconcile changes and run listed validation commands.
3. Continue implementation or finalize acceptance.

## Validation Commands

Use these commands before concluding integration-related work:

```powershell
python -m pytest -m spec --no-cov
python scripts/check_service_boundaries.py
```

For focused integration checks:

```powershell
python -m pytest tests/spec/test_copilot_codex_integration.py -q --no-cov
```

## Troubleshooting

Issue: Copilot resumes with stale context.

Resolution:

1. Treat .planning/STATE.md as canonical.
2. Regenerate checkpoint in .planning/copilot-state.md.
3. Add a decision-log entry describing the conflict and resolution.

Issue: Required skill behavior is unclear.

Resolution:

1. Consult .planning/SKILLS_FOR_COPILOT.md.
2. Prefer Codex handoff for partial-support skills.

## Definition of Done for Integration Cycle

1. Checkpoint updated.
2. Decision evidence updated where applicable.
3. Required validation commands pass.
4. CI remains green.
