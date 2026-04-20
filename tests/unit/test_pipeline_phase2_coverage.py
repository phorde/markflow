from __future__ import annotations

import asyncio
import builtins
import sys
from types import SimpleNamespace

import pytest

from markflow.llm_types import DiscoveredModel, LlmCallResult, RoutingDecision
from markflow.pipeline import (
    PipelineConfig,
    _autotune_for_machine,
    _call_local_ocr,
    _call_strict_llm_review,
    _call_tesseract_local_ocr,
    _detect_total_ram_gb,
    _resolve_llm_client,
    _route_llm_model,
    get_env,
    get_required_env,
)

pytestmark = pytest.mark.unit


def test_env_loading_and_required_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("markflow.pipeline._ENV_LOADED", False)
    monkeypatch.delenv("MARKFLOW_TEST_ENV", raising=False)
    (tmp_path / ".env").write_text(
        "export MARKFLOW_TEST_ENV='loaded value'\nEMPTY=\n# comment\n",
        encoding="utf-8",
    )

    assert get_env("MARKFLOW_TEST_ENV") == "loaded value"
    assert get_required_env("MARKFLOW_TEST_ENV") == "loaded value"
    with pytest.raises(RuntimeError, match="Missing required environment variable"):
        get_required_env("MARKFLOW_MISSING_ENV")


def test_detect_total_ram_returns_zero_when_platform_detection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("no psutil")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr("markflow.pipeline.os.name", "posix")
    assert _detect_total_ram_gb() == 0.0


def test_autotune_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("markflow.pipeline.os.cpu_count", lambda: 16)
    monkeypatch.setattr("markflow.pipeline._detect_total_ram_gb", lambda: 32.0)

    text_cfg = _autotune_for_machine(PipelineConfig(concurrency=1))
    assert text_cfg.concurrency >= 8

    strict_cfg = _autotune_for_machine(PipelineConfig(medical_strict=True, concurrency=8))
    assert strict_cfg.concurrency == 2
    assert strict_cfg.zoom_matrix >= 1.8
    assert strict_cfg.ocr_grayscale is False

    fast_cfg = _autotune_for_machine(PipelineConfig(scanned_fast=True, zoom_matrix=2.0))
    assert fast_cfg.zoom_matrix <= 1.25
    assert fast_cfg.ocr_grayscale is True


def test_resolve_llm_client_disabled_missing_and_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    assert _resolve_llm_client(PipelineConfig(llm_enabled=False)) is None
    assert _resolve_llm_client(PipelineConfig(llm_enabled=True)) is None

    cfg = PipelineConfig(
        llm_api_key="secret",
        llm_base_url="https://api.example.com",
        llm_provider_preset="custom",
        llm_provider_name="Example",
    )
    client = _resolve_llm_client(cfg)
    assert client is not None
    assert client.base_url == "https://api.example.com"


def test_route_llm_model_uses_explicit_model(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = SimpleNamespace(base_url="https://x", provider_name="p")
    monkeypatch.setattr("markflow.pipeline._resolve_llm_client", lambda cfg: fake_client)

    cfg = PipelineConfig(llm_enabled=True, llm_model="fixed-model")
    client, decision, warnings = asyncio.run(
        _route_llm_model(
            session=object(),
            cfg=cfg,
            task_kind="remote_ocr",
            complexity="high",
            require_vision=True,
        )
    )
    assert client is fake_client
    assert warnings == []
    assert decision is not None
    assert decision.selected_model.id == "fixed-model"
    assert decision.selected_model.supports_vision is True


def test_call_strict_llm_review_returns_draft_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "markflow.pipeline._route_llm_model",
        lambda **kwargs: asyncio.sleep(0, result=(None, None, ["missing"])),
    )
    result = asyncio.run(
        _call_strict_llm_review(
            session=object(),
            cfg=PipelineConfig(),
            image_b64="",
            draft_text="draft",
            reason="test",
        )
    )
    assert result == "draft"


def test_call_strict_llm_review_handles_image_and_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = DiscoveredModel("m1", "m1", True, True)
    decision = RoutingDecision(
        task_kind="strict_review",
        complexity="high",
        selected_model=selected,
        fallback_models=[],
        debug_lines=[],
        selector_result=None,
    )

    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0
            self.seen_content = None

        async def chat_completion_async(self, **kwargs):
            self.calls += 1
            self.seen_content = kwargs["messages"][0]["content"]
            if self.calls == 1:
                raise RuntimeError("temporary")
            return LlmCallResult(text="```markdown\nreviewed\n```", model="m1", usage={})

    client = FakeClient()
    monkeypatch.setattr(
        "markflow.pipeline._route_llm_model",
        lambda **kwargs: asyncio.sleep(0, result=(client, decision, [])),
    )

    result = asyncio.run(
        _call_strict_llm_review(
            session=object(),
            cfg=PipelineConfig(qa_retries=2),
            image_b64="img",
            draft_text="draft",
            reason="test",
        )
    )
    assert result == "reviewed"
    assert client.calls == 2
    assert isinstance(client.seen_content, list)


def test_call_tesseract_local_ocr_uses_data_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pytesseract = SimpleNamespace()
    fake_pytesseract.Output = SimpleNamespace(DICT="dict")
    fake_pytesseract.pytesseract = SimpleNamespace(tesseract_cmd="")

    def image_to_data(*args, **kwargs):
        return {
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
            "conf": ["12"],
            "text": ["x"],
        }

    fake_pytesseract.image_to_data = image_to_data
    fake_pytesseract.image_to_string = lambda *args, **kwargs: "fallback text with more content"
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)
    monkeypatch.setattr("markflow.pipeline.get_env", lambda name, default="": "")

    text, confidence, warnings = _call_tesseract_local_ocr(
        image=object(),
        lang="por",
        psm=6,
    )
    assert "fallback text" in text
    assert confidence == 0.12
    assert "local_ocr_text_fallback" in warnings


def test_call_local_ocr_reports_all_provider_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "markflow.pipeline._prepare_local_ocr_image",
        lambda image_b64, cfg: ("image", object()),
    )
    monkeypatch.setattr(
        "markflow.pipeline._get_easyocr_reader",
        lambda key: (_ for _ in ()).throw(RuntimeError("easy")),
    )
    monkeypatch.setattr(
        "markflow.pipeline._get_rapidocr_reader",
        lambda: (_ for _ in ()).throw(RuntimeError("rapid")),
    )
    monkeypatch.setattr(
        "markflow.pipeline._call_tesseract_local_ocr",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("tess")),
    )

    with pytest.raises(RuntimeError, match="local_ocr_unavailable"):
        _call_local_ocr(
            image_b64="img",
            lang="pt,en",
            psm=6,
            engine="auto",
            cfg=PipelineConfig(),
        )
