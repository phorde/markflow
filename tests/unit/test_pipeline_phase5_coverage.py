from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from markflow.llm_types import BenchmarkSignal, DiscoveredModel, LlmCallResult, RoutingDecision
from markflow.pipeline import (
    LocalOcrResult,
    PageInspection,
    PipelineConfig,
    _DISCOVERY_CACHE,
    _ROUTING_CACHE,
    _call_gemini_visual_qa,
    _call_local_ocr,
    _call_openrouter_nlp,
    _call_zai_vision,
    _enforce_fail_closed_policy,
    _get_discovery_snapshot,
    _ocr_result_items_to_text,
    _process_page,
    _route_llm_model,
)

pytestmark = pytest.mark.unit


class _Progress:
    def __init__(self) -> None:
        self.count = 0

    def update(self, value: int) -> None:
        self.count += value


class _Client:
    def __init__(self, responses: list[object] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls = 0
        self.base_url = "https://provider.test"
        self.provider_name = "Provider"
        self.api_key = "secret"

    async def list_models_async(self, session: object) -> list[DiscoveredModel]:
        self.calls += 1
        return [DiscoveredModel("vision", "vision", True, True)]

    async def chat_completion_async(self, **kwargs: object) -> LlmCallResult:
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return LlmCallResult(text=str(item), model=str(kwargs["model"]), usage={})


def _decision(selected: str = "vision", *fallbacks: str) -> RoutingDecision:
    return RoutingDecision(
        task_kind="x",
        complexity="high",
        selected_model=DiscoveredModel(selected, selected, True, True),
        fallback_models=[DiscoveredModel(item, item, True, True) for item in fallbacks],
        debug_lines=["selected by test"],
        selector_result=None,
    )


def _run_page(cfg: PipelineConfig, page: object, cache_dir: Path):
    return asyncio.run(
        _process_page(
            session=object(),
            cfg=cfg,
            semaphore=asyncio.Semaphore(1),
            page=page,
            cache_dir=cache_dir,
            doc_fingerprint="doc",
            progress=_Progress(),
        )
    )


def test_discovery_and_route_cache_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    _DISCOVERY_CACHE.clear()
    _ROUTING_CACHE.clear()
    client = _Client()
    signal = BenchmarkSignal(
        source="s",
        model_name="vision",
        normalized_model_name="vision",
        ocr_score=0.9,
        structured_extraction_score=0.8,
        context_stability_score=0.7,
        confidence=1.0,
    )
    monkeypatch.setattr(
        "markflow.pipeline.collect_ocr_benchmark_signals",
        lambda timeout: ([signal], ["snapshot-warning"]),
    )
    cfg = PipelineConfig(llm_discovery_timeout_seconds=1)

    first = asyncio.run(_get_discovery_snapshot(object(), cfg, client))
    second = asyncio.run(_get_discovery_snapshot(object(), cfg, client))

    assert first == second
    assert client.calls == 1

    monkeypatch.setattr("markflow.pipeline._resolve_llm_client", lambda cfg: client)
    routed_first = asyncio.run(
        _route_llm_model(object(), cfg, "remote_ocr", "high", require_vision=True)
    )
    routed_second = asyncio.run(
        _route_llm_model(object(), cfg, "remote_ocr", "high", require_vision=True)
    )
    assert routed_first[1] is routed_second[1]
    assert routed_second[2] == ["snapshot-warning"]


def test_remote_ocr_empty_then_failure_includes_discovery_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(["", RuntimeError("down")])
    monkeypatch.setattr(
        "markflow.pipeline._route_llm_model",
        lambda **kwargs: asyncio.sleep(
            0,
            result=(client, _decision("m1"), ["missing-benchmark", "partial"]),
        ),
    )
    cfg = PipelineConfig(ocr_retries=2)

    with pytest.raises(RuntimeError, match="all_routed_models_failed:down"):
        asyncio.run(_call_zai_vision(object(), cfg, "image"))


def test_remote_ocr_unconfigured_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "markflow.pipeline._route_llm_model",
        lambda **kwargs: asyncio.sleep(0, result=(None, None, [])),
    )
    with pytest.raises(RuntimeError, match="remote_ocr_llm_unavailable"):
        asyncio.run(_call_zai_vision(object(), PipelineConfig(), "image"))


def test_visual_qa_and_cleanup_return_draft_after_retry_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visual_client = _Client([RuntimeError("v1"), RuntimeError("v2")])
    cleanup_client = _Client([RuntimeError("c1"), RuntimeError("c2")])

    def route(**kwargs: object):
        client = visual_client if kwargs["task_kind"] == "visual_qa" else cleanup_client
        return asyncio.sleep(0, result=(client, _decision("m1"), []))

    monkeypatch.setattr("markflow.pipeline._route_llm_model", route)
    cfg = PipelineConfig(qa_retries=2, cleanup_retries=2)
    assert asyncio.run(_call_gemini_visual_qa(object(), cfg, "img", "draft")) == "draft"
    assert asyncio.run(_call_openrouter_nlp(object(), cfg, "draft")) == "draft"


def test_llm_cleanup_helpers_return_input_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "markflow.pipeline._route_llm_model",
        lambda **kwargs: asyncio.sleep(0, result=(None, None, [])),
    )
    assert (
        asyncio.run(_call_gemini_visual_qa(object(), PipelineConfig(), "img", "draft")) == "draft"
    )
    assert asyncio.run(_call_openrouter_nlp(object(), PipelineConfig(), "draft")) == "draft"


def test_fail_closed_policy_two_pass_accepts_better_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            "Data 10/01/2024 valor 120 texto suficiente para primeira revisao",
            "Data 10/01/2024 valor 120 texto suficiente para segunda revisao com contexto",
        ]
    )
    monkeypatch.setattr(
        "markflow.pipeline._resolve_llm_client",
        lambda cfg: object(),
    )
    monkeypatch.setattr(
        "markflow.pipeline._call_strict_llm_review",
        lambda *args, **kwargs: asyncio.sleep(0, result=next(responses)),
    )
    cfg = PipelineConfig(
        medical_strict=True,
        strict_llm_required=True,
        llm_review_two_pass=True,
        min_acceptable_confidence=0.5,
    )
    result = asyncio.run(
        _enforce_fail_closed_policy(
            session=object(),
            cfg=cfg,
            page_index=0,
            image_b64="img",
            source="vision-ocr",
            baseline_text="Data 10/01/2024 valor 120",
            confidence=0.1,
            warnings=["very_short_output"],
        )
    )
    assert result[1] == "llm_review_passed"
    assert result[4] is True
    assert any(item.startswith("post_llm_confidence:") for item in result[3])


def test_ocr_item_reconstruction_edge_shapes() -> None:
    text, confidence = _ocr_result_items_to_text(
        [
            ("plain", "0.7"),
            ("text-only",),
            ([[object(), object()]], "bad-point", "bad-confidence"),
            ([], "", 0.9),
        ],
        fallback_join=" ",
    )
    assert "plain" in text
    assert "text-only" in text
    assert "bad-point" in text
    assert confidence == pytest.approx(0.7)
    assert _ocr_result_items_to_text([]) == ("", 0.0)
    assert _ocr_result_items_to_text([(object(),)]) == ("", 0.0)


def test_call_local_ocr_tesseract_and_short_easyocr_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "markflow.pipeline._prepare_local_ocr_image",
        lambda image_b64, cfg: ("image", np.zeros((2, 2, 3), dtype=np.uint8)),
    )
    monkeypatch.setattr(
        "markflow.pipeline._call_tesseract_local_ocr",
        lambda image, lang, psm: ("texto tesseract suficiente", 0.8, ["tess"]),
    )
    tesseract = _call_local_ocr("img", "pt", 6, "tesseract", PipelineConfig())
    assert tesseract.engine == "tesseract"

    class _Reader:
        def readtext(self, image_array: object, detail: int = 1, paragraph: bool = True):
            if paragraph:
                return [([[0, 0], [1, 1]], "curto", 0.1)]
            return [([[0, 0], [1, 1]], "fallback easyocr com conteudo maior", 0.9)]

    monkeypatch.setattr("markflow.pipeline._get_easyocr_reader", lambda key: _Reader())
    easy = _call_local_ocr("img", "pt", 6, "easyocr", PipelineConfig())
    assert easy.engine == "easyocr"
    assert "fallback easyocr" in easy.text
    assert "local_ocr_text_fallback" in easy.warnings


def test_process_page_local_cache_and_provider_failure_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("markflow.pipeline._page_has_usable_text_layer", lambda page, cfg: None)
    monkeypatch.setattr("markflow.pipeline._get_rendered_page_image_b64", lambda **kwargs: "img")
    monkeypatch.setattr(
        "markflow.pipeline._call_local_ocr",
        lambda *args, **kwargs: LocalOcrResult(
            "texto local com qualidade suficiente", "easy", 0.9, []
        ),
    )
    cfg = PipelineConfig(cache_enabled=True, enable_local_ocr=True, local_first=True)
    local_result = _run_page(cfg, SimpleNamespace(number=0), tmp_path)
    assert local_result.source == "local-ocr"
    assert not local_result.cache_hit

    cached = _run_page(cfg, SimpleNamespace(number=0), tmp_path)
    assert cached.cache_hit
    assert cached.source == "local-ocr"

    monkeypatch.setattr(
        "markflow.pipeline._call_local_ocr",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("local down")),
    )
    monkeypatch.setattr(
        "markflow.pipeline._call_zai_vision",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("remote down")),
    )
    error_result = _run_page(
        PipelineConfig(cache_enabled=False, enable_local_ocr=True, local_first=True),
        SimpleNamespace(number=2),
        tmp_path,
    )
    assert error_result.status == "error"
    assert "all_ocr_providers_failed" in error_result.text


def test_process_page_text_layer_corruption_repair_and_strict_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inspection = PageInspection(
        page_index=0,
        source="text-layer",
        text="A1B2C3 " * 50,
        text_chars=350,
        word_count=50,
        block_count=1,
        image_count=0,
        confidence=0.5,
        warnings=[],
    )
    monkeypatch.setattr(
        "markflow.pipeline._page_has_usable_text_layer", lambda page, cfg: inspection
    )
    monkeypatch.setattr("markflow.pipeline._get_rendered_page_image_b64", lambda **kwargs: "img")
    monkeypatch.setattr(
        "markflow.pipeline._call_strict_llm_review",
        lambda **kwargs: asyncio.sleep(0, result="texto reparado com conteudo suficiente"),
    )
    monkeypatch.setattr(
        "markflow.pipeline._enforce_medical_strict_review",
        lambda **kwargs: asyncio.sleep(
            0,
            result=("strict text", 0.9, ["strict"], "llm_review_passed", True),
        ),
    )
    cfg = PipelineConfig(cache_enabled=True, medical_strict=True, llm_enabled=True)
    result = _run_page(cfg, SimpleNamespace(number=0), tmp_path)
    assert result.llm_review_applied
    assert result.status in {"accepted", "llm_review_passed"}
