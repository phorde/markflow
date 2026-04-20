from __future__ import annotations

import argparse
import json
from pathlib import Path
import asyncio

import pytest

from markflow import cli
from markflow.pipeline import (
    DocumentProcessingResult,
    PageResult,
    PipelineConfig,
    process_document,
    run_pipeline,
)

pytestmark = pytest.mark.integration


def test_run_pipeline_disables_persistent_cache_in_medical_strict(
    monkeypatch: pytest.MonkeyPatch,
    sample_pdf: Path,
) -> None:
    async def fake_process_page(
        session, cfg, semaphore, page, cache_dir, doc_fingerprint, progress
    ):
        return PageResult(
            page_index=page.number,
            text="conteudo seguro",
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
    cfg = PipelineConfig(medical_strict=True, cache_enabled=True)
    markdown_text, report = asyncio.run(run_pipeline(sample_pdf, cfg))
    assert "conteudo seguro" in markdown_text
    assert report["summary"]["cache_enabled_requested"] is True
    assert report["summary"]["cache_enabled_effective"] is False
    assert report["document_status"] == "accepted"
    assert not (sample_pdf.parent / ".cache" / sample_pdf.stem).exists()


def test_process_document_writes_outputs_and_warns_on_failed_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sample_pdf: Path,
) -> None:
    fake_report = {
        "document": sample_pdf.name,
        "summary": {
            "error_pages": 1,
            "needs_reprocess_pages": 0,
            "llm_review_required_pages": 0,
        },
    }

    async def fake_run_pipeline(pdf_file, cfg):
        return "# report", fake_report

    monkeypatch.setattr("markflow.pipeline.run_pipeline", fake_run_pipeline)
    result = process_document(sample_pdf, tmp_path, ".canonical.md", True, PipelineConfig())
    assert not result.success
    assert result.status == "error"
    assert result.markdown_file.exists()
    assert result.report_file.exists()
    assert result.html_file is not None and result.html_file.exists()


def test_cli_main_counts_document_status_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sample_pdf: Path,
) -> None:
    args = argparse.Namespace(
        input=str(sample_pdf),
        output_dir=str(tmp_path / "out"),
        suffix=".canonical.md",
        html=False,
        concurrency=4,
        timeout=240,
        zoom=1.5,
        max_image_side=1700,
        rgb_ocr=False,
        scanned_fast=False,
        ocr_retries=2,
        qa_retries=1,
        cleanup_retries=1,
        text_min_chars=40,
        qa_confidence_threshold=0.82,
        cleanup_confidence_threshold=0.68,
        min_acceptable_confidence=0.88,
        remote_first=False,
        disable_local_ocr=False,
        local_ocr_lang="pt,en",
        local_ocr_engine="easyocr",
        local_min_confidence=0.84,
        local_ocr_psm=6,
        disable_ocr_preprocess=False,
        no_autocontrast=False,
        no_sharpen=False,
        ocr_binarize_threshold=0,
        disable_render_cache=False,
        medical_strict=False,
        strict_recovery_attempts=1,
        allow_single_pass_llm_review=False,
        disable_strict_llm_required=False,
        no_text_layer=False,
        disable_visual_qa=False,
        disable_nlp_review=False,
        disable_cache=False,
        allow_sensitive_cache=False,
        cache_schema_version=1,
        cache_ttl_seconds=0,
        no_autotune_local=True,
        llm_base_url="",
        llm_provider_preset="custom",
        zai_plan="general",
        llm_provider_name="",
        llm_model="",
        routing_mode="balanced",
        routing_debug=False,
        llm_discovery_timeout=8,
        disable_llm=True,
        mode="auto",
        tui=False,
    )

    monkeypatch.setattr(cli, "parse_args", lambda: args)
    monkeypatch.setattr(cli, "discover_pdfs", lambda _: [sample_pdf])
    monkeypatch.setattr(
        cli,
        "process_document",
        lambda *a, **k: DocumentProcessingResult(
            markdown_file=tmp_path / "out" / "sample.canonical.md",
            report_file=tmp_path / "out" / "sample.canonical.report.json",
            html_file=None,
            status="error",
            success=False,
            report={},
        ),
    )
    exit_code = cli.main()
    assert exit_code == 2


def test_process_document_report_is_json_serializable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sample_pdf: Path,
) -> None:
    async def fake_run_pipeline(pdf_file, cfg):
        return "# md", {
            "document": sample_pdf.name,
            "summary": {
                "error_pages": 0,
                "needs_reprocess_pages": 0,
                "llm_review_required_pages": 0,
            },
        }

    monkeypatch.setattr("markflow.pipeline.run_pipeline", fake_run_pipeline)
    result = process_document(sample_pdf, tmp_path, ".canonical.md", False, PipelineConfig())
    report_payload = json.loads(result.report_file.read_text(encoding="utf-8"))
    assert report_payload["document"] == sample_pdf.name
