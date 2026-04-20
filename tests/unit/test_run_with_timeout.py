from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run_with_timeout.py"


@pytest.mark.unit
def test_run_with_timeout_returns_child_exit_code() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "5",
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(7)",
        ],
        cwd=ROOT,
        check=False,
    )

    assert completed.returncode == 7


@pytest.mark.unit
def test_run_with_timeout_kills_timed_out_process() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "0.5",
            "--",
            sys.executable,
            "-c",
            "import time; time.sleep(10)",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 124
    assert "Command timed out after" in completed.stderr
