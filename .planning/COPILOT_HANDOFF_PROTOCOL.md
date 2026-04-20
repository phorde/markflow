# Copilot <-> Codex Handoff Protocol

Purpose: deterministic and auditable handoff between GitHub Copilot and Codex in this repository.

## Canonical Inputs

Before any handoff, both agents must align on:

1. .planning/STATE.md
2. .planning/PROJECT.md
3. .planning/decisions/DECISION_LOG.md
4. .planning/copilot-state.md

## Copilot -> Codex Handoff

Use this when task execution requires Codex orchestration (multi-wave, multi-file, subagent fan-out, or long-running phase execution).

### Procedure

1. Save checkpoint in .planning/copilot-state.md.
2. Append decision entry in .planning/decisions/DECISION_LOG.md if a design/process decision was made.
3. Include requested skill and expected outputs in checkpoint.
4. Ask Codex to execute and return a structured completion block.

### Required Completion Block from Codex

Use this exact shape in responses and logs:

CODEX CHECKPOINT
- Files changed:
- Validation commands run:
- Validation result:
- Artifacts produced:
- Decision log updated: yes/no
- Recommended next step for Copilot:

## Codex -> Copilot Resume

### Procedure

1. Copilot reads .planning/copilot-state.md.
2. Copilot reads latest .planning/STATE.md and decision log entries.
3. Copilot reconciles differences:
   - If state differs, STATE.md wins.
   - If checkpoint lacks evidence, request clarification before proceeding.
4. Copilot continues from the latest validated state.

## Conflict Resolution

If state conflicts cannot be reconciled:

1. Record conflict in DECISION_LOG.md with status active.
2. Stop execution on risky paths.
3. Route through $gsd-review or $gsd-verify-work before continuing.

## Minimum Validation for Every Handoff

1. Checkpoint exists and is updated.
2. Decision evidence is recorded when relevant.
3. Validation command list is present.
4. Next step owner is explicit (Copilot or Codex).
