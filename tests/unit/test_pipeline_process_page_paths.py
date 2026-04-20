from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from markflow.pipeline import PageInspection, PipelineConfig, _process_page

pytestmark = pytest.mark.unit


class _Progress:
    def __init__(self) -> None:
        self.count = 0

    def update(self, step: int) -> None:
        self.count += step


def _run_process_page(cfg: PipelineConfig, page: object, cache_dir: Path):
    return asyncio.run(
        _process_page(
            session=object(),
            cfg=cfg,
            semaphore=asyncio.Semaphore(1),
            page=page,
            cache_dir=cache_dir,
            doc_fingerprint="fp",
            progress=_Progress(),
        )
    )


def test_process_page_text_layer_cache_hit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    inspection = PageInspection(
        page_index=0,
        source="text-layer",
        text="cached base text",
        text_chars=100,
        word_count=20,
        block_count=2,
        image_count=0,
        confidence=0.9,
        warnings=[],
    )
    monkeypatch.setattr(
        "markflow.pipeline._page_has_usable_text_layer", lambda page, cfg: inspection
    )
    monkeypatch.setattr(
        "markflow.pipeline._cache_path",
        lambda cache_dir, kind, page_index, payload: cache_dir / "cached.txt",
    )
    (tmp_path / "cached.txt").write_text("cached result", encoding="utf-8")
    cfg = PipelineConfig(cache_enabled=True, medical_strict=False)
    result = _run_process_page(cfg, SimpleNamespace(number=0), tmp_path)
    assert result.cache_hit
    assert result.source == "text-layer"
    assert "cached result" in result.text


def test_process_page_text_layer_with_review_and_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inspection = PageInspection(
        page_index=0,
        source="text-layer",
        text="base content",
        text_chars=120,
        word_count=22,
        block_count=3,
        image_count=1,
        confidence=0.8,
        warnings=[],
    )
    monkeypatch.setattr(
        "markflow.pipeline._page_has_usable_text_layer", lambda page, cfg: inspection
    )
    monkeypatch.setattr(
        "markflow.pipeline._cache_path",
        lambda cache_dir, kind, page_index, payload: cache_dir / "cache_out.txt",
    )
    monkeypatch.setattr(
        "markflow.pipeline._get_rendered_page_image_b64", lambda **kwargs: "rendered-b64"
    )
    monkeypatch.setattr(
        "markflow.pipeline._should_use_visual_qa",
        lambda confidence, warnings, source, cfg: True,
    )
    monkeypatch.setattr(
        "markflow.pipeline._call_gemini_visual_qa",
        lambda session, cfg, image_b64, text: asyncio.sleep(0, result="qa text"),
    )
    monkeypatch.setattr(
        "markflow.pipeline._should_use_cleanup",
        lambda confidence, warnings, source, cfg: True,
    )
    monkeypatch.setattr(
        "markflow.pipeline._call_openrouter_nlp",
        lambda session, cfg, text: asyncio.sleep(0, result="cleanup text"),
    )
    monkeypatch.setattr("markflow.pipeline._has_corruption_warning", lambda warnings: False)
    cfg = PipelineConfig(cache_enabled=True, medical_strict=False)
    result = _run_process_page(cfg, SimpleNamespace(number=0), tmp_path)
    assert not result.cache_hit
    assert result.qa_applied
    assert result.cleanup_applied
    assert result.text == "cleanup text"
    assert (tmp_path / "cache_out.txt").exists()


def test_process_page_remote_ocr_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "markflow.pipeline._page_has_usable_text_layer",
        lambda page, cfg: None,
    )
    monkeypatch.setattr("markflow.pipeline._get_rendered_page_image_b64", lambda **kwargs: "img")
    monkeypatch.setattr(
        "markflow.pipeline._call_zai_vision",
        lambda session, cfg, image_b64: asyncio.sleep(0, result="# remote text"),
    )
    monkeypatch.setattr(
        "markflow.pipeline._should_use_visual_qa",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "markflow.pipeline._should_use_cleanup",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr("markflow.pipeline._has_corruption_warning", lambda warnings: False)
    monkeypatch.setattr(
        "markflow.pipeline._route_llm_model",
        lambda **kwargs: asyncio.sleep(0, result=(None, None, ["w1"])),
    )
    cfg = PipelineConfig(
        cache_enabled=False,
        enable_local_ocr=False,
        local_first=False,
        llm_routing_debug=True,
    )
    result = _run_process_page(cfg, SimpleNamespace(number=0), tmp_path)
    assert result.source == "vision-ocr"
    assert result.status == "accepted"


def test_process_page_strict_mode_calls_enforcer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "markflow.pipeline._page_has_usable_text_layer",
        lambda page, cfg: None,
    )
    monkeypatch.setattr(
        "markflow.pipeline._get_rendered_page_image_b64",
        lambda **kwargs: "img",
    )
    monkeypatch.setattr(
        "markflow.pipeline._call_zai_vision",
        lambda session, cfg, image_b64: asyncio.sleep(0, result="short"),
    )
    monkeypatch.setattr(
        "markflow.pipeline._should_use_visual_qa",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "markflow.pipeline._should_use_cleanup",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr("markflow.pipeline._has_corruption_warning", lambda warnings: False)
    monkeypatch.setattr(
        "markflow.pipeline._score_markdown_confidence",
        lambda text, source, warnings: 0.1,
    )
    monkeypatch.setattr(
        "markflow.pipeline._enforce_medical_strict_review",
        lambda **kwargs: asyncio.sleep(
            0,
            result=("blocked", 0.1, ["x"], "needs_reprocess", True),
        ),
    )
    cfg = PipelineConfig(
        cache_enabled=False,
        enable_local_ocr=False,
        local_first=False,
        medical_strict=True,
        min_acceptable_confidence=0.88,
    )
    result = _run_process_page(cfg, SimpleNamespace(number=0), tmp_path)
    assert result.status == "needs_reprocess"
    assert result.llm_review_applied
