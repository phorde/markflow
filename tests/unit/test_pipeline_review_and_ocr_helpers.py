from __future__ import annotations

import asyncio

import numpy as np
import pytest

from markflow.llm_types import DiscoveredModel, LlmCallResult, RoutingDecision
from markflow.pipeline import (
    PipelineConfig,
    _call_gemini_visual_qa,
    _call_local_ocr,
    _call_openrouter_nlp,
    _call_zai_vision,
    _enforce_fail_closed_policy,
)

pytestmark = pytest.mark.unit


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def chat_completion_async(self, **kwargs):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return LlmCallResult(text=item, model=kwargs["model"], usage={})


def _decision(*models: str) -> RoutingDecision:
    selected = DiscoveredModel(models[0], models[0], True, True)
    fallback = [DiscoveredModel(mid, mid, True, True) for mid in models[1:]]
    return RoutingDecision(
        task_kind="x",
        complexity="high",
        selected_model=selected,
        fallback_models=fallback,
        debug_lines=[],
        selector_result=None,
    )


def test_enforce_fail_closed_policy_non_strict_passthrough() -> None:
    cfg = PipelineConfig(medical_strict=False)
    result = asyncio.run(
        _enforce_fail_closed_policy(
            session=object(),
            cfg=cfg,
            page_index=0,
            image_b64="",
            source="text-layer",
            baseline_text="ok",
            confidence=0.9,
            warnings=[],
        )
    )
    assert result[1] == "accepted"
    assert result[0] == "ok"


def test_enforce_fail_closed_policy_strict_without_llm_requirement() -> None:
    cfg = PipelineConfig(
        medical_strict=True, strict_llm_required=False, min_acceptable_confidence=0.88
    )
    result = asyncio.run(
        _enforce_fail_closed_policy(
            session=object(),
            cfg=cfg,
            page_index=0,
            image_b64="",
            source="text-layer",
            baseline_text="ok",
            confidence=0.2,
            warnings=["very_short_output"],
        )
    )
    assert result[1] == "needs_reprocess"
    assert "strict_llm_required_disabled" in result[3]


def test_call_zai_vision_uses_fallback_model(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient([RuntimeError("fail"), "```markdown\nok\n```"])
    monkeypatch.setattr(
        "markflow.pipeline._route_llm_model",
        lambda **kwargs: asyncio.sleep(0, result=(client, _decision("m1", "m2"), [])),
    )
    cfg = PipelineConfig(ocr_retries=1, llm_enabled=True)
    text = asyncio.run(_call_zai_vision(session=object(), cfg=cfg, image_b64="img"))
    assert text == "ok"
    assert client.calls == 2


def test_call_visual_qa_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    visual_client = _FakeClient(["qa output"])
    cleanup_client = _FakeClient(["nlp output"])
    monkeypatch.setattr(
        "markflow.pipeline._route_llm_model",
        lambda **kwargs: asyncio.sleep(
            0,
            result=(
                visual_client if kwargs["task_kind"] == "visual_qa" else cleanup_client,
                _decision("m1"),
                [],
            ),
        ),
    )
    cfg = PipelineConfig(qa_retries=1, cleanup_retries=1)
    qa = asyncio.run(
        _call_gemini_visual_qa(session=object(), cfg=cfg, image_b64="img", draft_text="x")
    )
    cleaned = asyncio.run(_call_openrouter_nlp(session=object(), cfg=cfg, text="x"))
    assert qa == "qa output"
    assert cleaned == "nlp output"


def test_call_local_ocr_easyocr_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "markflow.pipeline._prepare_local_ocr_image",
        lambda image_b64, cfg: ("image", np.zeros((2, 2, 3), dtype=np.uint8)),
    )

    class _Reader:
        def readtext(self, image_array, detail=1, paragraph=True):
            return [([[0, 0], [1, 1]], "texto", 0.95)]

    monkeypatch.setattr("markflow.pipeline._get_easyocr_reader", lambda key: _Reader())
    result = _call_local_ocr(
        image_b64="img",
        lang="pt,en",
        psm=6,
        engine="easyocr",
        cfg=PipelineConfig(),
    )
    assert result.engine == "easyocr"
    assert result.text == "texto"
    assert result.confidence == 0.95


def test_call_local_ocr_fallback_to_rapidocr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "markflow.pipeline._prepare_local_ocr_image",
        lambda image_b64, cfg: ("image", np.zeros((2, 2, 3), dtype=np.uint8)),
    )
    monkeypatch.setattr(
        "markflow.pipeline._get_easyocr_reader",
        lambda key: (_ for _ in ()).throw(RuntimeError("easy fail")),
    )

    class _Rapid:
        def __call__(self, image_array):
            return [[([[0, 0], [1, 1]], "rapido", 0.87)]]

    monkeypatch.setattr("markflow.pipeline._get_rapidocr_reader", lambda: _Rapid())
    result = _call_local_ocr(
        image_b64="img",
        lang="pt,en",
        psm=6,
        engine="auto",
        cfg=PipelineConfig(),
    )
    assert result.engine == "rapidocr"
    assert result.text == "rapido"
