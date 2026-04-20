from __future__ import annotations

from pathlib import Path
import re
import sys
from uuid import uuid4

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    """Workspace-backed tmp_path replacement for Windows tempfile ACL issues."""
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid)
    path = ROOT / "test-work" / f"{safe_name}-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello MarkFlow\nLine 2\n12345")
    doc.save(pdf_path)
    doc.close()
    return pdf_path
