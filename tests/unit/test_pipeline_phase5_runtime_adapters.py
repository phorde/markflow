from __future__ import annotations

import asyncio
import base64
import builtins
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from markflow import pipeline
from markflow.extraction.local_ocr import normalize_local_ocr_language_token
from markflow.extraction.page_analysis import looks_like_atomic_markdown_line, page_text_layer
from markflow.extraction.rendering import preprocess_ocr_image
from markflow.pipeline import PageResult, PipelineConfig

pytestmark = pytest.mark.unit


def test_dotenv_fallback_parser_without_python_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):
        if name == "dotenv":
            raise ImportError("blocked")
        return original_import(name, *args, **kwargs)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(pipeline, "_ENV_LOADED", False)
    monkeypatch.delenv("FALLBACK_ENV", raising=False)
    monkeypatch.delenv("EMPTY_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "\n# comment\nexport FALLBACK_ENV=\"value\"\nNO_EQUALS\n='bad'\nEMPTY_KEY=\n",
        encoding="utf-8",
    )

    assert pipeline.get_env("FALLBACK_ENV") == "value"
    assert pipeline.get_env("EMPTY_KEY") == ""


def test_detect_ram_psutil_success_and_low_ram_autotune(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_psutil = SimpleNamespace(
        virtual_memory=lambda: SimpleNamespace(total=8 * 1024 * 1024 * 1024)
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    assert pipeline._detect_total_ram_gb() == 8.0

    monkeypatch.setattr(pipeline, "_detect_total_ram_gb", lambda: 8.0)
    cfg = pipeline._autotune_for_machine(PipelineConfig(max_image_side_px=3000))
    assert cfg.max_image_side_px == 1400

    monkeypatch.setattr(pipeline, "_detect_total_ram_gb", lambda: 8.0)
    strict = pipeline._autotune_for_machine(
        PipelineConfig(medical_strict=True, strict_recovery_attempts=3)
    )
    assert strict.strict_recovery_attempts == 1


def test_pipeline_compatibility_wrappers_and_discover_quotes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "quoted.pdf"
    pdf.write_bytes(b"%PDF")
    assert pipeline.discover_pdfs(f'"{pdf}"') == [pdf]

    class _Page:
        number = 3

        def get_text(self, mode: str):
            if mode == "text":
                return "um dois tres quatro cinco seis"
            if mode == "blocks":
                return []
            return ""

        def get_images(self, full: bool = True):
            return []

    assert looks_like_atomic_markdown_line("# title")
    assert page_text_layer(_Page())[2] == 6
    assert pipeline._page_has_usable_text_layer(_Page(), PipelineConfig(text_min_chars=999)) is None
    assert (
        pipeline._page_has_usable_text_layer(_Page(), PipelineConfig(text_min_chars=1)).page_index
        == 3
    )
    assert (
        preprocess_ocr_image(
            b"raw", enable_preprocess=False, autocontrast=False, sharpen=False, binarize_threshold=0
        )
        == b"raw"
    )
    assert normalize_local_ocr_language_token("por") == "pt"


def test_prepare_local_ocr_image_and_reader_factories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import Image

    image = Image.new("RGB", (2, 2), color="white")
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    payload = base64.b64encode(buf.getvalue()).decode()

    pil_image, array = pipeline._prepare_local_ocr_image(payload, PipelineConfig())
    assert pil_image.mode == "RGB"
    assert array.shape[0] == 2

    class _Reader:
        def __init__(self, languages: list[str], gpu: bool, verbose: bool) -> None:
            self.languages = languages
            self.gpu = gpu
            self.verbose = verbose

    class _Rapid:
        pass

    monkeypatch.setitem(sys.modules, "easyocr", SimpleNamespace(Reader=_Reader))
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", SimpleNamespace(RapidOCR=_Rapid))
    pipeline._get_easyocr_reader.cache_clear()
    pipeline._get_rapidocr_reader.cache_clear()

    reader = pipeline._get_easyocr_reader("pt+en")
    assert reader.languages == ["pt", "en"]
    assert isinstance(pipeline._get_rapidocr_reader(), _Rapid)


def test_tesseract_command_multiline_and_non_numeric_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pytesseract = SimpleNamespace()
    fake_pytesseract.Output = SimpleNamespace(DICT="dict")
    fake_pytesseract.pytesseract = SimpleNamespace(tesseract_cmd="")
    fake_pytesseract.image_to_data = lambda *args, **kwargs: {
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 2, 2],
        "conf": ["90", "bad", "95"],
        "text": ["linha1", "", "linha2"],
    }
    fake_pytesseract.image_to_string = lambda *args, **kwargs: "short"
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)
    monkeypatch.setattr(pipeline, "get_env", lambda name, default="": "cmd.exe")

    text, confidence, warnings = pipeline._call_tesseract_local_ocr(object(), "por", 99)

    assert "linha1" in text
    assert "linha2" in text
    assert confidence == pytest.approx(0.925)
    assert fake_pytesseract.pytesseract.tesseract_cmd == "cmd.exe"
    assert "local_ocr_text_fallback" not in warnings


def test_strict_review_no_image_empty_and_final_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = pipeline.DiscoveredModel("m", "m", True, False)
    decision = pipeline.RoutingDecision(
        task_kind="strict",
        complexity="high",
        selected_model=selected,
        fallback_models=[],
        debug_lines=[],
        selector_result=None,
    )

    class EmptyClient:
        async def chat_completion_async(self, **kwargs: object) -> pipeline.LlmCallResult:
            assert isinstance(kwargs["messages"][0]["content"], str)
            return pipeline.LlmCallResult(text="", model="m", usage={})

    monkeypatch.setattr(
        pipeline,
        "_route_llm_model",
        lambda **kwargs: asyncio.sleep(0, result=(EmptyClient(), decision, [])),
    )
    assert (
        asyncio.run(
            pipeline._call_strict_llm_review(
                object(), PipelineConfig(qa_retries=1), "", "draft", "reason"
            )
        )
        == "draft"
    )

    class FailingClient:
        async def chat_completion_async(self, **kwargs: object) -> pipeline.LlmCallResult:
            raise RuntimeError("fail")

    monkeypatch.setattr(
        pipeline,
        "_route_llm_model",
        lambda **kwargs: asyncio.sleep(0, result=(FailingClient(), decision, [])),
    )
    assert (
        asyncio.run(
            pipeline._call_strict_llm_review(
                object(), PipelineConfig(qa_retries=1), "", "draft", "reason"
            )
        )
        == "draft"
    )


def test_ocr_result_items_unhandled_tuple_branches() -> None:
    text, confidence = pipeline._ocr_result_items_to_text(
        [
            ([object()], "bad", "0.5"),
            ("bad-confidence", object()),
            (1, 2),
            object(),
            (["bad-point"], "pointless", 0.9),
        ]
    )
    assert "bad" in text
    assert "bad-confidence" in text
    assert "pointless" in text
    assert confidence == pytest.approx(0.7)


def test_render_page_image_and_cache_with_fake_fitz(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _Matrix:
        def __init__(self, x: float, y: float) -> None:
            self.x = x
            self.y = y

    class _Pixmap:
        def tobytes(self, fmt: str) -> bytes:
            assert fmt == "jpeg"
            return b"jpeg-bytes"

    class _Page:
        rect = SimpleNamespace(width=1000, height=500)

        def get_pixmap(self, **kwargs: object) -> _Pixmap:
            return _Pixmap()

    fake_fitz = SimpleNamespace(Matrix=_Matrix, csGRAY="gray", csRGB="rgb")
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

    rendered = pipeline._render_page_image_b64(_Page(), 2.0, 100, grayscale=True)
    assert base64.b64decode(rendered) == b"jpeg-bytes"

    cached = pipeline._get_rendered_page_image_b64(
        page=_Page(),
        cache_dir=tmp_path,
        page_index=0,
        doc_fingerprint="doc",
        zoom_matrix=1.0,
        max_image_side_px=100,
        grayscale=True,
        cache_enabled=True,
        preprocess_enabled=False,
        autocontrast=False,
        sharpen=False,
        binarize_threshold=0,
    )
    assert cached == rendered
    assert (
        pipeline._get_rendered_page_image_b64(
            page=_Page(),
            cache_dir=tmp_path,
            page_index=0,
            doc_fingerprint="doc",
            zoom_matrix=1.0,
            max_image_side_px=100,
            grayscale=True,
            cache_enabled=True,
            preprocess_enabled=False,
            autocontrast=False,
            sharpen=False,
            binarize_threshold=0,
        )
        == rendered
    )


def test_process_document_writes_outputs_and_windows_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    out = tmp_path / "out"
    policy_calls: list[object] = []

    monkeypatch.setattr(pipeline, "platform_is_windows", lambda: True)
    monkeypatch.setattr(asyncio, "WindowsSelectorEventLoopPolicy", lambda: "policy", raising=False)
    monkeypatch.setattr(
        asyncio, "set_event_loop_policy", lambda policy: policy_calls.append(policy)
    )
    monkeypatch.setattr(
        pipeline,
        "run_pipeline",
        lambda pdf_file, cfg: asyncio.sleep(
            0,
            result=("# Title", {"summary": {"error_pages": 0}, "document_status": "accepted"}),
        ),
    )

    result = pipeline.process_document(pdf, out, ".canonical.md", True, PipelineConfig())

    assert result.success
    assert result.html_file is not None
    assert result.markdown_file.exists()
    assert result.report_file.exists()
    assert policy_calls == ["policy"]


def test_run_pipeline_with_fake_runtime_modules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")

    class _Doc:
        def __init__(self) -> None:
            self.closed = False

        def __len__(self) -> int:
            return 2

        def __getitem__(self, index: int) -> SimpleNamespace:
            return SimpleNamespace(number=index)

        def close(self) -> None:
            self.closed = True

    doc = _Doc()

    class _ClientSession:
        def __init__(self, timeout: object) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "_ClientSession":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class _Progress:
        def __init__(self, total: int, ncols: int, desc: str) -> None:
            self.total = total
            self.closed = False

        def close(self) -> None:
            self.closed = True

    async def fake_process_page(
        session: object,
        cfg: PipelineConfig,
        semaphore: asyncio.Semaphore,
        page: SimpleNamespace,
        cache_dir: Path,
        doc_fingerprint: str,
        progress: object,
    ) -> PageResult:
        return PageResult(
            page_index=page.number,
            text=f"page-{page.number}",
            source="text-layer" if page.number == 0 else "local-ocr",
            status="accepted",
            confidence=0.9,
            cache_hit=False,
            qa_applied=False,
            cleanup_applied=False,
            llm_review_applied=False,
            warnings=[],
            elapsed_seconds=0.1,
        )

    monkeypatch.setitem(sys.modules, "fitz", SimpleNamespace(open=lambda path: doc))
    monkeypatch.setitem(
        sys.modules,
        "aiohttp",
        SimpleNamespace(
            ClientTimeout=lambda total: ("timeout", total), ClientSession=_ClientSession
        ),
    )
    monkeypatch.setitem(sys.modules, "tqdm.asyncio", SimpleNamespace(tqdm=_Progress))
    monkeypatch.setattr(pipeline, "_process_page", fake_process_page)

    markdown, report = asyncio.run(
        pipeline.run_pipeline(
            pdf,
            PipelineConfig(scanned_fast=True, cache_enabled=True, concurrency=5),
        )
    )

    assert "page-0" in markdown
    assert report["summary"]["pages"] == 2
    assert report["summary"]["local_ocr_pages"] == 1
    assert report["summary"]["cache_enabled_effective"] is True
    assert report["document_status"] == "accepted"
    assert doc.closed
