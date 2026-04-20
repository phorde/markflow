from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pytest

from markflow import cli
from markflow.pipeline import DocumentProcessingResult, PipelineConfig

pytestmark = pytest.mark.unit


def _base_args(**overrides):
    data = dict(
        input=".",
        output_dir="out",
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
    data.update(overrides)
    return argparse.Namespace(**data)


def test_apply_mode_profiles() -> None:
    fast = cli.apply_mode_profile(_base_args(mode="fast"))
    assert fast.scanned_fast and fast.disable_visual_qa and fast.disable_nlp_review
    quality = cli.apply_mode_profile(_base_args(mode="quality"))
    assert quality.medical_strict and quality.routing_mode == "high-accuracy-ocr"
    local = cli.apply_mode_profile(_base_args(mode="local"))
    assert local.disable_llm and local.disable_strict_llm_required
    remote = cli.apply_mode_profile(_base_args(mode="remote"))
    assert remote.remote_first


def test_parse_args_reads_common_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "app.py",
            "--input",
            "./docs",
            "--output-dir",
            "./out",
            "--mode",
            "quality",
            "--routing-mode",
            "high-accuracy-ocr",
            "--allow-sensitive-cache",
        ],
    )
    args = cli.parse_args()
    assert args.input == "./docs"
    assert args.output_dir == "./out"
    assert args.mode == "quality"
    assert args.routing_mode == "high-accuracy-ocr"
    assert args.allow_sensitive_cache is True


def test_build_config_maps_allow_sensitive_cache() -> None:
    cfg = cli.build_config(_base_args(allow_sensitive_cache=True))
    assert isinstance(cfg, PipelineConfig)
    assert cfg.allow_sensitive_cache_persistence is True


def test_main_returns_1_when_discover_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "parse_args", lambda: _base_args())
    monkeypatch.setattr(cli, "discover_pdfs", lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    assert cli.main() == 1


def test_main_returns_0_when_no_pdfs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "parse_args", lambda: _base_args())
    monkeypatch.setattr(cli, "discover_pdfs", lambda _: [])
    assert cli.main() == 0


def test_main_returns_0_when_all_documents_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(cli, "parse_args", lambda: _base_args(input=str(pdf)))
    monkeypatch.setattr(cli, "discover_pdfs", lambda _: [pdf])
    monkeypatch.setattr(
        cli,
        "process_document",
        lambda *a, **k: DocumentProcessingResult(
            markdown_file=tmp_path / "out" / "a.canonical.md",
            report_file=tmp_path / "out" / "a.canonical.report.json",
            html_file=None,
            status="accepted",
            success=True,
            report={},
        ),
    )
    assert cli.main() == 0
