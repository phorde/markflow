from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.spec


ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / ".planning" / "REQUIREMENTS.md"
FEATURES = ROOT / ".planning" / "specs" / "features.json"
ACCEPTANCE_MATRIX = ROOT / ".planning" / "specs" / "feature_acceptance_matrix.md"


def _v1_requirement_ids() -> set[str]:
    text = REQUIREMENTS.read_text(encoding="utf-8")
    v1_match = re.search(r"## v1 Requirements(?P<body>.*?)## v2 Requirements", text, re.S)
    assert v1_match, "REQUIREMENTS.md must contain v1 and v2 sections"
    return set(re.findall(r"\*\*([A-Z]+-\d{2})\*\*", v1_match.group("body")))


def _feature_specs() -> list[dict[str, object]]:
    payload = json.loads(FEATURES.read_text(encoding="utf-8"))
    requirements = payload.get("requirements")
    assert isinstance(requirements, list), "features.json must contain a requirements list"
    return requirements


def _acceptance_sections() -> dict[str, str]:
    text = ACCEPTANCE_MATRIX.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^### (?P<id>[A-Z]+-\d{2})\s*$", text, re.M))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group("id")] = text[start:end]
    return sections


def _test_file_contains_tests(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return bool(re.search(r"^def test_|^async def test_", text, re.M))


def test_all_v1_requirements_have_exactly_one_feature_spec() -> None:
    requirement_ids = _v1_requirement_ids()
    specs = _feature_specs()
    spec_ids = [str(item.get("id", "")) for item in specs]

    assert len(spec_ids) == len(set(spec_ids)), "features.json contains duplicate IDs"
    assert set(spec_ids) == requirement_ids


def test_every_feature_spec_has_existing_implementation_and_tests() -> None:
    for spec in _feature_specs():
        spec_id = str(spec.get("id", ""))
        implementations = spec.get("implementation")
        tests = spec.get("tests")

        assert (
            isinstance(implementations, list) and implementations
        ), f"{spec_id} must list implementation paths"
        assert isinstance(tests, list) and tests, f"{spec_id} must list test paths"

        for raw_path in implementations + tests:
            assert (
                isinstance(raw_path, str) and raw_path.strip()
            ), f"{spec_id} contains an invalid path"
            path = ROOT / raw_path
            assert path.exists(), f"{spec_id} references missing path: {raw_path}"

        for raw_path in tests:
            path = ROOT / str(raw_path)
            assert _test_file_contains_tests(path), f"{spec_id} references test file with no tests"


def test_every_v1_requirement_has_acceptance_criteria_and_test_evidence() -> None:
    requirement_ids = _v1_requirement_ids()
    sections = _acceptance_sections()

    assert set(sections) == requirement_ids

    for requirement_id, body in sections.items():
        assert "Acceptance Criteria:" in body, f"{requirement_id} lacks acceptance criteria"
        assert "Test Evidence:" in body, f"{requirement_id} lacks test evidence"
        assert re.search(r"^- .+", body, re.M), f"{requirement_id} lacks bullet evidence"


def test_every_production_module_is_mapped_to_at_least_one_feature_spec() -> None:
    specs = _feature_specs()
    mapped_paths = {
        str(path).replace("\\", "/")
        for spec in specs
        for path in spec.get("implementation", [])
        if isinstance(path, str)
    }
    production_modules = {
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (ROOT / "markflow").rglob("*.py")
        if path.name != "__init__.py"
    }

    assert production_modules - mapped_paths == set()


def test_every_referenced_test_file_is_evidence_for_at_least_one_acceptance_section() -> None:
    matrix_text = ACCEPTANCE_MATRIX.read_text(encoding="utf-8")
    referenced_tests = {
        str(path).replace("\\", "/")
        for spec in _feature_specs()
        for path in spec.get("tests", [])
        if isinstance(path, str)
    }

    for test_path in referenced_tests:
        assert test_path in matrix_text, f"{test_path} is not listed in acceptance matrix"


def test_gsd_runtime_and_planning_artifacts_exist() -> None:
    required_paths = [
        ".codex/config.toml",
        ".codex/gsd-file-manifest.json",
        ".codex/get-shit-done/VERSION",
        ".planning/config.json",
        ".planning/PROJECT.md",
        ".planning/REQUIREMENTS.md",
        ".planning/ROADMAP.md",
        ".planning/STATE.md",
        ".planning/specs/features.json",
        ".planning/specs/feature_acceptance_matrix.md",
        ".planning/codebase/ARCHITECTURE.md",
        ".planning/codebase/CONCERNS.md",
        ".planning/codebase/CONVENTIONS.md",
        ".planning/codebase/INTEGRATIONS.md",
        ".planning/codebase/STACK.md",
        ".planning/codebase/STRUCTURE.md",
        ".planning/codebase/TESTING.md",
    ]

    missing = [path for path in required_paths if not (ROOT / path).exists()]
    assert missing == []


def test_ci_runs_spec_traceability_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Spec traceability" in workflow
    assert "pytest -m spec" in workflow
