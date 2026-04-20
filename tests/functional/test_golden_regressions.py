from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

from markflow.pipeline import PageResult, PipelineConfig, process_document

pytestmark = [pytest.mark.functional]


def _make_pdf(path: Path, text: str = "fixture") -> Path:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    return path


def test_golden_text_native_pdf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "text-native.pdf", "Paciente Maria\nGlicose 120")

    async def fake_process_page(
        session, cfg, semaphore, page, cache_dir, doc_fingerprint, progress
    ):
        return PageResult(
            page_index=page.number,
            text="# Laudo\n\nPaciente Maria\n\nGlicose: 120",
            source="text-layer",
            status="accepted",
            confidence=0.97,
            cache_hit=False,
            qa_applied=False,
            cleanup_applied=False,
            llm_review_applied=False,
            warnings=[],
            elapsed_seconds=0.01,
        )

    monkeypatch.setattr("markflow.pipeline._process_page", fake_process_page)
    result = process_document(pdf, tmp_path / "out", ".canonical.md", True, PipelineConfig())

    assert result.markdown_file.read_text(encoding="utf-8") == (
        "# Laudo\n\nPaciente Maria\n\nGlicose: 120"
    )
    report = json.loads(result.report_file.read_text(encoding="utf-8"))
    assert report["document_status"] == "accepted"
    assert report["summary"]["text_layer_pages"] == 1


def test_golden_table_pdf_preserves_structure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pdf = _make_pdf(tmp_path / "table.pdf", "Tabela")

    async def fake_process_page(
        session, cfg, semaphore, page, cache_dir, doc_fingerprint, progress
    ):
        return PageResult(
            page_index=page.number,
            text="| Exame | Resultado |\n|---|---|\n| Hemoglobina | 13.2 |",
            source="vision-ocr",
            status="accepted",
            confidence=0.93,
            cache_hit=False,
            qa_applied=True,
            cleanup_applied=False,
            llm_review_applied=False,
            warnings=[],
            elapsed_seconds=0.02,
        )

    monkeypatch.setattr("markflow.pipeline._process_page", fake_process_page)
    result = process_document(pdf, tmp_path / "out", ".canonical.md", True, PipelineConfig())
    markdown = result.markdown_file.read_text(encoding="utf-8")
    html = result.html_file.read_text(encoding="utf-8") if result.html_file else ""

    assert "| Hemoglobina | 13.2 |" in markdown
    assert "<table>" in html
    assert "<td>Hemoglobina</td>" in html


def test_golden_scanned_pdf_local_ocr_stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "scan.pdf", "scan placeholder")

    async def fake_process_page(
        session, cfg, semaphore, page, cache_dir, doc_fingerprint, progress
    ):
        return PageResult(
            page_index=page.number,
            text="Texto vindo de OCR local",
            source="local-ocr",
            status="accepted",
            confidence=0.91,
            cache_hit=False,
            qa_applied=False,
            cleanup_applied=False,
            llm_review_applied=False,
            warnings=["local_ocr_provider"],
            elapsed_seconds=0.03,
        )

    monkeypatch.setattr("markflow.pipeline._process_page", fake_process_page)
    result = process_document(pdf, tmp_path / "out", ".canonical.md", False, PipelineConfig())
    report = json.loads(result.report_file.read_text(encoding="utf-8"))
    assert result.success
    assert report["summary"]["local_ocr_pages"] == 1
    assert report["pages"][0]["warnings"] == ["local_ocr_provider"]


def test_golden_invalid_page_status_fails_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pdf = _make_pdf(tmp_path / "invalid.pdf", "bad page")

    async def fake_process_page(
        session, cfg, semaphore, page, cache_dir, doc_fingerprint, progress
    ):
        return PageResult(
            page_index=page.number,
            text="[Page 1 failed: invalid]",
            source="error",
            status="error",
            confidence=0.0,
            cache_hit=False,
            qa_applied=False,
            cleanup_applied=False,
            llm_review_applied=False,
            warnings=["page_failed:invalid"],
            elapsed_seconds=0.01,
        )

    monkeypatch.setattr("markflow.pipeline._process_page", fake_process_page)
    result = process_document(pdf, tmp_path / "out", ".canonical.md", False, PipelineConfig())
    report = json.loads(result.report_file.read_text(encoding="utf-8"))
    assert not result.success
    assert result.status == "error"
    assert report["summary"]["error_pages"] == 1


def test_golden_malicious_html_payload_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pdf = _make_pdf(tmp_path / "malicious.pdf", "payload")

    async def fake_process_page(
        session, cfg, semaphore, page, cache_dir, doc_fingerprint, progress
    ):
        return PageResult(
            page_index=page.number,
            text='[x](javascript:alert(1))\n\n<script>alert(1)</script>\n\n<img src=x onerror="x">',
            source="text-layer",
            status="accepted",
            confidence=0.95,
            cache_hit=False,
            qa_applied=False,
            cleanup_applied=False,
            llm_review_applied=False,
            warnings=[],
            elapsed_seconds=0.01,
        )

    monkeypatch.setattr("markflow.pipeline._process_page", fake_process_page)
    result = process_document(pdf, tmp_path / "out", ".canonical.md", True, PipelineConfig())
    html = result.html_file.read_text(encoding="utf-8") if result.html_file else ""
    assert "javascript:" not in html
    assert "<script>" not in html
    assert "onerror" not in html
