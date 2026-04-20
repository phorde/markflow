# Skills for Copilot (Codex Runtime Mapping)

This document maps Codex GSD skills to practical Copilot usage.

Source of truth for installed skills: .codex/skills/

## Full Support (recommended from Copilot)

These skills are straightforward to trigger from Copilot sessions.

| Skill | Typical Use | Copilot Notes |
|---|---|---|
| $gsd-help | Discover commands and usage | Safe default at session start |
| $gsd-progress | Read current project progress | Useful before planning |
| $gsd-plan-phase | Build phase plan artifacts | Uses question prompts for decisions |
| $gsd-review | Review current work status | Good for checkpointing |
| $gsd-map-codebase | Refresh map and architecture context | Read-heavy workflow |
| $gsd-research-phase | Research before planning | Produces research artifacts |
| $gsd-verify-work | Goal-backward verification | Useful before release decisions |
| $gsd-decision-ledger | Record rationale in decision log | Required for traceability |

## Partial Support (requires structured handoff)

These usually require Codex orchestration semantics or longer-running multi-step execution.

| Skill | Why Partial | Copilot Fallback |
|---|---|---|
| $gsd-execute-phase | Multi-wave orchestration, subagent fan-out | Save checkpoint; request Codex execution; resume from state |
| $gsd-code-review | Deep scanning with generated artifacts | Run from Codex, then summarize in Copilot |
| $gsd-code-review-fix | Atomic fixes over many files | Use Codex for execution; Copilot validates outcomes |
| $gsd-debug | Iterative, checkpointed debug loops | Hand off to Codex and require checkpoint output |
| $gsd-secure-phase | Security-focused review/fix workflow | Run in Codex, then verify tests in Copilot |
| $gsd-ui-phase | Spec-first UI orchestration | Keep Copilot as reviewer unless execution is small |

## High-Leverage Utility Skills

These are often useful from Copilot for project hygiene and flow control.

- $gsd-next
- $gsd-check-todos
- $gsd-add-todo
- $gsd-docs-update
- $gsd-stats
- $gsd-session-report

## Interaction Mapping

GSD workflows often reference AskUserQuestion and Task semantics.

- AskUserQuestion -> use vscode_askQuestions in Copilot.
- Codex Task/spawn_agent orchestration -> prefer handoff to Codex when required.

## Copilot Handoff Rule

If the task requires one or more of these, perform handoff using .planning/COPILOT_HANDOFF_PROTOCOL.md:

1. Atomic multi-file execution across wave dependencies
2. Long-running orchestration with multiple generated artifacts
3. Explicit Codex subagent fan-out

Checkpoint template: .planning/copilot-state.md
