"""Deterministic service boundary checks for monorepo import isolation."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SERVICE_ROOTS = [
    REPO_ROOT / "services" / "api",
    REPO_ROOT / "services" / "worker",
    REPO_ROOT / "services" / "frontend",
]

REQUIRED_CONTRACT_ROOTS = [
    REPO_ROOT / "services" / "api" / "contracts" / "http",
    REPO_ROOT / "services" / "api" / "contracts" / "events",
    REPO_ROOT / "services" / "worker" / "contracts" / "events",
]

API_ROOTS = [
    REPO_ROOT / "services" / "api",
]

WORKER_ROOTS = [
    REPO_ROOT / "services" / "worker",
]

FRONTEND_ROOTS = [
    REPO_ROOT / "services" / "frontend",
]

PYTHON_FORBIDDEN = {
    "api": (
        "services.worker",
        "markflow",
    ),
    "worker": (
        "services.api",
        "markflow",
    ),
}

MARKFLOW_LAYER_FORBIDDEN: tuple[tuple[Path, tuple[str, ...]], ...] = (
    (
        REPO_ROOT / "markflow" / "contracts",
        (
            "markflow.web",
            "markflow.extraction",
            "markflow.pipeline",
            "services.api",
            "services.worker",
            "services.frontend",
        ),
    ),
    (
        REPO_ROOT / "markflow" / "web",
        (
            "markflow.extraction",
            "markflow.pipeline",
            "markflow.cli",
        ),
    ),
)

LEGACY_FORBIDDEN_MODULES = ("markflow.web.broker",)

FRONTEND_FORBIDDEN_PREFIXES = (
    "api/",
    "worker/",
    "markflow/web",
    "markflow/extraction",
    "markflow.web",
    "markflow.extraction",
    "services/api",
    "services/worker",
    "services.api",
    "services.worker",
)

IGNORED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
}

IMPORT_SPEC_PATTERN = re.compile(
    r"(?:import|export)\s+(?:[^'\"\n]*?\s+from\s+)?['\"]([^'\"]+)['\"]|"
    r"import\(\s*['\"]([^'\"]+)['\"]\s*\)",
    re.MULTILINE,
)


def _iter_files(root: Path, suffixes: Iterable[str]) -> Iterable[Path]:
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        relative_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIR_NAMES for part in relative_parts):
            continue
        if path.is_file() and path.suffix in suffixes:
            yield path


def _iter_python_import_modules(source: str) -> Iterable[str]:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module


def _is_forbidden_python_import(module_name: str, forbidden_prefixes: tuple[str, ...]) -> bool:
    return any(
        module_name == forbidden_prefix or module_name.startswith(f"{forbidden_prefix}.")
        for forbidden_prefix in forbidden_prefixes
    )


def _check_python_boundaries() -> list[str]:
    violations: list[str] = []

    for root in API_ROOTS:
        for path in _iter_files(root, {".py"}):
            source = path.read_text(encoding="utf-8")
            for module_name in _iter_python_import_modules(source):
                if _is_forbidden_python_import(module_name, PYTHON_FORBIDDEN["api"]):
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)} imports forbidden module '{module_name}'"
                    )

    for root in WORKER_ROOTS:
        for path in _iter_files(root, {".py"}):
            source = path.read_text(encoding="utf-8")
            for module_name in _iter_python_import_modules(source):
                if _is_forbidden_python_import(module_name, PYTHON_FORBIDDEN["worker"]):
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)} imports forbidden module '{module_name}'"
                    )

    return violations


def _check_markflow_package_boundaries() -> list[str]:
    violations: list[str] = []

    for root, forbidden_prefixes in MARKFLOW_LAYER_FORBIDDEN:
        for path in _iter_files(root, {".py"}):
            source = path.read_text(encoding="utf-8")
            for module_name in _iter_python_import_modules(source):
                if _is_forbidden_python_import(module_name, forbidden_prefixes):
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)} imports forbidden module '{module_name}'"
                    )

    for path in _iter_files(REPO_ROOT / "markflow", {".py"}):
        source = path.read_text(encoding="utf-8")
        for module_name in _iter_python_import_modules(source):
            if module_name in LEGACY_FORBIDDEN_MODULES:
                violations.append(
                    f"{path.relative_to(REPO_ROOT)} imports legacy module '{module_name}'"
                )

    return violations


def _check_frontend_boundaries() -> list[str]:
    violations: list[str] = []
    for frontend_root in FRONTEND_ROOTS:
        if not frontend_root.exists():
            continue

        for path in _iter_files(frontend_root, {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}):
            source = path.read_text(encoding="utf-8")
            for match in IMPORT_SPEC_PATTERN.finditer(source):
                specifier = match.group(1) or match.group(2)
                if not specifier:
                    continue

                if specifier.startswith("."):
                    target = (path.parent / specifier).resolve()
                    if not str(target).startswith(str(frontend_root.resolve())):
                        violations.append(
                            f"{path.relative_to(REPO_ROOT)} uses relative import outside "
                            f"frontend root: '{specifier}'"
                        )
                    continue

                if any(specifier.startswith(prefix) for prefix in FRONTEND_FORBIDDEN_PREFIXES):
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)} imports forbidden "
                        f"cross-service path '{specifier}'"
                    )

    return violations


def _check_required_roots() -> list[str]:
    expected_roots = [*REQUIRED_SERVICE_ROOTS, *REQUIRED_CONTRACT_ROOTS]
    missing = [root for root in expected_roots if not root.exists()]
    return [f"missing required root: {path.relative_to(REPO_ROOT)}" for path in missing]


def main() -> int:
    violations = []
    violations.extend(_check_required_roots())
    violations.extend(_check_python_boundaries())
    violations.extend(_check_markflow_package_boundaries())
    violations.extend(_check_frontend_boundaries())

    if violations:
        print("Service boundary violations detected:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("Service boundary checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
