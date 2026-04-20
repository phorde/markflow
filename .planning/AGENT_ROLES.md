# Agent Roles and Responsibilities

Defines operational boundaries for Copilot and Codex in this repository.

## GitHub Copilot

Primary responsibilities:

1. Architecture-level reasoning and implementation planning
2. Interactive user clarification and decision shaping
3. Small to medium scoped code edits and verification
4. Documentation updates and continuity checks

Handoff triggers to Codex:

1. Multi-file atomic orchestration is required
2. Wave-based execution is required
3. GSD skills with heavy orchestration semantics are required

## Codex

Primary responsibilities:

1. GSD workflow orchestration from .codex/skills and .codex/workflows
2. Multi-step execution with explicit checkpoints
3. Large execution batches and artifact generation
4. Structured completion checkpoints for resume

Handoff triggers to Copilot:

1. Interactive decision loops with user guidance
2. Final review, explanation, and acceptance checks
3. Targeted small adjustments after major orchestration

## Shared Responsibilities

1. Keep .planning/STATE.md aligned with reality.
2. Record decisions in .planning/decisions/DECISION_LOG.md.
3. Follow .planning/COPILOT_HANDOFF_PROTOCOL.md on every handoff.
4. Preserve CI gates and service-isolation constraints.
