from __future__ import annotations

from pathlib import Path

import pytest

from markflow.pipeline import PageResult, PipelineConfig, process_document

pytestmark = [pytest.mark.functional]


def test_end_to_end_text_pdf_generates_markdown_and_report(
    monkeypatch: pytest.MonkeyPatch,
    sample_pdf: Path,
    tmp_path: Path,
) -> None:
    async def fake_process_page(
        session, cfg, semaphore, page, cache_dir, doc_fingerprint, progress
    ):
        return PageResult(
            page_index=page.number,
            text="# Documento\n\nConteudo extraido",
            source="text-layer",
            status="accepted",
            confidence=0.98,
            cache_hit=False,
            qa_applied=False,
            cleanup_applied=False,
            llm_review_applied=False,
            warnings=[],
            elapsed_seconds=0.01,
        )

    monkeypatch.setattr("markflow.pipeline._process_page", fake_process_page)
    result = process_document(sample_pdf, tmp_path, ".canonical.md", True, PipelineConfig())
    assert result.success
    assert "# Documento" in result.markdown_file.read_text(encoding="utf-8")
    assert "document_status" in result.report_file.read_text(encoding="utf-8")
    assert result.html_file is not None
    html = result.html_file.read_text(encoding="utf-8")
    assert "<h1>Documento</h1>" in html
