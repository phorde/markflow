"""Unit tests for deterministic service boundary checker."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_service_boundaries.py"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _create_minimal_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "services" / "api" / "contracts" / "events" / "placeholder.txt", "ok")
    _write(repo / "services" / "api" / "contracts" / "http" / "placeholder.txt", "ok")
    _write(repo / "services" / "worker" / "contracts" / "events" / "placeholder.txt", "ok")
    _write(repo / "services" / "api" / "app.py", "from __future__ import annotations\n")
    _write(repo / "services" / "worker" / "app.py", "from __future__ import annotations\n")
    _write(repo / "services" / "frontend" / "index.ts", "export const ready = true;\n")
    _write(repo / "markflow" / "contracts" / "__init__.py", "")
    _write(repo / "markflow" / "web" / "__init__.py", "")
    return repo


def _run_checker(repo: Path) -> subprocess.CompletedProcess[str]:
    script_target = repo / "scripts" / "check_service_boundaries.py"
    script_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPT_PATH, script_target)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE", "PYTEST_ADDOPTS"))}
    return subprocess.run(
        [sys.executable, "-S", str(script_target)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.mark.unit
def test_boundary_checker_passes_on_minimal_valid_layout(tmp_path: Path) -> None:
    repo = _create_minimal_repo(tmp_path)

    result = _run_checker(repo)

    assert result.returncode == 0
    assert "Service boundary checks passed." in result.stdout


@pytest.mark.unit
def test_boundary_checker_flags_worker_importing_web_runtime(tmp_path: Path) -> None:
    repo = _create_minimal_repo(tmp_path)
    _write(
        repo / "services" / "worker" / "app.py",
        "from markflow.web.api import create_app\n",
    )

    result = _run_checker(repo)

    assert result.returncode == 1
    assert "imports forbidden module 'markflow.web.api'" in result.stdout


@pytest.mark.unit
def test_boundary_checker_flags_contracts_importing_web_layer(tmp_path: Path) -> None:
    repo = _create_minimal_repo(tmp_path)
    _write(
        repo / "markflow" / "contracts" / "broker.py",
        "from markflow.web.api import create_app\n",
    )

    result = _run_checker(repo)

    assert result.returncode == 1
    normalized = result.stdout.replace("\\", "/")
    assert "markflow/contracts/broker.py imports forbidden module 'markflow.web.api'" in normalized


@pytest.mark.unit
def test_boundary_checker_flags_legacy_wrapper_import(tmp_path: Path) -> None:
    repo = _create_minimal_repo(tmp_path)
    _write(
        repo / "markflow" / "contracts" / "broker.py",
        "from markflow.web.broker import RedisStreamsBroker\n",
    )

    result = _run_checker(repo)

    assert result.returncode == 1
    assert "imports legacy module 'markflow.web.broker'" in result.stdout


@pytest.mark.unit
def test_boundary_checker_flags_frontend_forbidden_service_import(tmp_path: Path) -> None:
    repo = _create_minimal_repo(tmp_path)
    _write(
        repo / "services" / "frontend" / "app" / "page.tsx",
        "import { createApp } from 'services/api/api';\n",
    )

    result = _run_checker(repo)

    assert result.returncode == 1
    assert "imports forbidden cross-service path 'services/api/api'" in result.stdout
