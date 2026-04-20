from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from markflow.llm_types import DiscoveredModel, RoutingDecision
from markflow.pipeline import PipelineConfig, _process_page, _route_llm_model

pytestmark = pytest.mark.unit


class _Progress:
    def __init__(self) -> None:
        self.count = 0

    def update(self, step: int) -> None:
        self.count += step


def test_route_llm_model_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = SimpleNamespace(base_url="https://x", provider_name="p")
    selected = DiscoveredModel(
        id="m1",
        normalized_id="m1",
        supports_chat=True,
        supports_vision=True,
    )
    fake_decision = RoutingDecision(
        task_kind="remote_ocr",
        complexity="high",
        selected_model=selected,
        fallback_models=[],
        debug_lines=[],
        selector_result=None,
    )

    route_calls = {"count": 0}

    class _Router:
        def route(self, **kwargs):
            route_calls["count"] += 1
            return fake_decision

    async def _fake_snapshot(session, cfg, client):
        return [selected], [], []

    monkeypatch.setattr("markflow.pipeline._resolve_llm_client", lambda cfg: fake_client)
    monkeypatch.setattr("markflow.pipeline._get_discovery_snapshot", _fake_snapshot)
    monkeypatch.setattr("markflow.pipeline.OcrAwareRouter", _Router)
    monkeypatch.setattr("markflow.pipeline._ROUTING_CACHE", {})

    cfg = PipelineConfig(llm_enabled=True)
    result1 = asyncio.run(
        _route_llm_model(
            session=object(),
            cfg=cfg,
            task_kind="remote_ocr",
            complexity="high",
            require_vision=True,
        )
    )
    result2 = asyncio.run(
        _route_llm_model(
            session=object(),
            cfg=cfg,
            task_kind="remote_ocr",
            complexity="high",
            require_vision=True,
        )
    )
    assert result1[1] is not None
    assert result2[1] is not None
    assert route_calls["count"] == 1


def test_process_page_uses_to_thread_for_render_and_local_ocr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = {"to_thread": 0}

    async def _fake_to_thread(func, *args, **kwargs):
        calls["to_thread"] += 1
        return func(*args, **kwargs)

    monkeypatch.setattr("markflow.pipeline.asyncio.to_thread", _fake_to_thread)
    monkeypatch.setattr("markflow.pipeline._page_has_usable_text_layer", lambda page, cfg: None)
    monkeypatch.setattr(
        "markflow.pipeline._get_rendered_page_image_b64", lambda **kwargs: "img-b64"
    )
    monkeypatch.setattr(
        "markflow.pipeline._call_local_ocr",
        lambda **kwargs: SimpleNamespace(
            text="ocr text", confidence=0.95, warnings=["local_ocr_provider"]
        ),
    )

    cfg = PipelineConfig(cache_enabled=False, enable_local_ocr=True, local_first=True)
    progress = _Progress()
    page = SimpleNamespace(number=0)
    result = asyncio.run(
        _process_page(
            session=object(),
            cfg=cfg,
            semaphore=asyncio.Semaphore(1),
            page=page,
            cache_dir=tmp_path,
            doc_fingerprint="fp",
            progress=progress,
        )
    )
    assert result.source == "local-ocr"
    assert progress.count == 1
    assert calls["to_thread"] >= 2
