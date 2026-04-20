from __future__ import annotations

from pathlib import Path
import sys

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello MarkFlow\nLine 2\n12345")
    doc.save(pdf_path)
    doc.close()
    return pdf_path
