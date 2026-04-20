# GitHub Copilot Instructions for MarkFlow

## Project Overview

MarkFlow is a provider-agnostic, OCR-first extraction system with strict governance and service-isolation rules.

Always load these files first when starting work:

1. .planning/PROJECT.md
2. .planning/STATE.md
3. .planning/REQUIREMENTS.md
4. .planning/decisions/DECISION_LOG.md
5. docs/architecture/service-isolation-policy.md
6. docs/architecture/event-contracts.md

## Constraints

These are mandatory constraints for Copilot sessions:

1. Service isolation is mandatory: do not create direct runtime imports between services/frontend, services/api, and services/worker.
2. API is the canonical state authority.
3. Every meaningful architecture or process decision must be recorded in .planning/decisions/DECISION_LOG.md.
4. Keep v1 requirement traceability intact in .planning/specs/features.json and tests/spec.
5. CI coverage gate is 100 percent; changes must include tests when behavior changes.
6. Do not introduce non-deterministic network dependencies into default tests.

## Codex Workflow Compatibility

Codex runtime is installed in .codex/. Copilot may ask Codex to execute workflow skills when atomic multi-file orchestration is needed.

Common skills:

- $gsd-plan-phase
- $gsd-execute-phase
- $gsd-code-review
- $gsd-code-review-fix
- $gsd-verify-work
- $gsd-review
- $gsd-decision-ledger

For skill catalog and fallback behavior, see .planning/SKILLS_FOR_COPILOT.md.

## Tool Mapping

When a skill workflow requests AskUserQuestion semantics, use VS Code question tools in Copilot chat.

- AskUserQuestion (Codex/Claude style) -> vscode_askQuestions (Copilot)

If an operation requires Codex-only orchestration primitives, save state and hand off.

## Handoff Protocol

Use .planning/COPILOT_HANDOFF_PROTOCOL.md as the source of truth.

Minimum Copilot -> Codex handoff steps:

1. Save checkpoint in .planning/copilot-state.md.
2. Record decision/evidence in .planning/decisions/DECISION_LOG.md.
3. Specify target skill and expected output.
4. On resume, reconcile .planning/copilot-state.md with .planning/STATE.md.

## Completion Checklist

Before finishing a task:

1. Run relevant tests/lint commands.
2. Confirm no service-boundary violations.
3. Update DECISION_LOG if a design or process decision was made.
4. Keep docs synchronized if workflow/process behavior changed.
