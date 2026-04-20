from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.spec


ROOT = Path(__file__).resolve().parents[2]


def test_integration_artifacts_exist() -> None:
    required = [
        ".github/copilot-instructions.md",
        ".planning/SKILLS_FOR_COPILOT.md",
        ".planning/copilot-state.md",
        ".planning/COPILOT_HANDOFF_PROTOCOL.md",
        ".planning/CONTEXT_FOR_AGENTS.md",
        ".planning/AGENT_ROLES.md",
        "docs/INTEGRATION_COPILOT_CODEX.md",
        "AGENTS.md",
    ]
    missing = [path for path in required if not (ROOT / path).exists()]
    assert missing == []


def test_copilot_instructions_have_required_sections() -> None:
    text = (ROOT / ".github/copilot-instructions.md").read_text(encoding="utf-8")
    assert "Project Overview" in text
    assert "Constraints" in text
    assert "Handoff Protocol" in text
    assert ".planning/COPILOT_HANDOFF_PROTOCOL.md" in text


def test_skill_mapping_mentions_supported_and_partial_paths() -> None:
    text = (ROOT / ".planning/SKILLS_FOR_COPILOT.md").read_text(encoding="utf-8")
    assert "Full Support" in text
    assert "Partial Support" in text
    assert "$gsd-plan-phase" in text
    assert "$gsd-execute-phase" in text


def test_handoff_protocol_and_checkpoint_templates_are_actionable() -> None:
    protocol = (ROOT / ".planning/COPILOT_HANDOFF_PROTOCOL.md").read_text(encoding="utf-8")
    checkpoint = (ROOT / ".planning/copilot-state.md").read_text(encoding="utf-8")
    assert "Copilot -> Codex Handoff" in protocol
    assert "Codex -> Copilot Resume" in protocol
    assert "CODEX CHECKPOINT" in protocol
    assert "Copilot Session Checkpoint" in checkpoint
    assert "Current Phase" in checkpoint


def test_agents_and_skill_are_aligned_for_decision_governance() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    skill = (ROOT / ".codex/skills/gsd-decision-ledger/SKILL.md").read_text(encoding="utf-8")
    assert ".planning/COPILOT_HANDOFF_PROTOCOL.md" in agents
    assert "$gsd-decision-ledger" in agents
    assert "copilot-state.md" in skill
    assert "GitHub Copilot" in skill
