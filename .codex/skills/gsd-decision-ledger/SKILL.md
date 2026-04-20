---
name: "gsd-decision-ledger"
description: "Maintain an auditable cross-agent decision ledger and decision changelog context."
metadata:
  short-description: "Append, normalize, and audit decision rationale for multi-agent continuity."
---

<objective>
Keep decision context durable and queryable across sessions and agent tools.

This skill updates:
- `.planning/decisions/DECISION_LOG.md` (canonical ledger)
- `docs/CHANGELOG_DECISOES.md` (detailed rationale/changelog for humans and agents)
- `CHANGELOG.md` (release-facing history when decision changes observable behavior)

For cross-agent continuity (Copilot/Codex), this skill also validates references to:
- `.planning/COPILOT_HANDOFF_PROTOCOL.md`
- `.planning/copilot-state.md`
- `docs/INTEGRATION_COPILOT_CODEX.md`
</objective>

<usage>
Invoke with `$gsd-decision-ledger` followed by one of:

- `append`: add one structured decision entry
- `sync`: reconcile ledger and decision changelog narrative
- `audit`: verify completeness and report missing rationale/evidence fields

Examples:
- `$gsd-decision-ledger append agent=Codex scope=api decision="ACK after reducer commit" rationale="state consistency" evidence="services/api/api.py tests/unit/test_web_foundation.py" impact="idempotent event handling"`
- `$gsd-decision-ledger sync`
- `$gsd-decision-ledger audit`
</usage>

<required_fields>
For `append`, always require and persist:

1. `date_utc` (YYYY-MM-DD)
2. `agent` (Codex, Claude Code, Gemini CLI, GitHub Copilot, etc.)
3. `scope` (component/workflow/domain)
4. `decision` (single sentence, concrete)
5. `rationale` (why this option was selected)
6. `evidence` (files/tests/commits)
7. `impact` (expected behavioral or operational effect)
8. `status` (`active` or `superseded`)

When `agent` is `GitHub Copilot` or `Codex`, include in `evidence`:
- primary file paths changed
- validation command(s) or test references
- checkpoint/handoff artifact reference when applicable
</required_fields>

<process>
1. Parse command intent (`append`, `sync`, or `audit`).
2. Normalize fields to plain ASCII where possible.
3. For `append`:
   - Insert row in `.planning/decisions/DECISION_LOG.md` under `## Ledger`.
   - If decision changes user-visible behavior, append/update relevant section in `CHANGELOG.md`.
   - Add or extend rationale notes in `docs/CHANGELOG_DECISOES.md`.
4. For `sync`:
   - Ensure every active ledger decision appears in `docs/CHANGELOG_DECISOES.md`.
   - Ensure every release-relevant decision appears in `CHANGELOG.md`.
   - Ensure Copilot/Codex continuity references are aligned with protocol and runbook docs.
5. For `audit`:
   - Report missing fields, duplicated decision statements, stale superseded links, and orphaned references.
6. Preserve existing entries; never rewrite history destructively.
</process>

<guardrails>
- Do not remove historical decisions; mark as `superseded` instead.
- Do not infer evidence paths that do not exist in the repository.
- If required fields are missing, request the missing fields before writing.
- Keep one decision per row in `DECISION_LOG.md`.
</guardrails>

<references>
- `CHANGELOG.md`
- `docs/CHANGELOG_DECISOES.md`
- `.planning/decisions/DECISION_LOG.md`
- `.planning/STATE.md`
</references>

