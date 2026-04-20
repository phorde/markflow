from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.spec


ROOT = Path(__file__).resolve().parents[2]


def test_decision_governance_artifacts_exist() -> None:
    required_paths = [
        "CHANGELOG.md",
        "docs/CHANGELOG_DECISOES.md",
        "docs/INTEGRATION_COPILOT_CODEX.md",
        ".github/copilot-instructions.md",
        ".planning/decisions/DECISION_LOG.md",
        ".planning/COPILOT_HANDOFF_PROTOCOL.md",
        ".planning/copilot-state.md",
        ".planning/SKILLS_FOR_COPILOT.md",
        "AGENTS.md",
        ".codex/skills/gsd-decision-ledger/SKILL.md",
    ]

    missing = [path for path in required_paths if not (ROOT / path).exists()]
    assert missing == []


def test_decision_log_has_template_and_entries() -> None:
    text = (ROOT / ".planning/decisions/DECISION_LOG.md").read_text(encoding="utf-8")
    assert (
        "| Date (UTC) | Agent | Scope | Decision | Rationale | Evidence | Impact | Status |" in text
    )
    assert "| 2026-04-" in text


def test_decision_changelog_covers_cross_agent_context() -> None:
    text = (ROOT / "docs/CHANGELOG_DECISOES.md").read_text(encoding="utf-8")
    assert "Registro por Agente" in text
    assert "Codex" in text
    assert "GitHub Copilot" in text


def test_release_changelog_mentions_governance_additions() -> None:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Decision Log" in text or "decision" in text.lower()
    assert "gsd-decision-ledger" in text


def test_copilot_codex_artifacts_are_cross_referenced() -> None:
    copilot_instructions = (ROOT / ".github/copilot-instructions.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs/INTEGRATION_COPILOT_CODEX.md").read_text(encoding="utf-8")
    handoff = (ROOT / ".planning/COPILOT_HANDOFF_PROTOCOL.md").read_text(encoding="utf-8")

    assert ".planning/COPILOT_HANDOFF_PROTOCOL.md" in copilot_instructions
    assert ".planning/copilot-state.md" in copilot_instructions
    assert "Copilot -> Codex Handoff" in handoff
    assert "Validation Commands" in runbook


def test_ci_enforces_service_runtime_checks() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "service-boundaries" in workflow
    assert "service-runtime-checks" in workflow
    assert "npm run build" in workflow
    assert "check_service_boundaries.py" in workflow
