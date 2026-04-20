"""Typed contracts for extraction orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class DocumentResult:
    markdown_file: Path
    report_file: Path
    html_file: Optional[Path]
    status: str
    success: bool
    report: Dict[str, Any]
