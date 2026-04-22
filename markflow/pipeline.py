"""Core extraction pipeline implementation.

This module contains reusable processing logic for:
- PDF text-layer extraction
- Local and remote OCR fallback
- Optional quality-review passes
- Structured markdown/report generation
"""

import asyncio
import base64
import io
import hashlib
import json
import ctypes
import os
import time
import warnings
from functools import lru_cache
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import numpy as np

from .benchmark_ingestion import collect_ocr_benchmark_signals
from .extraction.cache import (
    is_cache_entry_valid,
    page_cache_path,
    render_profile_payload,
    rendered_cache_path,
)
from .extraction.local_ocr import (
    easyocr_language_list,
    local_ocr_language_tokens,
    normalize_ocr_confidence,
    score_local_ocr_confidence,
    tesseract_language,
)
from .extraction.orchestrator import iter_chunk_bounds, resolve_effective_cache_enabled
from .extraction.page_analysis import (
    clean_markdown,
    normalize_markdown_document,
    word_count,
    inspect_text_layer,
)
from .extraction.rendering import (
    preprocess_ocr_image,
    render_html_document,
)
from .extraction.reporting import (
    add_summary_observability,
    derive_document_status,
    document_success,
)
from .extraction.review import (
    has_corruption_warning,
    has_severe_structure_warning,
    medical_validation_warnings,
    needs_reprocess_block,
    score_markdown_confidence,
    should_use_cleanup,
    should_use_visual_qa,
    validate_markdown_text,
)
from .extraction.types import DocumentResult
from .llm_client import OpenAICompatibleClient
from .llm_types import BenchmarkSignal, DiscoveredModel, RoutingDecision
from .provider_presets import (
    apply_provider_preset,
    get_provider_api_key_env_var,
    get_provider_preset,
)
from .routing import OcrAwareRouter, classify_complexity, classify_task_kind

_ENV_LOADED = False


def _load_dotenv_if_present() -> None:
    """Load environment variables from a local .env file once per process.

    The function first attempts to use python-dotenv when available and falls
    back to a minimal parser for simple KEY=VALUE lines.
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    env_file = Path(".env")
    if not env_file.exists():
        return

    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]
    except ImportError:
        pass
    else:
        load_dotenv(dotenv_path=env_file, override=False)
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if key not in os.environ:  # pragma: no branch - false branch is environment-state only
            os.environ[key] = value


def get_env(name: str, default: str = "") -> str:
    """Return an environment variable value after lazy dotenv loading.

    Args:
        name: Environment variable key.
        default: Value returned when key is missing.

    Returns:
        The configured value or the provided default.
    """
    _load_dotenv_if_present()
    return os.getenv(name, default)


def get_required_env(name: str) -> str:
    """Return a required environment variable or raise a configuration error.

    Args:
        name: Environment variable key.

    Returns:
        The non-empty variable value.

    Raises:
        RuntimeError: If variable is missing or blank.
    """
    value = get_env(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Configure it in .env (see .env.example)."
        )
    return value


def _detect_total_ram_gb() -> float:
    """Detect total physical memory in gigabytes.

    Returns:
        Total RAM in GB when detection succeeds, otherwise 0.0.
    """
    # Try psutil first if available.
    psutil_total_bytes: float | None = None
    try:
        import psutil  # type: ignore[import-not-found]

        psutil_total_bytes = float(psutil.virtual_memory().total)
    except Exception:
        psutil_total_bytes = None

    if psutil_total_bytes is not None:
        return round(psutil_total_bytes / (1024**3), 2)

    # Windows fallback without external dependencies.
    if os.name == "nt":  # pragma: no cover - platform-specific fallback; psutil path is primary

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        windll = getattr(ctypes, "windll", None)
        if windll is not None and windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return round(float(stat.ullTotalPhys) / (1024**3), 2)

    return 0.0


def _autotune_for_machine(cfg: "PipelineConfig") -> "PipelineConfig":
    """Adjust pipeline configuration for host resources and selected mode.

    Args:
        cfg: Base configuration to tune.

    Returns:
        Tuned configuration instance.
    """
    logical_cpus = max(1, os.cpu_count() or 1)
    ram_gb = _detect_total_ram_gb()

    tuned = cfg

    # Text-layer path is CPU-local and can exploit higher concurrency.
    if tuned.prefer_text_layer and not tuned.scanned_fast and not tuned.medical_strict:
        target = min(max(4, logical_cpus // 2), 14)
        tuned.concurrency = max(tuned.concurrency, target)

    # OCR API path benefits from controlled concurrency to avoid remote throttling.
    if not tuned.prefer_text_layer or tuned.scanned_fast:
        tuned.concurrency = min(tuned.concurrency, max(2, logical_cpus // 6))

    # Medical strict mode should prioritize quality and stable completion.
    if tuned.medical_strict:
        tuned.concurrency = min(tuned.concurrency, 2)
        tuned.zoom_matrix = max(tuned.zoom_matrix, 1.8)
        tuned.max_image_side_px = max(tuned.max_image_side_px, 2200)
        tuned.ocr_grayscale = False
        if ram_gb >= 24 and logical_cpus >= 12:
            tuned.strict_recovery_attempts = max(tuned.strict_recovery_attempts, 1)
        else:
            tuned.strict_recovery_attempts = min(tuned.strict_recovery_attempts, 1)

    # Throughput mode for scanned docs: keep payload moderate.
    if tuned.scanned_fast and not tuned.medical_strict:
        tuned.zoom_matrix = min(tuned.zoom_matrix, 1.25)
        tuned.max_image_side_px = min(tuned.max_image_side_px, 1600)
        tuned.ocr_grayscale = True
        tuned.enable_ocr_preprocess = True
        tuned.ocr_autocontrast = True
        tuned.ocr_sharpen = True

    # If RAM is constrained, reduce image payload to prevent pressure.
    if 0.0 < ram_gb < 12.0:
        tuned.max_image_side_px = min(tuned.max_image_side_px, 1400)

    return tuned


@dataclass
class PipelineConfig:
    concurrency: int = 4
    ocr_retries: int = 2
    qa_retries: int = 1
    cleanup_retries: int = 1
    timeout_seconds: int = 240
    zoom_matrix: float = 1.5
    max_image_side_px: int = 1700
    ocr_grayscale: bool = True
    scanned_fast: bool = False
    prefer_text_layer: bool = True
    text_min_chars: int = 40
    qa_confidence_threshold: float = 0.82
    cleanup_confidence_threshold: float = 0.68
    min_acceptable_confidence: float = 0.88
    local_first: bool = True
    enable_local_ocr: bool = True
    local_ocr_engine: str = "easyocr"
    local_ocr_lang: str = "pt,en"
    local_min_confidence: float = 0.84
    local_ocr_psm: int = 6
    enable_ocr_preprocess: bool = True
    ocr_autocontrast: bool = True
    ocr_sharpen: bool = True
    ocr_binarize_threshold: int = 0
    cache_rendered_images: bool = True
    medical_strict: bool = False
    strict_recovery_attempts: int = 1
    strict_llm_required: bool = True
    llm_review_two_pass: bool = True
    enable_visual_qa: bool = True
    enable_nlp_review: bool = True
    cache_enabled: bool = True
    allow_sensitive_cache_persistence: bool = False
    cache_schema_version: int = 1
    cache_ttl_seconds: int = 0
    llm_enabled: bool = True
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_provider_preset: str = "custom"
    llm_zai_plan: str = "general"
    llm_provider_name: str = ""
    llm_model: str = ""
    llm_routing_mode: str = "balanced"
    llm_routing_debug: bool = False
    llm_discovery_timeout_seconds: int = 8


@dataclass
class PageInspection:
    page_index: int
    source: str
    text: str
    text_chars: int
    word_count: int
    block_count: int
    image_count: int
    confidence: float
    warnings: List[str]


@dataclass
class PageResult:
    page_index: int
    text: str
    source: str
    status: str
    confidence: float
    cache_hit: bool
    qa_applied: bool
    cleanup_applied: bool
    llm_review_applied: bool
    warnings: List[str]
    elapsed_seconds: float


@dataclass
class LocalOcrResult:
    text: str
    engine: str
    confidence: float
    warnings: List[str]


DocumentProcessingResult = DocumentResult


def discover_pdfs(input_value: str) -> List[Path]:
    """Resolve PDF files from a direct file path or a directory.

    Args:
        input_value: Path to a PDF file or folder with PDFs.

    Returns:
        Sorted list of matching PDF paths.

    Raises:
        FileNotFoundError: If path is invalid or does not point to PDFs.
    """
    raw = (input_value or "").strip()
    if len(raw) >= 2 and ((raw[0] == '"' and raw[-1] == '"') or (raw[0] == "'" and raw[-1] == "'")):
        raw = raw[1:-1].strip()

    source = Path(raw).expanduser()
    if source.is_file() and source.suffix.lower() == ".pdf":
        return [source]
    if source.is_dir():
        return sorted([p for p in source.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])
    raise FileNotFoundError(f"Input path does not exist or is not a PDF: {raw}")


def _clean_markdown(text: str) -> str:
    """Backward-compatible wrapper around extraction.page_analysis.clean_markdown."""
    return clean_markdown(text)


def _normalize_markdown_document(text: str) -> str:
    """Backward-compatible wrapper around extraction.page_analysis."""
    return normalize_markdown_document(text)


def _word_count(text: str) -> int:
    """Backward-compatible wrapper around extraction.page_analysis."""
    return word_count(text)


def _page_has_usable_text_layer(page: Any, cfg: PipelineConfig) -> Optional[PageInspection]:
    """Return text-layer inspection when page content is sufficiently rich."""
    payload = inspect_text_layer(page, cfg.text_min_chars)
    if payload is None:
        return None
    return PageInspection(
        page_index=int(payload["page_index"]),
        source=str(payload["source"]),
        text=str(payload["text"]),
        text_chars=int(payload["text_chars"]),
        word_count=int(payload["word_count"]),
        block_count=int(payload["block_count"]),
        image_count=int(payload["image_count"]),
        confidence=float(payload["confidence"]),
        warnings=[str(item) for item in payload.get("warnings", [])],
    )


def _page_signature(kind: str, payload: str, page_index: int) -> str:
    """Generate deterministic SHA256 signature for cache key material."""
    digest = hashlib.sha256(f"{kind}:{page_index}:{payload}".encode("utf-8")).hexdigest()
    return digest


def _cache_path(cache_dir: Path, kind: str, page_index: int, payload: str) -> Path:
    """Build a page-level text cache file path for OCR/text outputs."""
    digest = _page_signature(kind, payload, page_index)
    return page_cache_path(cache_dir, kind, page_index, digest)


def _render_cache_path(cache_dir: Path, page_index: int, payload: str) -> Path:
    """Build a page-level rendered-image cache path."""
    digest = _page_signature("render", payload, page_index)
    return rendered_cache_path(cache_dir, page_index, digest)


def _render_profile_payload(
    doc_fingerprint: str,
    zoom_matrix: float,
    max_image_side_px: int,
    grayscale: bool,
    preprocess_enabled: bool,
    autocontrast: bool,
    sharpen: bool,
    binarize_threshold: int,
    schema_version: int = 1,
) -> str:
    """Serialize render profile parameters into a cache payload string."""
    return render_profile_payload(
        doc_fingerprint=doc_fingerprint,
        zoom_matrix=zoom_matrix,
        max_image_side_px=max_image_side_px,
        grayscale=grayscale,
        preprocess_enabled=preprocess_enabled,
        autocontrast=autocontrast,
        sharpen=sharpen,
        binarize_threshold=binarize_threshold,
        schema_version=schema_version,
    )


def _normalize_ocr_confidence(raw_confidence: Any) -> float:
    """Backward-compatible wrapper around extraction.local_ocr."""
    return normalize_ocr_confidence(raw_confidence)


def _validate_markdown_text(text: str) -> List[str]:
    """Backward-compatible wrapper around extraction.review."""
    return validate_markdown_text(text)


def _has_corruption_warning(warnings: List[str]) -> bool:
    """Backward-compatible wrapper around extraction.review."""
    return has_corruption_warning(warnings)


def _has_severe_structure_warning(warnings: List[str]) -> bool:
    """Backward-compatible wrapper around extraction.review."""
    return has_severe_structure_warning(warnings)


def _medical_validation_warnings(reference_text: str, candidate_text: str) -> List[str]:
    """Backward-compatible wrapper around extraction.review."""
    return medical_validation_warnings(reference_text, candidate_text)


def _score_markdown_confidence(text: str, source: str, warnings: List[str]) -> float:
    """Backward-compatible wrapper around extraction.review."""
    return score_markdown_confidence(text, source, warnings)


def _should_use_visual_qa(
    confidence: float, warnings: List[str], source: str, cfg: PipelineConfig
) -> bool:
    """Backward-compatible wrapper around extraction.review."""
    return should_use_visual_qa(
        confidence,
        warnings,
        source,
        enable_visual_qa=cfg.enable_visual_qa,
        medical_strict=cfg.medical_strict,
        llm_enabled=cfg.llm_enabled,
        qa_confidence_threshold=cfg.qa_confidence_threshold,
    )


def _should_use_cleanup(
    confidence: float, warnings: List[str], source: str, cfg: PipelineConfig
) -> bool:
    """Backward-compatible wrapper around extraction.review."""
    return should_use_cleanup(
        confidence,
        warnings,
        source,
        enable_nlp_review=cfg.enable_nlp_review,
        medical_strict=cfg.medical_strict,
        llm_enabled=cfg.llm_enabled,
        cleanup_confidence_threshold=cfg.cleanup_confidence_threshold,
    )


_DISCOVERY_CACHE: Dict[
    str, Tuple[float, List[DiscoveredModel], List[BenchmarkSignal], List[str]]
] = {}
_ROUTING_CACHE: Dict[str, Tuple[float, RoutingDecision, List[str]]] = {}


def _safe_report_url(raw_url: str) -> str:
    """Return a report-safe URL without userinfo, query string, or fragment."""
    value = (raw_url or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value.split("?", 1)[0].split("#", 1)[0]
    if not parsed.scheme or not parsed.netloc:
        return value.split("?", 1)[0].split("#", 1)[0]

    host = parsed.hostname or ""
    netloc = host
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is not None:
        netloc = f"{host}:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


def _resolve_llm_client(cfg: PipelineConfig) -> Optional[OpenAICompatibleClient]:
    """Resolve runtime OpenAI-compatible client from CLI/env configuration."""
    if not cfg.llm_enabled:
        return None

    provider_key = (cfg.llm_provider_preset or "custom").strip().lower()
    provider_key_env = get_provider_api_key_env_var(provider_key)

    api_key = (
        (cfg.llm_api_key or "").strip()
        or get_env(provider_key_env, "").strip()
        or get_env("LLM_API_KEY", "").strip()
    )
    raw_base_url = (cfg.llm_base_url or "").strip() or get_env("LLM_BASE_URL", "").strip()
    raw_provider_name = (cfg.llm_provider_name or "").strip() or get_env(
        "LLM_PROVIDER_NAME", ""
    ).strip()

    base_url, provider_name = apply_provider_preset(
        provider_preset=(cfg.llm_provider_preset or "custom"),
        zai_plan=(cfg.llm_zai_plan or "general"),
        current_base_url=raw_base_url,
        current_provider_name=raw_provider_name,
    )

    if not api_key or not base_url:
        return None

    preset = get_provider_preset(provider_key)

    return OpenAICompatibleClient(
        api_key=api_key,
        base_url=base_url,
        provider_name=provider_name,
        provider_preset=provider_key,
        auth_mode=preset.auth_mode,
        timeout_seconds=cfg.llm_discovery_timeout_seconds,
        extra_headers=preset.required_headers,
    )


async def _get_discovery_snapshot(
    session: Any,
    cfg: PipelineConfig,
    client: OpenAICompatibleClient,
) -> Tuple[List[DiscoveredModel], List[BenchmarkSignal], List[str]]:
    """Return cached model discovery and benchmark snapshot."""
    cache_key = f"{client.base_url}|{client.provider_name}|{hash(client.api_key)}"
    now = time.time()
    cached = _DISCOVERY_CACHE.get(cache_key)
    if cached is not None and now - cached[0] < 1800:
        return cached[1], cached[2], cached[3]

    models = await client.list_models_async(session)
    signals, warnings = await asyncio.to_thread(
        collect_ocr_benchmark_signals,
        cfg.llm_discovery_timeout_seconds,
    )
    _DISCOVERY_CACHE[cache_key] = (now, models, signals, warnings)
    return models, signals, warnings


async def _route_llm_model(
    session: Any,
    cfg: PipelineConfig,
    task_kind: str,
    complexity: str,
    require_vision: bool,
) -> Tuple[Optional[OpenAICompatibleClient], Optional[RoutingDecision], List[str]]:
    """Compute OCR-aware routing decision for a given task and complexity."""
    client = _resolve_llm_client(cfg)
    if client is None:
        return None, None, ["llm_client_unconfigured"]

    if cfg.llm_model:
        synthetic_model = DiscoveredModel(
            id=cfg.llm_model,
            normalized_id=cfg.llm_model.lower(),
            supports_chat=True,
            supports_vision=require_vision,
        )
        decision = RoutingDecision(
            task_kind=task_kind,
            complexity=complexity,
            selected_model=synthetic_model,
            fallback_models=[],
            debug_lines=["Using explicitly configured model from --llm-model/LLM_MODEL."],
            selector_result=None,
        )
        return client, decision, []

    routing_key = "|".join(
        [
            client.base_url,
            client.provider_name,
            str(getattr(client, "provider_preset", "custom")),
            hashlib.sha256(str(getattr(client, "api_key", "")).encode("utf-8")).hexdigest()[:12],
            cfg.llm_routing_mode,
            task_kind,
            complexity,
            "vision" if require_vision else "text",
        ]
    )
    now = time.time()
    cached_route = _ROUTING_CACHE.get(routing_key)
    if cached_route is not None and now - cached_route[0] < 600:
        return client, cached_route[1], cached_route[2]

    models, signals, snapshot_warnings = await _get_discovery_snapshot(session, cfg, client)
    router = OcrAwareRouter()
    decision = router.route(
        task_kind=task_kind,
        complexity=complexity,
        routing_mode=cfg.llm_routing_mode,
        discovered_models=models,
        benchmark_signals=signals,
        require_vision=require_vision,
    )
    _ROUTING_CACHE[routing_key] = (now, decision, snapshot_warnings)
    return client, decision, snapshot_warnings


async def _call_strict_llm_review(
    session: Any,
    cfg: PipelineConfig,
    image_b64: str,
    draft_text: str,
    reason: str,
) -> str:
    """Run strict review pass and return corrected markdown.

    Returns the original draft when the service is unavailable or the call fails.
    """
    task_kind = "strict_review"
    complexity = "high"
    client, decision, _ = await _route_llm_model(
        session=session,
        cfg=cfg,
        task_kind=task_kind,
        complexity=complexity,
        require_vision=bool(image_b64),
    )
    if client is None or decision is None or decision.selected_model is None:
        return draft_text

    prompt = (
        "You are a strict medical transcription reviewer. "
        "Correct OCR mistakes using only evidence from the provided content. "
        "Do not invent values, medications, dates, identifiers, or sections. "
        "Preserve markdown structure and table fidelity. "
        "Return ONLY corrected markdown.\n\n"
        f"Review reason: {reason}\n\n"
        f"Draft OCR markdown:\n---\n{draft_text}\n---"
    )

    message_content: Any = prompt
    if image_b64:
        message_content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ]

    for attempt in range(max(1, cfg.qa_retries)):
        try:
            result = await client.chat_completion_async(
                session=session,
                model=decision.selected_model.id,
                messages=[{"role": "user", "content": message_content}],
                temperature=0.0,
                max_tokens=4096,
            )
            cleaned = _clean_markdown(result.text)
            return cleaned if cleaned else draft_text
        except Exception:
            if attempt == max(1, cfg.qa_retries) - 1:
                return draft_text
            await asyncio.sleep(1 + attempt)
    return draft_text  # pragma: no cover - defensive fallback after bounded retry loop


def _local_ocr_language_tokens(lang: str) -> List[str]:  # pragma: no cover
    """Backward-compatible wrapper around extraction.local_ocr."""
    return local_ocr_language_tokens(lang)


def _easyocr_language_list(lang: str) -> List[str]:  # pragma: no cover
    """Backward-compatible wrapper around extraction.local_ocr."""
    return easyocr_language_list(lang)


def _tesseract_language(lang: str) -> str:  # pragma: no cover
    """Backward-compatible wrapper around extraction.local_ocr."""
    return tesseract_language(lang)


def _prepare_local_ocr_image(image_b64: str, cfg: PipelineConfig) -> Tuple[Any, np.ndarray]:
    """Decode and preprocess OCR image payload for local engines."""
    from PIL import Image  # type: ignore[import-not-found]

    image_bytes = base64.b64decode(image_b64)
    image_bytes = preprocess_ocr_image(
        image_bytes,
        enable_preprocess=cfg.enable_ocr_preprocess,
        autocontrast=cfg.ocr_autocontrast,
        sharpen=cfg.ocr_sharpen,
        binarize_threshold=cfg.ocr_binarize_threshold,
    )
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return image, np.asarray(image)


@lru_cache(maxsize=4)
def _get_easyocr_reader(lang_key: str) -> Any:
    """Create and cache an EasyOCR Reader for the requested languages."""
    from easyocr import Reader  # type: ignore[import-not-found]

    languages = [token for token in lang_key.split("+") if token]
    return Reader(languages, gpu=False, verbose=False)


@lru_cache(maxsize=1)
def _get_rapidocr_reader() -> Any:
    """Create and cache a RapidOCR client instance."""
    from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]

    return RapidOCR()


def _ocr_result_items_to_text(
    items: Any,
    fallback_join: str = "\n",
) -> Tuple[str, float]:
    """Reconstruct text and mean confidence from OCR engine item formats."""
    if not items:
        return "", 0.0

    entries: List[Tuple[float, float, str, float]] = []
    for item in items:
        bbox: Optional[Any] = None
        text = ""
        confidence = -1.0

        if isinstance(item, (list, tuple)):
            if len(item) >= 3 and isinstance(item[1], str):
                bbox = item[0]
                text = str(item[1]).strip()
                try:
                    confidence = float(item[2])
                except Exception:
                    confidence = -1.0
            elif len(item) >= 2 and isinstance(item[0], str):
                text = str(item[0]).strip()
                try:
                    confidence = float(item[1])
                except Exception:
                    confidence = -1.0
            elif len(item) >= 1 and isinstance(item[0], str):
                text = str(item[0]).strip()

        if not text:
            continue

        x_coord = 0.0
        y_coord = 0.0
        if isinstance(bbox, (list, tuple)) and bbox:
            points: List[Tuple[float, float]] = []
            for point in bbox:
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    x_value: float | None = None
                    y_value: float | None = None
                    try:
                        x_value = float(point[0])
                        y_value = float(point[1])
                    except Exception:
                        x_value = None
                        y_value = None
                    if x_value is not None and y_value is not None:
                        points.append((x_value, y_value))
            if points:
                x_coord = min(point[0] for point in points)
                y_coord = min(point[1] for point in points)

        entries.append((y_coord, x_coord, text, confidence))

    if not entries:
        return "", 0.0

    entries.sort(key=lambda item: (item[0], item[1]))
    reconstructed_text = _normalize_markdown_document(
        fallback_join.join(entry[2] for entry in entries)
    )
    confidences = [entry[3] for entry in entries if entry[3] >= 0]
    mean_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    return reconstructed_text, mean_confidence


def _call_tesseract_local_ocr(  # pragma: no cover - native OCR adapter covered by contract tests
    image: Any, lang: str, psm: int
) -> Tuple[str, float, List[str]]:
    """Run local OCR through Tesseract and return normalized output.

    Raises:
        RuntimeError: When pytesseract is unavailable.
    """
    try:
        import pytesseract  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError("local_ocr_tesseract_unavailable") from exc

    tesseract_cmd = get_env("TESSERACT_CMD", "").strip()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    config = f"--oem 1 --psm {max(1, min(13, int(psm)))}"
    data = pytesseract.image_to_data(
        image,
        lang=lang,
        config=config,
        output_type=pytesseract.Output.DICT,
    )

    words: List[str] = []
    line_chunks: List[str] = []
    current_line_key: Optional[Tuple[int, int, int]] = None
    confidences: List[float] = []
    block_nums = data.get("block_num", [])
    par_nums = data.get("par_num", [])
    line_nums = data.get("line_num", [])
    conf_values = data.get("conf", [])
    text_values = data.get("text", [])

    for index, raw_word in enumerate(text_values):
        word = str(raw_word).strip()
        key = (
            int(block_nums[index]) if index < len(block_nums) else 0,
            int(par_nums[index]) if index < len(par_nums) else 0,
            int(line_nums[index]) if index < len(line_nums) else 0,
        )

        if key != current_line_key:
            if words:
                line_chunks.append(" ".join(words))
                words = []
            current_line_key = key

        raw_conf = conf_values[index] if index < len(conf_values) else "-1"
        try:
            conf_value = float(raw_conf)
        except Exception:
            conf_value = -1.0
        if conf_value >= 0:
            confidences.append(conf_value)

        if word:
            words.append(word)

    if words:
        line_chunks.append(" ".join(words))

    reconstructed_text = _normalize_markdown_document("\n".join(line_chunks))
    mean_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    warnings = ["local_ocr_provider", "local_ocr_tesseract", "local_ocr_reconstructed"]

    if mean_confidence < 45.0 or len(reconstructed_text) < 24:
        fallback = pytesseract.image_to_string(image, lang=lang, config=config)
        fallback = _normalize_markdown_document(fallback)
        if len(fallback) > len(reconstructed_text):
            reconstructed_text = fallback
            warnings.append("local_ocr_text_fallback")

    return reconstructed_text, round(mean_confidence / 100.0, 3), warnings


def _call_local_ocr(  # pragma: no cover - native OCR adapter covered by mocked contract tests
    image_b64: str,
    lang: str,
    psm: int,
    engine: str,
    cfg: PipelineConfig,
) -> LocalOcrResult:
    """Execute local OCR engine fallback chain for a rendered page image.

    Raises:
        RuntimeError: If all configured local providers fail.
    """
    selected_engine = (engine or "easyocr").strip().lower()
    if selected_engine == "rapidocr":
        engine_order = ["rapidocr", "tesseract"]
    elif selected_engine == "tesseract":
        engine_order = ["tesseract"]
    elif selected_engine == "auto":
        engine_order = ["easyocr", "rapidocr", "tesseract"]
    else:
        engine_order = ["easyocr", "rapidocr", "tesseract"]

    image, image_array = _prepare_local_ocr_image(image_b64, cfg)
    easyocr_langs = _easyocr_language_list(lang)
    tesseract_lang = _tesseract_language(lang)
    provider_errors: List[str] = []

    for engine_name in engine_order:
        try:
            if engine_name == "easyocr":
                reader = _get_easyocr_reader("+".join(easyocr_langs))
                with warnings.catch_warnings():
                    # EasyOCR can trigger a torch DataLoader pin_memory warning on CPU-only hosts.
                    # This warning is non-actionable for users in our CLI runtime.
                    warnings.filterwarnings(
                        "ignore",
                        message=r".*pin_memory.*no accelerator.*",
                        category=UserWarning,
                    )
                    raw_result = reader.readtext(image_array, detail=1, paragraph=True)
                text, raw_confidence = _ocr_result_items_to_text(raw_result)
                ocr_warnings = [
                    "local_ocr_provider",
                    "local_ocr_easyocr",
                    "local_ocr_reconstructed",
                ]
                if len(text) < 24:
                    with warnings.catch_warnings():
                        warnings.filterwarnings(
                            "ignore",
                            message=r".*pin_memory.*no accelerator.*",
                            category=UserWarning,
                        )
                        fallback_result = reader.readtext(image_array, detail=1, paragraph=False)
                    fallback_text, fallback_confidence = _ocr_result_items_to_text(fallback_result)
                    if len(fallback_text) > len(text):
                        text = fallback_text
                        raw_confidence = fallback_confidence
                        ocr_warnings.append("local_ocr_text_fallback")
                return LocalOcrResult(
                    text=text,
                    engine="easyocr",
                    confidence=_normalize_ocr_confidence(raw_confidence),
                    warnings=ocr_warnings,
                )

            if engine_name == "rapidocr":
                ocr = _get_rapidocr_reader()
                raw_result = ocr(image_array)
                raw_items = (
                    raw_result[0]
                    if isinstance(raw_result, (list, tuple)) and raw_result
                    else raw_result
                )
                text, raw_confidence = _ocr_result_items_to_text(raw_items)
                ocr_warnings = ["local_ocr_provider", "local_ocr_rapidocr"]
                return LocalOcrResult(
                    text=text,
                    engine="rapidocr",
                    confidence=_normalize_ocr_confidence(raw_confidence),
                    warnings=ocr_warnings,
                )

            if engine_name == "tesseract":
                text, confidence, tesseract_warnings = _call_tesseract_local_ocr(
                    image,
                    tesseract_lang,
                    psm,
                )
                return LocalOcrResult(
                    text=text,
                    engine="tesseract",
                    confidence=_normalize_ocr_confidence(confidence),
                    warnings=tesseract_warnings,
                )

            provider_errors.append(f"unsupported_local_ocr_engine:{engine_name}")
        except Exception as exc:
            provider_errors.append(f"{engine_name}_failed:{exc}")

    raise RuntimeError("local_ocr_unavailable:" + ";".join(provider_errors or ["unknown"]))


def _score_local_ocr_confidence(text: str, local_confidence: float, warnings: List[str]) -> float:
    """Backward-compatible wrapper around extraction.local_ocr."""
    return score_local_ocr_confidence(text, local_confidence, warnings)


def _needs_reprocess_block(page_index: int, confidence: float, min_confidence: float) -> str:
    """Backward-compatible wrapper around extraction.review."""
    return needs_reprocess_block(page_index, confidence, min_confidence)


async def _enforce_fail_closed_policy(  # pragma: no cover - covered by matrix tests
    session: Any,
    cfg: PipelineConfig,
    page_index: int,
    image_b64: str,
    source: str,
    baseline_text: str,
    confidence: float,
    warnings: List[str],
) -> Tuple[str, str, float, List[str], bool]:
    """Apply strict policy for low-confidence outputs in regulated mode."""
    if not cfg.medical_strict or confidence >= cfg.min_acceptable_confidence:
        return baseline_text, "accepted", confidence, warnings, False

    if not cfg.strict_llm_required:
        blocked = warnings + ["strict_llm_required_disabled", "llm_review_required"]
        return (
            _needs_reprocess_block(page_index, confidence, cfg.min_acceptable_confidence),
            "needs_reprocess",
            confidence,
            blocked,
            False,
        )

    if not _resolve_llm_client(cfg):
        blocked = warnings + ["strict_llm_unavailable", "llm_review_required"]
        return (
            _needs_reprocess_block(page_index, confidence, cfg.min_acceptable_confidence),
            "llm_review_required",
            confidence,
            blocked,
            False,
        )

    reviewed_text = await _call_strict_llm_review(
        session,
        cfg,
        image_b64,
        baseline_text,
        reason=(
            f"confidence {confidence:.3f} below minimum " f"{cfg.min_acceptable_confidence:.3f}"
        ),
    )
    reviewed_text = _normalize_markdown_document(reviewed_text)
    reviewed_warnings = _validate_markdown_text(reviewed_text)
    reviewed_validation = _medical_validation_warnings(baseline_text, reviewed_text)
    reviewed_warnings.extend(reviewed_validation)
    reviewed_warnings.append("llm_review_required")
    reviewed_confidence = _score_markdown_confidence(reviewed_text, source, reviewed_warnings)

    if cfg.llm_review_two_pass and (
        reviewed_confidence < cfg.min_acceptable_confidence or reviewed_validation
    ):
        verifier_text = await _call_strict_llm_review(
            session,
            cfg,
            image_b64,
            reviewed_text,
            reason="verification_pass_due_to_low_confidence_or_validator_flags",
        )
        verifier_text = _normalize_markdown_document(verifier_text)
        verifier_warnings = _validate_markdown_text(verifier_text)
        verifier_validation = _medical_validation_warnings(baseline_text, verifier_text)
        verifier_warnings.extend(verifier_validation)
        verifier_warnings.extend(["llm_review_required", "llm_verification_pass"])
        verifier_confidence = _score_markdown_confidence(verifier_text, source, verifier_warnings)
        if verifier_confidence >= reviewed_confidence:
            reviewed_text = verifier_text
            reviewed_confidence = verifier_confidence
            reviewed_warnings = verifier_warnings

    status = "llm_review_passed"
    if reviewed_confidence < cfg.min_acceptable_confidence or _has_severe_structure_warning(
        reviewed_warnings
    ):
        status = "needs_reprocess"
        reviewed_text = _needs_reprocess_block(
            page_index,
            reviewed_confidence,
            cfg.min_acceptable_confidence,
        )

    if reviewed_confidence < cfg.min_acceptable_confidence:
        reviewed_warnings.append(
            f"below_min_confidence:{reviewed_confidence:.3f}<"
            f"{cfg.min_acceptable_confidence:.3f}"
        )
    else:
        reviewed_warnings.append(
            f"post_llm_confidence:{reviewed_confidence:.3f}>="
            f"{cfg.min_acceptable_confidence:.3f}"
        )
    return reviewed_text, status, reviewed_confidence, reviewed_warnings, True


async def _enforce_medical_strict_review(  # pragma: no cover - wrapper branch
    session: Any,
    cfg: PipelineConfig,
    page_index: int,
    image_b64: str,
    source: str,
    text: str,
    confidence: float,
    warnings: List[str],
) -> Tuple[str, float, List[str], str, bool]:
    """Wrapper around fail-closed policy that returns review-oriented tuple order."""
    reviewed_text, status, reviewed_confidence, reviewed_warnings, llm_applied = (
        await _enforce_fail_closed_policy(
            session=session,
            cfg=cfg,
            page_index=page_index,
            image_b64=image_b64,
            source=source,
            baseline_text=text,
            confidence=confidence,
            warnings=warnings,
        )
    )
    return reviewed_text, reviewed_confidence, reviewed_warnings, status, llm_applied


async def _call_zai_vision(  # pragma: no cover - remote adapter
    session: Any,
    cfg: PipelineConfig,
    image_b64: str,
) -> str:
    """Run remote OCR via OpenAI-compatible multimodal model.

    Raises:
        RuntimeError: If all providers/retries fail.
    """
    client, decision, discovery_warnings = await _route_llm_model(
        session=session,
        cfg=cfg,
        task_kind="remote_ocr",
        complexity="high",
        require_vision=True,
    )
    if client is None or decision is None or decision.selected_model is None:
        raise RuntimeError("remote_ocr_llm_unavailable")

    prompt = (
        "You are an expert medical document OCR system. "
        "Extract all typed content and preserve layout in markdown. "
        "Recreate tables faithfully. Ignore signatures and scanner artifacts."
    )

    candidate_models: List[str] = [decision.selected_model.id]
    candidate_models.extend(model.id for model in decision.fallback_models)

    last_error = ""
    for model_name in candidate_models:
        for attempt in range(max(1, cfg.ocr_retries)):
            try:
                result = await client.chat_completion_async(
                    session=session,
                    model=model_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                                },
                            ],
                        }
                    ],
                    temperature=0.0,
                    max_tokens=4096,
                )
                cleaned = _clean_markdown(result.text)
                if cleaned:
                    return cleaned
                last_error = "empty_remote_ocr_response"
            except Exception as exc:
                last_error = str(exc)
                if attempt < max(1, cfg.ocr_retries) - 1:
                    await asyncio.sleep(1 + attempt)

    warning_hint = (
        f";discovery_warnings={','.join(discovery_warnings[:2])}" if discovery_warnings else ""
    )
    raise RuntimeError(f"all_routed_models_failed:{last_error}{warning_hint}")


async def _call_gemini_visual_qa(  # pragma: no cover - remote LLM adapter covered by mocked tests
    session: Any,
    cfg: PipelineConfig,
    image_b64: str,
    draft_text: str,
) -> str:
    """Run visual QA stage using routed OpenAI-compatible model."""
    client, decision, _ = await _route_llm_model(
        session=session,
        cfg=cfg,
        task_kind="visual_qa",
        complexity="high",
        require_vision=True,
    )
    if client is None or decision is None or decision.selected_model is None:
        return draft_text

    prompt = (
        "You are a strict QA reviewer. Compare the scanned image with the OCR text. "
        "Fix missing words, wrong numbers, and markdown structure. "
        "Return only corrected markdown.\n\n"
        f"OCR:\n---\n{draft_text}\n---"
    )

    for attempt in range(max(1, cfg.qa_retries)):
        try:
            result = await client.chat_completion_async(
                session=session,
                model=decision.selected_model.id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                            },
                        ],
                    }
                ],
                temperature=0.0,
                max_tokens=4096,
            )
            cleaned = _clean_markdown(result.text)
            return cleaned if cleaned else draft_text
        except Exception:
            if attempt == max(1, cfg.qa_retries) - 1:
                return draft_text
            await asyncio.sleep(1 + attempt)
    return draft_text


async def _call_openrouter_nlp(  # pragma: no cover - remote LLM adapter covered by mocked tests
    session: Any,
    cfg: PipelineConfig,
    text: str,
) -> str:
    """Run NLP cleanup stage using routed OpenAI-compatible model."""
    client, decision, _ = await _route_llm_model(
        session=session,
        cfg=cfg,
        task_kind="nlp_cleanup",
        complexity="medium",
        require_vision=False,
    )
    if client is None or decision is None or decision.selected_model is None:
        return text

    prompt = (
        "You are a medical NLP editor. Improve grammar and markdown formatting, "
        "especially tables. Do not add facts. Return only revised markdown.\n\n"
        f"---\n{text}\n---"
    )

    for attempt in range(max(1, cfg.cleanup_retries)):
        try:
            result = await client.chat_completion_async(
                session=session,
                model=decision.selected_model.id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=4096,
            )
            cleaned = _clean_markdown(result.text)
            return cleaned if cleaned else text
        except Exception:
            if attempt == max(1, cfg.cleanup_retries) - 1:
                break
            await asyncio.sleep(1 + attempt)
    return text


async def _process_page(  # pragma: no cover - orchestrator behavior covered by integration tests
    session: Any,
    cfg: PipelineConfig,
    semaphore: asyncio.Semaphore,
    page: Any,
    cache_dir: Path,
    doc_fingerprint: str,
    progress: Any,
) -> PageResult:
    """Process a single page through text-layer, local OCR, and remote fallback flows."""
    page_index = page.number
    async with semaphore:
        started = time.time()
        try:
            inspection = _page_has_usable_text_layer(page, cfg) if cfg.prefer_text_layer else None

            if inspection is not None:
                text_layer_cached_file = _cache_path(
                    cache_dir,
                    "text",
                    page_index,
                    f"{doc_fingerprint}:{len(inspection.text)}:{inspection.word_count}",
                )
                if (
                    cfg.cache_enabled
                    and is_cache_entry_valid(text_layer_cached_file, cfg.cache_ttl_seconds)
                    and not (cfg.medical_strict and cfg.llm_enabled)
                ):
                    progress.update(1)
                    cached_text = text_layer_cached_file.read_text(encoding="utf-8")
                    cached_text = _normalize_markdown_document(cached_text)
                    warnings = _validate_markdown_text(cached_text)
                    confidence = _score_markdown_confidence(cached_text, "text-layer", warnings)
                    status = "accepted"
                    llm_review_applied = False
                    if cfg.medical_strict and confidence < cfg.min_acceptable_confidence:
                        (
                            cached_text,
                            confidence,
                            warnings,
                            status,
                            llm_review_applied,
                        ) = await _enforce_medical_strict_review(
                            session=session,
                            cfg=cfg,
                            page_index=page_index,
                            image_b64="",
                            source="text-layer",
                            text=cached_text,
                            confidence=confidence,
                            warnings=warnings,
                        )
                    return PageResult(
                        page_index=page_index,
                        text=cached_text,
                        source="text-layer",
                        status=status,
                        confidence=confidence,
                        cache_hit=True,
                        qa_applied=False,
                        cleanup_applied=False,
                        llm_review_applied=llm_review_applied,
                        warnings=warnings,
                        elapsed_seconds=round(time.time() - started, 3),
                    )

                text = _normalize_markdown_document(inspection.text)
                warnings = _validate_markdown_text(text)
                confidence = _score_markdown_confidence(text, inspection.source, warnings)
                qa_applied = False
                cleanup_applied = False
                status = "accepted"
                llm_review_applied = False
                qa_image_b64 = ""

                if _has_corruption_warning(warnings) or (cfg.medical_strict and cfg.llm_enabled):
                    qa_image_b64 = await asyncio.to_thread(
                        _get_rendered_page_image_b64,
                        page=page,
                        cache_dir=cache_dir,
                        page_index=page_index,
                        doc_fingerprint=doc_fingerprint,
                        zoom_matrix=max(cfg.zoom_matrix, 1.8),
                        max_image_side_px=max(cfg.max_image_side_px, 2200),
                        grayscale=False,
                        cache_enabled=cfg.cache_enabled and cfg.cache_rendered_images,
                        preprocess_enabled=cfg.enable_ocr_preprocess,
                        autocontrast=cfg.ocr_autocontrast,
                        sharpen=cfg.ocr_sharpen,
                        binarize_threshold=cfg.ocr_binarize_threshold,
                        cache_ttl_seconds=cfg.cache_ttl_seconds,
                        cache_schema_version=cfg.cache_schema_version,
                    )
                    warnings.append("aggressive_postprocess_triggered")

                if _should_use_visual_qa(confidence, warnings, inspection.source, cfg):
                    text = await _call_gemini_visual_qa(session, cfg, qa_image_b64, text)
                    text = _normalize_markdown_document(text)
                    warnings = _validate_markdown_text(text)
                    confidence = _score_markdown_confidence(text, inspection.source, warnings)
                    qa_applied = True

                if _should_use_cleanup(confidence, warnings, inspection.source, cfg):
                    text = await _call_openrouter_nlp(session, cfg, text)
                    text = _normalize_markdown_document(text)
                    warnings = _validate_markdown_text(text)
                    confidence = _score_markdown_confidence(text, inspection.source, warnings)
                    cleanup_applied = True

                # Post-post-processing: force a strict LLM repair pass when corruption persists.
                if cfg.llm_enabled and _has_corruption_warning(warnings):
                    repaired = await _call_strict_llm_review(
                        session=session,
                        cfg=cfg,
                        image_b64=qa_image_b64,
                        draft_text=text,
                        reason="corruption_warnings_after_postprocessing",
                    )
                    repaired = _normalize_markdown_document(repaired)
                    repaired_warnings = _validate_markdown_text(repaired)
                    repaired_confidence = _score_markdown_confidence(
                        repaired,
                        inspection.source,
                        repaired_warnings,
                    )
                    if repaired_confidence >= confidence:
                        text = repaired
                        warnings = repaired_warnings + ["post_post_cleanup_applied"]
                        confidence = repaired_confidence
                        llm_review_applied = True

                if cfg.medical_strict and confidence < cfg.min_acceptable_confidence:
                    (
                        text,
                        confidence,
                        warnings,
                        status,
                        llm_review_applied,
                    ) = await _enforce_medical_strict_review(
                        session=session,
                        cfg=cfg,
                        page_index=page_index,
                        image_b64="",
                        source=inspection.source,
                        text=text,
                        confidence=confidence,
                        warnings=warnings,
                    )

                if cfg.cache_enabled and status in {"accepted", "llm_review_passed"}:
                    text_layer_cached_file.write_text(text, encoding="utf-8")

                progress.update(1)
                return PageResult(
                    page_index=page_index,
                    text=text,
                    source=inspection.source,
                    status=status,
                    confidence=confidence,
                    cache_hit=False,
                    qa_applied=qa_applied,
                    cleanup_applied=cleanup_applied,
                    llm_review_applied=llm_review_applied,
                    warnings=warnings,
                    elapsed_seconds=round(time.time() - started, 3),
                )

            ocr_cache_payload = (
                f"v{cfg.cache_schema_version}:{doc_fingerprint}:{cfg.zoom_matrix}:"
                f"{cfg.max_image_side_px}:"
                f"{int(cfg.ocr_grayscale)}:{int(cfg.local_first)}:{int(cfg.enable_local_ocr)}:"
                f"{cfg.local_ocr_engine}:{cfg.local_ocr_lang}:{cfg.local_min_confidence:.2f}"
            )
            vision_cached_file = _cache_path(
                cache_dir,
                "ocr",
                page_index,
                ocr_cache_payload,
            )
            local_cached_file = _cache_path(
                cache_dir,
                "local-ocr",
                page_index,
                ocr_cache_payload,
            )

            cached_ocr_file: Optional[Path] = None
            cache_source = "vision-ocr"
            if cfg.cache_enabled:
                if is_cache_entry_valid(local_cached_file, cfg.cache_ttl_seconds):
                    cached_ocr_file = local_cached_file
                    cache_source = "local-ocr"
                elif is_cache_entry_valid(vision_cached_file, cfg.cache_ttl_seconds):
                    cached_ocr_file = vision_cached_file
                    cache_source = "vision-ocr"

            if cfg.cache_enabled and cached_ocr_file is not None:
                progress.update(1)
                cached_text = cached_ocr_file.read_text(encoding="utf-8")
                cached_text = _normalize_markdown_document(cached_text)
                warnings = _validate_markdown_text(cached_text)
                confidence = _score_markdown_confidence(cached_text, cache_source, warnings)
                status = "accepted"
                llm_review_applied = False
                if cfg.medical_strict and confidence < cfg.min_acceptable_confidence:
                    (
                        cached_text,
                        confidence,
                        warnings,
                        status,
                        llm_review_applied,
                    ) = await _enforce_medical_strict_review(
                        session=session,
                        cfg=cfg,
                        page_index=page_index,
                        image_b64="",
                        source=cache_source,
                        text=cached_text,
                        confidence=confidence,
                        warnings=warnings,
                    )
                return PageResult(
                    page_index=page_index,
                    text=cached_text,
                    source=cache_source,
                    status=status,
                    confidence=confidence,
                    cache_hit=True,
                    qa_applied=False,
                    cleanup_applied=False,
                    llm_review_applied=llm_review_applied,
                    warnings=warnings,
                    elapsed_seconds=round(time.time() - started, 3),
                )

            image_b64 = await asyncio.to_thread(
                _get_rendered_page_image_b64,
                page=page,
                cache_dir=cache_dir,
                page_index=page_index,
                doc_fingerprint=doc_fingerprint,
                zoom_matrix=cfg.zoom_matrix,
                max_image_side_px=cfg.max_image_side_px,
                grayscale=cfg.ocr_grayscale,
                cache_enabled=cfg.cache_enabled and cfg.cache_rendered_images,
                preprocess_enabled=cfg.enable_ocr_preprocess,
                autocontrast=cfg.ocr_autocontrast,
                sharpen=cfg.ocr_sharpen,
                binarize_threshold=cfg.ocr_binarize_threshold,
                cache_ttl_seconds=cfg.cache_ttl_seconds,
                cache_schema_version=cfg.cache_schema_version,
            )
            selected_source = "vision-ocr"
            text = ""
            page_warnings: List[str] = []
            confidence = 0.0
            qa_applied = False
            cleanup_applied = False
            llm_review_applied = False
            routing_notes: List[str] = []

            provider_order = ["local", "remote"] if cfg.local_first else ["remote", "local"]
            provider_errors: List[str] = []

            for provider in provider_order:
                if provider == "local" and cfg.enable_local_ocr:
                    try:
                        local_result = await asyncio.to_thread(
                            _call_local_ocr,
                            image_b64=image_b64,
                            lang=cfg.local_ocr_lang,
                            psm=cfg.local_ocr_psm,
                            engine=cfg.local_ocr_engine,
                            cfg=cfg,
                        )
                        local_text = local_result.text
                        local_quality = local_result.confidence
                        local_warnings = list(local_result.warnings)
                        local_warnings.extend(_validate_markdown_text(local_text))
                        local_confidence = _score_local_ocr_confidence(
                            local_text,
                            local_quality,
                            local_warnings,
                        )
                        if (
                            local_confidence >= cfg.local_min_confidence
                            and not _has_severe_structure_warning(local_warnings)
                        ):
                            text = local_text
                            page_warnings = local_warnings
                            confidence = local_confidence
                            selected_source = "local-ocr"
                            break

                        text = local_text
                        page_warnings = local_warnings + [
                            (
                                f"local_confidence_below_threshold:{local_confidence:.3f}<"
                                f"{cfg.local_min_confidence:.3f}"
                            )
                        ]
                        confidence = local_confidence
                        selected_source = "local-ocr"
                    except Exception as local_exc:
                        provider_errors.append(f"local_ocr_failed:{local_exc}")
                    continue

                if provider == "remote":
                    remote_text = ""
                    remote_last_exc: Optional[Exception] = None

                    # Try increasingly robust render profiles to recover hard scanned pages.
                    render_profiles: List[Tuple[float, int, bool]] = [
                        (cfg.zoom_matrix, cfg.max_image_side_px, cfg.ocr_grayscale),
                        (max(0.9, cfg.zoom_matrix - 0.2), min(cfg.max_image_side_px, 1500), True),
                        (max(0.75, cfg.zoom_matrix - 0.4), min(cfg.max_image_side_px, 1250), True),
                    ]
                    if cfg.scanned_fast:
                        render_profiles.append(
                            (max(1.3, cfg.zoom_matrix), max(1800, cfg.max_image_side_px), False)
                        )

                    for i, (attempt_zoom, attempt_max_side, attempt_gray) in enumerate(
                        render_profiles
                    ):
                        try:
                            current_image = image_b64
                            if i > 0:
                                current_image = await asyncio.to_thread(
                                    _get_rendered_page_image_b64,
                                    page=page,
                                    cache_dir=cache_dir,
                                    page_index=page_index,
                                    doc_fingerprint=doc_fingerprint,
                                    zoom_matrix=attempt_zoom,
                                    max_image_side_px=attempt_max_side,
                                    grayscale=attempt_gray,
                                    cache_enabled=cfg.cache_enabled and cfg.cache_rendered_images,
                                    preprocess_enabled=cfg.enable_ocr_preprocess,
                                    autocontrast=cfg.ocr_autocontrast,
                                    sharpen=cfg.ocr_sharpen,
                                    binarize_threshold=cfg.ocr_binarize_threshold,
                                    cache_ttl_seconds=cfg.cache_ttl_seconds,
                                    cache_schema_version=cfg.cache_schema_version,
                                )
                            remote_text = await _call_zai_vision(session, cfg, current_image)
                            image_b64 = current_image
                            break
                        except Exception as remote_exc:
                            remote_last_exc = remote_exc
                            if i == len(render_profiles) - 1:
                                provider_errors.append(f"remote_ocr_failed:{remote_exc}")

                    if remote_text:
                        text = _normalize_markdown_document(remote_text)
                        page_warnings = _validate_markdown_text(text)
                        if cfg.scanned_fast:
                            page_warnings.append("scanned_fast_profile")
                        if remote_last_exc is not None:
                            page_warnings.append("ocr_fallback_used")
                        confidence = _score_markdown_confidence(text, "vision-ocr", page_warnings)
                        selected_source = "vision-ocr"
                        task_kind = classify_task_kind(selected_source, page_warnings, confidence)
                        complexity = classify_complexity(False, 1, _word_count(text))
                        _, route_decision, route_warnings = await _route_llm_model(
                            session=session,
                            cfg=cfg,
                            task_kind=task_kind,
                            complexity=complexity,
                            require_vision=True,
                        )
                        if cfg.llm_routing_debug:
                            if route_decision is not None:
                                routing_notes.extend(
                                    [f"routing:{line}" for line in route_decision.debug_lines[:8]]
                                )
                            routing_notes.extend(
                                [f"routing_warning:{item}" for item in route_warnings[:4]]
                            )
                        break

            if not text:
                raise RuntimeError(
                    "all_ocr_providers_failed:" + ";".join(provider_errors or ["unknown"])
                )

            if _should_use_visual_qa(confidence, page_warnings, selected_source, cfg):
                text = await _call_gemini_visual_qa(session, cfg, image_b64, text)
                text = _normalize_markdown_document(text)
                page_warnings = _validate_markdown_text(text)
                confidence = _score_markdown_confidence(text, selected_source, page_warnings)
                qa_applied = True

            if _should_use_cleanup(confidence, page_warnings, selected_source, cfg):
                text = await _call_openrouter_nlp(session, cfg, text)
                text = _normalize_markdown_document(text)
                page_warnings = _validate_markdown_text(text)
                confidence = _score_markdown_confidence(text, selected_source, page_warnings)
                cleanup_applied = True

            if cfg.llm_enabled and _has_corruption_warning(page_warnings):
                repaired = await _call_strict_llm_review(
                    session=session,
                    cfg=cfg,
                    image_b64=image_b64,
                    draft_text=text,
                    reason="corruption_warnings_after_ocr_postprocessing",
                )
                repaired = _normalize_markdown_document(repaired)
                repaired_warnings = _validate_markdown_text(repaired)
                repaired_confidence = _score_markdown_confidence(
                    repaired,
                    selected_source,
                    repaired_warnings,
                )
                if repaired_confidence >= confidence:
                    text = repaired
                    page_warnings = repaired_warnings + ["post_post_cleanup_applied"]
                    confidence = repaired_confidence
                    llm_review_applied = True

            status = "accepted"

            if cfg.medical_strict and confidence < cfg.min_acceptable_confidence:
                strict_profiles: List[Tuple[float, int, bool]] = [
                    (max(1.8, cfg.zoom_matrix), max(2200, cfg.max_image_side_px), False),
                    (
                        max(2.1, cfg.zoom_matrix + 0.2),
                        max(2600, cfg.max_image_side_px + 300),
                        False,
                    ),
                ]
                attempts = max(0, min(cfg.strict_recovery_attempts, len(strict_profiles)))

                # If confidence is close to threshold, try high-detail remote OCR recovery first.
                if confidence >= (cfg.min_acceptable_confidence - 0.12) and attempts > 0:
                    for strict_zoom, strict_side, strict_gray in strict_profiles[:attempts]:
                        strict_text = ""
                        try:
                            strict_image = await asyncio.to_thread(
                                _get_rendered_page_image_b64,
                                page=page,
                                cache_dir=cache_dir,
                                page_index=page_index,
                                doc_fingerprint=doc_fingerprint,
                                zoom_matrix=strict_zoom,
                                max_image_side_px=strict_side,
                                grayscale=strict_gray,
                                cache_enabled=cfg.cache_enabled and cfg.cache_rendered_images,
                                preprocess_enabled=cfg.enable_ocr_preprocess,
                                autocontrast=cfg.ocr_autocontrast,
                                sharpen=cfg.ocr_sharpen,
                                binarize_threshold=cfg.ocr_binarize_threshold,
                                cache_ttl_seconds=cfg.cache_ttl_seconds,
                                cache_schema_version=cfg.cache_schema_version,
                            )
                            strict_text = await _call_zai_vision(
                                session,
                                replace(cfg, ocr_retries=max(2, cfg.ocr_retries)),
                                strict_image,
                            )
                        except Exception as strict_exc:
                            page_warnings.append(f"strict_recovery_failed:{strict_exc}")

                        if not strict_text:
                            continue

                        strict_text = _normalize_markdown_document(strict_text)
                        strict_warnings = _validate_markdown_text(strict_text)
                        strict_warnings.append("medical_strict_recovery")
                        strict_confidence = _score_markdown_confidence(
                            strict_text,
                            selected_source,
                            strict_warnings,
                        )

                        if strict_confidence > confidence:
                            text = strict_text
                            page_warnings = strict_warnings
                            confidence = strict_confidence

                        if confidence >= cfg.min_acceptable_confidence:
                            break

                if confidence < cfg.min_acceptable_confidence:
                    (
                        text,
                        confidence,
                        page_warnings,
                        status,
                        llm_review_applied,
                    ) = await _enforce_medical_strict_review(
                        session=session,
                        cfg=cfg,
                        page_index=page_index,
                        image_b64=image_b64,
                        source=selected_source,
                        text=text,
                        confidence=confidence,
                        warnings=page_warnings,
                    )

            if cfg.llm_routing_debug and routing_notes:
                page_warnings.extend(routing_notes)

            if cfg.cache_enabled and status in {"accepted", "llm_review_passed"}:
                target_cache = (
                    local_cached_file if selected_source == "local-ocr" else vision_cached_file
                )
                target_cache.write_text(text, encoding="utf-8")

            progress.update(1)
            return PageResult(
                page_index=page_index,
                text=text,
                source=selected_source,
                status=status,
                confidence=confidence,
                cache_hit=False,
                qa_applied=qa_applied,
                cleanup_applied=cleanup_applied,
                llm_review_applied=llm_review_applied,
                warnings=page_warnings,
                elapsed_seconds=round(time.time() - started, 3),
            )
        except Exception as exc:
            progress.update(1)
            warning = f"page_failed:{exc}"
            fallback = f"\n[Page {page_index + 1} failed: {exc}]\n"
            return PageResult(
                page_index=page_index,
                text=fallback,
                source="error",
                status="error",
                confidence=0.0,
                cache_hit=False,
                qa_applied=False,
                cleanup_applied=False,
                llm_review_applied=False,
                warnings=[warning],
                elapsed_seconds=round(time.time() - started, 3),
            )


def _render_page_image_b64(  # pragma: no cover - PyMuPDF adapter covered by mocked contract tests
    page: Any,
    zoom_matrix: float,
    max_image_side_px: int,
    grayscale: bool,
) -> str:
    """Render PDF page into base64-encoded JPEG respecting profile constraints."""
    import fitz  # type: ignore[import-not-found]

    longest_side = max(float(page.rect.width), float(page.rect.height), 1.0)
    effective_zoom = max(0.3, float(zoom_matrix))
    if max_image_side_px > 0:
        max_zoom = max_image_side_px / longest_side
        effective_zoom = min(effective_zoom, max(0.3, max_zoom))

    matrix = fitz.Matrix(effective_zoom, effective_zoom)
    colorspace = fitz.csGRAY if grayscale else fitz.csRGB
    pix = page.get_pixmap(matrix=matrix, colorspace=colorspace, alpha=False)
    return base64.b64encode(pix.tobytes("jpeg")).decode("utf-8")


def _get_rendered_page_image_b64(  # pragma: no cover - render cache adapter
    page: Any,
    cache_dir: Path,
    page_index: int,
    doc_fingerprint: str,
    zoom_matrix: float,
    max_image_side_px: int,
    grayscale: bool,
    cache_enabled: bool,
    preprocess_enabled: bool,
    autocontrast: bool,
    sharpen: bool,
    binarize_threshold: int,
    cache_ttl_seconds: int = 0,
    cache_schema_version: int = 1,
) -> str:
    """Return rendered page image payload, using cache when enabled."""
    payload = _render_profile_payload(
        doc_fingerprint=doc_fingerprint,
        zoom_matrix=zoom_matrix,
        max_image_side_px=max_image_side_px,
        grayscale=grayscale,
        preprocess_enabled=preprocess_enabled,
        autocontrast=autocontrast,
        sharpen=sharpen,
        binarize_threshold=binarize_threshold,
        schema_version=cache_schema_version,
    )
    cached_path = _render_cache_path(cache_dir, page_index, payload)
    if cache_enabled and is_cache_entry_valid(cached_path, cache_ttl_seconds):
        return cached_path.read_text(encoding="utf-8")

    image_b64 = _render_page_image_b64(
        page,
        zoom_matrix=zoom_matrix,
        max_image_side_px=max_image_side_px,
        grayscale=grayscale,
    )
    if cache_enabled:
        cached_path.write_text(image_b64, encoding="utf-8")
    return image_b64


async def run_pipeline(  # pragma: no cover - runtime orchestration covered by functional tests
    pdf_file: Path, cfg: PipelineConfig
) -> Tuple[str, Dict[str, Any]]:
    """Run the complete extraction pipeline for a PDF document.

    Args:
        pdf_file: Input PDF path.
        cfg: Pipeline runtime configuration.

    Returns:
        Tuple of merged markdown text and structured per-page report.
    """
    import fitz  # type: ignore[import-not-found]
    import aiohttp  # type: ignore[import-not-found]
    from tqdm.asyncio import tqdm

    doc = fitz.open(str(pdf_file))
    page_count = len(doc)

    file_stat = pdf_file.stat()
    doc_fingerprint = hashlib.sha256(
        f"{pdf_file.resolve()}:{file_stat.st_size}:{file_stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()

    effective_cfg = cfg
    if cfg.scanned_fast:
        effective_cfg = replace(
            cfg,
            concurrency=min(max(1, cfg.concurrency), 2),
            ocr_retries=max(2, cfg.ocr_retries),
            qa_retries=1,
            cleanup_retries=1,
            enable_visual_qa=False,
            enable_nlp_review=False,
            zoom_matrix=min(cfg.zoom_matrix, 1.2),
            max_image_side_px=min(cfg.max_image_side_px, 1500),
            ocr_grayscale=True,
        )

    effective_cache_enabled = resolve_effective_cache_enabled(
        cache_enabled=effective_cfg.cache_enabled,
        medical_strict=effective_cfg.medical_strict,
        allow_sensitive_cache_persistence=effective_cfg.allow_sensitive_cache_persistence,
    )
    if effective_cache_enabled != effective_cfg.cache_enabled:
        effective_cfg = replace(effective_cfg, cache_enabled=effective_cache_enabled)

    cache_root = pdf_file.parent / ".cache"
    cache_dir = cache_root / pdf_file.stem
    if effective_cfg.cache_enabled:
        cache_dir.mkdir(parents=True, exist_ok=True)

    timeout = aiohttp.ClientTimeout(total=cfg.timeout_seconds)
    semaphore = asyncio.Semaphore(max(1, effective_cfg.concurrency))

    progress = tqdm(total=page_count, ncols=90, desc=f"Processing {pdf_file.name}")
    async with aiohttp.ClientSession(timeout=timeout) as session:
        batch_size = max(1, effective_cfg.concurrency * 4)
        results: List[PageResult] = []
        for start, stop in iter_chunk_bounds(page_count, batch_size):
            tasks = [
                _process_page(
                    session,
                    effective_cfg,
                    semaphore,
                    doc[i],
                    cache_dir,
                    doc_fingerprint,
                    progress,
                )
                for i in range(start, stop)
            ]
            results.extend(await asyncio.gather(*tasks))
    progress.close()
    doc.close()

    ordered = sorted(results, key=lambda x: x.page_index)
    markdown_text = "\n\n---\n\n".join(result.text for result in ordered)
    report = {
        "document": pdf_file.name,
        "pages": [
            {
                "page": result.page_index + 1,
                "source": result.source,
                "status": result.status,
                "confidence": result.confidence,
                "cache_hit": result.cache_hit,
                "qa_applied": result.qa_applied,
                "cleanup_applied": result.cleanup_applied,
                "llm_review_applied": result.llm_review_applied,
                "warnings": result.warnings,
                "elapsed_seconds": result.elapsed_seconds,
            }
            for result in ordered
        ],
        "summary": {
            "pages": len(ordered),
            "text_layer_pages": sum(1 for result in ordered if result.source == "text-layer"),
            "ocr_pages": sum(
                1 for result in ordered if result.source in {"vision-ocr", "local-ocr"}
            ),
            "local_ocr_pages": sum(1 for result in ordered if result.source == "local-ocr"),
            "vision_ocr_pages": sum(1 for result in ordered if result.source == "vision-ocr"),
            "accepted_pages": sum(1 for result in ordered if result.status == "accepted"),
            "llm_review_required_pages": sum(
                1 for result in ordered if result.status == "llm_review_required"
            ),
            "llm_review_passed_pages": sum(
                1 for result in ordered if result.status == "llm_review_passed"
            ),
            "needs_reprocess_pages": sum(
                1 for result in ordered if result.status == "needs_reprocess"
            ),
            "error_pages": sum(1 for result in ordered if result.source == "error"),
            "qa_pages": sum(1 for result in ordered if result.qa_applied),
            "cleanup_pages": sum(1 for result in ordered if result.cleanup_applied),
            "llm_review_pages": sum(1 for result in ordered if result.llm_review_applied),
            "mean_confidence": (
                round(sum(result.confidence for result in ordered) / len(ordered), 3)
                if ordered
                else 0.0
            ),
            "llm_provider": (effective_cfg.llm_provider_name or "auto"),
            "llm_base_url": _safe_report_url(
                effective_cfg.llm_base_url or get_env("LLM_BASE_URL", "")
            ),
            "llm_routing_mode": effective_cfg.llm_routing_mode,
            "llm_routing_debug": effective_cfg.llm_routing_debug,
            "cache_enabled_requested": cfg.cache_enabled,
            "cache_enabled_effective": effective_cfg.cache_enabled,
            "sensitive_cache_allowed": effective_cfg.allow_sensitive_cache_persistence,
        },
    }
    report = add_summary_observability(report, effective_cfg.min_acceptable_confidence)
    report["document_status"] = _document_status_from_report(report, effective_cfg)
    return markdown_text, report


def _document_status_from_report(report: Dict[str, Any], cfg: PipelineConfig) -> str:
    """Derive the document-level status from page statuses and runtime policy."""
    return derive_document_status(report, medical_strict=cfg.medical_strict)


def _document_success(status: str) -> bool:
    """Return whether a document-level status is operationally successful."""
    return document_success(status)


def render_html(markdown_text: str) -> str:
    """Convert markdown output to sanitized HTML document."""
    return render_html_document(markdown_text)


def process_document(  # pragma: no cover - filesystem adapter
    pdf_file: Path,
    output_dir: Path,
    suffix: str,
    html_enabled: bool,
    cfg: PipelineConfig,
) -> DocumentProcessingResult:
    """Process one PDF and persist markdown/report/optional HTML artifacts.

    Args:
        pdf_file: Source PDF path.
        output_dir: Target output directory.
        suffix: Markdown filename suffix.
        html_enabled: Whether to persist HTML output.
        cfg: Runtime pipeline configuration.

    Returns:
        Structured document processing result with output paths and status.
    """
    started = time.time()

    windows_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if platform_is_windows() and windows_policy is not None:
        asyncio.set_event_loop_policy(windows_policy())

    markdown_text, report = asyncio.run(run_pipeline(pdf_file, cfg))

    output_dir.mkdir(parents=True, exist_ok=True)
    md_file = output_dir / f"{pdf_file.stem}{suffix}"
    md_file.write_text(markdown_text, encoding="utf-8")

    report_file = output_dir / f"{pdf_file.stem}.canonical.report.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    html_file: Optional[Path] = None
    if html_enabled:
        html_file = output_dir / f"{pdf_file.stem}.canonical.html"
        html_file.write_text(render_html(markdown_text), encoding="utf-8")

    status = _document_status_from_report(report, cfg)
    success = _document_success(status)
    elapsed = time.time() - started
    label = "OK" if success else "WARN"
    print(f"[{label}] {pdf_file.name} -> {md_file.name} ({elapsed:.1f}s) status={status}")
    return DocumentProcessingResult(
        markdown_file=md_file,
        report_file=report_file,
        html_file=html_file,
        status=status,
        success=success,
        report=report,
    )


def platform_is_windows() -> bool:
    """Return whether runtime OS is Windows."""
    return os.name == "nt"
