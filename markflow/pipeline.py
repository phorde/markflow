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
import re
import time
import warnings
from functools import lru_cache
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .benchmark_ingestion import collect_ocr_benchmark_signals
from .llm_client import OpenAICompatibleClient
from .llm_types import BenchmarkSignal, DiscoveredModel, RoutingDecision
from .provider_presets import apply_provider_preset, get_provider_api_key_env_var, get_provider_preset
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

        if key not in os.environ:
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
    try:
        import psutil  # type: ignore[import-not-found]

        return round(float(psutil.virtual_memory().total) / (1024**3), 2)
    except Exception:
        pass

    # Windows fallback without external dependencies.
    if os.name == "nt":

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
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
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

    source = Path(raw)
    if source.is_file() and source.suffix.lower() == ".pdf":
        return [source]
    if source.is_dir():
        return sorted([p for p in source.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])
    raise FileNotFoundError(f"Input path does not exist or is not a PDF: {raw}")


def _clean_markdown(text: str) -> str:
    """Remove common markdown code-fence wrappers from model output.

    Args:
        text: Raw markdown-like text from OCR/LLM stages.

    Returns:
        Normalized markdown content without wrapping fences.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if text.startswith("```markdown"):
        text = text.replace("```markdown\n", "", 1)
    if text.endswith("```"):
        text = text[:-3].strip()
    return text.strip()


def _looks_like_atomic_markdown_line(line: str) -> bool:
    """Determine whether a line should be preserved as a standalone markdown line.

    Args:
        line: Candidate markdown line.

    Returns:
        True when line looks like a heading/list/table or structural marker.
    """
    if not line:
        return True
    if line.startswith(("#", ">", "```", "|")):
        return True
    if re.match(r"^(?:[-*+]|\d+[.)])\s+", line):
        return True
    if re.match(r"^\[([ xX])\]\s+", line):
        return True
    if re.match(r"^\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?$", line):
        return True
    if len(line) <= 60 and (line.isupper() or line.endswith(":")):
        return True
    return False


def _normalize_markdown_document(text: str) -> str:
    """Normalize markdown spacing while preserving structural lines.

    Args:
        text: Raw markdown text.

    Returns:
        Compact and normalized markdown document.
    """
    normalized = _normalize_whitespace(_clean_markdown(text))
    if not normalized:
        return normalized

    lines = normalized.splitlines()
    output_lines: List[str] = []
    paragraph: List[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            output_lines.append(" ".join(paragraph).strip())
            paragraph.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            if output_lines and output_lines[-1] != "":
                output_lines.append("")
            continue

        if _looks_like_atomic_markdown_line(line):
            flush_paragraph()
            output_lines.append(line)
            continue

        if paragraph:
            previous = paragraph[-1]
            if previous.endswith(("-", "/")) or len(previous) < 24:
                paragraph.append(line)
            else:
                paragraph.append(line)
        else:
            paragraph.append(line)

    flush_paragraph()

    compacted: List[str] = []
    previous_blank = False
    for line in output_lines:
        if not line:
            if not previous_blank:
                compacted.append("")
            previous_blank = True
            continue
        compacted.append(line)
        previous_blank = False

    return "\n".join(compacted).strip()


def _normalize_whitespace(text: str) -> str:
    """Collapse excessive whitespace and normalize line endings.

    Args:
        text: Raw input text.

    Returns:
        Text with canonical spacing.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _word_count(text: str) -> int:
    """Count unicode-aware words in text.

    Args:
        text: Input text.

    Returns:
        Number of detected words.
    """
    return len(re.findall(r"\b[\wÀ-ÿ]+\b", text, flags=re.UNICODE))


def _page_text_layer(page: Any) -> Tuple[str, int, int, int, int]:
    """Extract text-layer metrics from a PDF page object.

    Args:
        page: PyMuPDF-like page object.

    Returns:
        Tuple of normalized text, character count, word count, block count,
        and embedded image count.
    """
    text = page.get_text("text") or ""
    blocks = page.get_text("blocks") or []
    image_count = len(page.get_images(full=True) or [])
    block_count = sum(1 for block in blocks if len(block) > 4 and str(block[4]).strip())
    return (
        _normalize_whitespace(text),
        len(text.strip()),
        _word_count(text),
        block_count,
        image_count,
    )


def _page_text_confidence(text_chars: int, word_count: int, structure_count: int) -> float:
    """Compute heuristic confidence for text-layer extraction quality.

    Args:
        text_chars: Number of extracted characters.
        word_count: Number of extracted words.
        structure_count: Number of structural blocks.

    Returns:
        Confidence score in range [0.0, 0.99].
    """
    if text_chars <= 0:
        return 0.0

    length_score = min(0.5, text_chars / 1200.0)
    word_score = min(0.2, word_count / 120.0)
    structure_score = min(0.2, structure_count / 40.0)
    base = 0.55 + length_score + word_score + structure_score
    return round(min(base, 0.99), 3)


def _page_has_usable_text_layer(page: Any, cfg: PipelineConfig) -> Optional[PageInspection]:
    """Return text-layer inspection when page content is sufficiently rich.

    Args:
        page: PDF page object.
        cfg: Runtime pipeline configuration.

    Returns:
        PageInspection for usable text-layer pages, otherwise None.
    """
    text, text_chars, word_count, block_count, image_count = _page_text_layer(page)
    if text_chars < cfg.text_min_chars or word_count < 5:
        return None

    warnings: List[str] = []
    if text_chars < 80:
        warnings.append("short_text_layer")
    if block_count == 0:
        warnings.append("low_text_structure")

    confidence = _page_text_confidence(text_chars, word_count, block_count)
    return PageInspection(
        page_index=page.number,
        source="text-layer",
        text=text,
        text_chars=text_chars,
        word_count=word_count,
        block_count=block_count,
        image_count=image_count,
        confidence=confidence,
        warnings=warnings,
    )


def _page_signature(kind: str, payload: str, page_index: int) -> str:
    """Generate deterministic SHA256 signature for cache key material."""
    digest = hashlib.sha256(f"{kind}:{page_index}:{payload}".encode("utf-8")).hexdigest()
    return digest


def _cache_path(cache_dir: Path, kind: str, page_index: int, payload: str) -> Path:
    """Build a page-level text cache file path for OCR/text outputs."""
    digest = _page_signature(kind, payload, page_index)
    return cache_dir / f"{page_index + 1:04d}.{kind}.{digest}.txt"


def _render_cache_path(cache_dir: Path, page_index: int, payload: str) -> Path:
    """Build a page-level rendered-image cache path."""
    digest = _page_signature("render", payload, page_index)
    return cache_dir / f"{page_index + 1:04d}.render.{digest}.b64"


def _render_profile_payload(
    doc_fingerprint: str,
    zoom_matrix: float,
    max_image_side_px: int,
    grayscale: bool,
    preprocess_enabled: bool,
    autocontrast: bool,
    sharpen: bool,
    binarize_threshold: int,
) -> str:
    """Serialize render profile parameters into a cache payload string."""
    return (
        f"{doc_fingerprint}:{zoom_matrix:.3f}:{max_image_side_px}:"
        f"{int(grayscale)}:{int(preprocess_enabled)}:{int(autocontrast)}:"
        f"{int(sharpen)}:{binarize_threshold}"
    )


def _preprocess_ocr_image(
    image_bytes: bytes,
    enable_preprocess: bool,
    autocontrast: bool,
    sharpen: bool,
    binarize_threshold: int,
) -> bytes:
    """Apply optional OCR-oriented image preprocessing.

    Args:
        image_bytes: Source image bytes.
        enable_preprocess: Toggle preprocessing stage.
        autocontrast: Apply autocontrast when enabled.
        sharpen: Apply sharpening filter when enabled.
        binarize_threshold: Optional binarization threshold.

    Returns:
        JPEG bytes ready for OCR.
    """
    if not enable_preprocess:
        return image_bytes

    try:
        from PIL import Image, ImageFilter, ImageOps  # type: ignore[import-not-found]
    except Exception:
        return image_bytes

    image = Image.open(io.BytesIO(image_bytes))
    if image.mode not in {"L", "RGB"}:
        image = image.convert("L")
    else:
        image = image.convert("L")

    if autocontrast:
        image = ImageOps.autocontrast(image)
    if sharpen:
        image = image.filter(ImageFilter.SHARPEN)
    if 0 < binarize_threshold < 255:
        threshold = int(binarize_threshold)
        lookup_table = [255 if level >= threshold else 0 for level in range(256)]
        image = image.point(lookup_table, mode="1").convert("L")

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()


def _validate_markdown_text(text: str) -> List[str]:
    """Run structural sanity checks over extracted markdown text.

    Args:
        text: Candidate markdown content.

    Returns:
        List of warning tokens describing suspicious output patterns.
    """
    warnings: List[str] = []
    normalized = text.strip()
    if not normalized:
        warnings.append("empty_output")
        return warnings

    if normalized.count("|") >= 2:
        table_lines = [line for line in normalized.splitlines() if "|" in line]
        if len(table_lines) == 1:
            warnings.append("isolated_table_row")
        if any(len(line.split("|")) <= 2 for line in table_lines):
            warnings.append("weak_table_structure")

    if re.search(r"\b(?:UNK|N/?A|nan|null|None)\b", normalized, flags=re.IGNORECASE):
        warnings.append("suspicious_placeholder_tokens")

    if re.search(r"[\uFFFD]{1,}", normalized):
        warnings.append("replacement_character_present")

    if len(normalized) < 20:
        warnings.append("very_short_output")

    # Corruption heuristics for OCR fragments that look like mixed noise/gibberish.
    tokens = re.findall(r"\b[\wÀ-ÿ]+\b", normalized, flags=re.UNICODE)
    alpha_tokens = [token for token in tokens if re.search(r"[A-Za-zÀ-ÿ]", token)]
    if len(alpha_tokens) >= 40:
        vowel_pattern = re.compile(r"[aeiouAEIOUÀ-ÿ]")
        no_vowel_ratio = sum(
            1 for token in alpha_tokens if len(token) >= 5 and not vowel_pattern.search(token)
        ) / max(1, len(alpha_tokens))
        single_char_ratio = sum(1 for token in alpha_tokens if len(token) == 1) / max(
            1, len(alpha_tokens)
        )
        alnum_mix_ratio = sum(
            1
            for token in alpha_tokens
            if len(token) >= 4 and re.search(r"[A-Za-zÀ-ÿ]", token) and re.search(r"\d", token)
        ) / max(1, len(alpha_tokens))

        if no_vowel_ratio >= 0.18:
            warnings.append("garbled_no_vowel_token_ratio")
        if single_char_ratio >= 0.30:
            warnings.append("garbled_single_char_ratio")
        if alnum_mix_ratio >= 0.12:
            warnings.append("garbled_alnum_mix_ratio")

    weird_char_ratio = len(re.findall(r"[^\w\sÀ-ÿ.,;:!?()\[\]{}\-_/\\|%$#+=*'\"\n]", normalized)) / max(
        1,
        len(normalized),
    )
    if weird_char_ratio >= 0.04:
        warnings.append("garbled_symbol_density")

    return warnings


def _has_corruption_warning(warnings: List[str]) -> bool:
    """Return whether warnings include strong OCR corruption indicators."""
    corruption_flags = {
        "garbled_no_vowel_token_ratio",
        "garbled_single_char_ratio",
        "garbled_alnum_mix_ratio",
        "garbled_symbol_density",
    }
    return any(warning in corruption_flags for warning in warnings)


def _has_severe_structure_warning(warnings: List[str]) -> bool:
    """Return whether warning list contains fail-critical structural issues."""
    severe = {
        "empty_output",
        "very_short_output",
        "isolated_table_row",
        "replacement_character_present",
        "garbled_no_vowel_token_ratio",
        "garbled_single_char_ratio",
        "garbled_alnum_mix_ratio",
        "garbled_symbol_density",
    }
    return any(warning in severe for warning in warnings)


def _extract_numeric_tokens(text: str) -> List[str]:
    """Extract numeric tokens useful for medical consistency checks."""
    return re.findall(r"\b\d+(?:[.,]\d+)?\b", text)


def _extract_date_tokens(text: str) -> List[str]:
    """Extract common date formats from text."""
    return re.findall(
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b",
        text,
    )


def _medical_validation_warnings(reference_text: str, candidate_text: str) -> List[str]:
    """Compare candidate output against reference text for critical drift.

    Args:
        reference_text: Baseline text used as factual anchor.
        candidate_text: Candidate corrected text.

    Returns:
        Validation warnings for numeric/date loss and short outputs.
    """
    warnings: List[str] = []
    ref = reference_text.strip()
    cand = candidate_text.strip()

    if not cand:
        return ["medical_validator_empty_output"]

    ref_nums = _extract_numeric_tokens(ref)
    cand_nums = _extract_numeric_tokens(cand)
    if ref_nums:
        overlap = sum(1 for token in ref_nums if token in cand_nums)
        ratio = overlap / max(1, len(ref_nums))
        if ratio < 0.75:
            warnings.append(f"medical_validator_numeric_mismatch:{ratio:.2f}")

    ref_dates = _extract_date_tokens(ref)
    cand_dates = _extract_date_tokens(cand)
    if ref_dates and not cand_dates:
        warnings.append("medical_validator_date_loss")

    if len(cand) < 24:
        warnings.append("medical_validator_too_short")

    return warnings


def _score_markdown_confidence(text: str, source: str, warnings: List[str]) -> float:
    """Compute bounded confidence score for markdown output quality."""
    if not text.strip():
        return 0.0

    word_count = _word_count(text)
    confidence = 0.90 if source == "text-layer" else 0.84
    confidence += min(0.05, len(text) / 8000.0)
    confidence += min(0.05, word_count / 900.0)
    confidence -= 0.08 * len(warnings)
    if _has_severe_structure_warning(warnings):
        confidence -= 0.05
    if _has_corruption_warning(warnings):
        confidence -= 0.22
    if re.search(r"\[Page \d+ failed:", text):
        confidence = 0.0
    return round(max(0.0, min(confidence, 0.99)), 3)


def _should_use_visual_qa(
    confidence: float, warnings: List[str], source: str, cfg: PipelineConfig
) -> bool:
    """Decide whether image-to-text output should enter visual QA stage."""
    if not cfg.enable_visual_qa:
        return False
    if source == "text-layer" and cfg.medical_strict and cfg.llm_enabled:
        return True
    if _has_corruption_warning(warnings):
        return True
    if source == "text-layer":
        return confidence < cfg.qa_confidence_threshold and _has_severe_structure_warning(warnings)
    return confidence < cfg.qa_confidence_threshold or _has_severe_structure_warning(warnings)


def _should_use_cleanup(
    confidence: float, warnings: List[str], source: str, cfg: PipelineConfig
) -> bool:
    """Decide whether output should enter NLP cleanup stage."""
    if not cfg.enable_nlp_review:
        return False
    if source == "text-layer" and cfg.medical_strict and cfg.llm_enabled:
        return True
    if _has_corruption_warning(warnings):
        return True
    if source == "text-layer":
        return confidence < cfg.cleanup_confidence_threshold and _has_severe_structure_warning(
            warnings
        )
    return confidence < cfg.cleanup_confidence_threshold and _has_severe_structure_warning(warnings)


_DISCOVERY_CACHE: Dict[str, Tuple[float, List[DiscoveredModel], List[BenchmarkSignal], List[str]]] = {}


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
    raw_provider_name = (cfg.llm_provider_name or "").strip() or get_env("LLM_PROVIDER_NAME", "").strip()

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
    return draft_text


def _normalize_local_ocr_language_token(token: str) -> str:
    """Normalize local OCR language aliases to canonical short codes."""
    normalized = token.strip().lower().replace("-", "_")
    aliases = {
        "": "",
        "pt": "pt",
        "por": "pt",
        "pt_br": "pt",
        "ptbr": "pt",
        "portuguese": "pt",
        "en": "en",
        "eng": "en",
        "english": "en",
    }
    return aliases.get(normalized, normalized)


def _local_ocr_language_tokens(lang: str) -> List[str]:
    """Split and normalize language configuration into unique tokens."""
    raw_tokens = [token for token in re.split(r"[,+;|\s/]+", (lang or "").strip()) if token]
    normalized_tokens: List[str] = []
    for token in raw_tokens:
        normalized = _normalize_local_ocr_language_token(token)
        if normalized and normalized not in normalized_tokens:
            normalized_tokens.append(normalized)
    if not normalized_tokens:
        return ["pt", "en"]
    return normalized_tokens


def _easyocr_language_list(lang: str) -> List[str]:
    """Return EasyOCR-compatible language list from configuration string."""
    language_list = [token for token in _local_ocr_language_tokens(lang) if token in {"pt", "en"}]
    if not language_list:
        return ["pt", "en"]
    return language_list


def _tesseract_language(lang: str) -> str:
    """Convert normalized language tokens to Tesseract language code string."""
    tokens = _local_ocr_language_tokens(lang)
    if not tokens:
        tokens = ["pt", "en"]
    mapped: List[str] = []
    for token in tokens:
        if token == "pt":
            mapped.append("por")
        elif token == "en":
            mapped.append("eng")
        else:
            mapped.append(token)
    return "+".join(mapped)


def _prepare_local_ocr_image(image_b64: str, cfg: PipelineConfig) -> Tuple[Any, np.ndarray]:
    """Decode and preprocess OCR image payload for local engines."""
    from PIL import Image  # type: ignore[import-not-found]

    image_bytes = base64.b64decode(image_b64)
    image_bytes = _preprocess_ocr_image(
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
                    try:
                        points.append((float(point[0]), float(point[1])))
                    except Exception:
                        continue
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


def _call_tesseract_local_ocr(image: Any, lang: str, psm: int) -> Tuple[str, float, List[str]]:
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


def _call_local_ocr(
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
                ocr_warnings = ["local_ocr_provider", "local_ocr_easyocr", "local_ocr_reconstructed"]
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
                    confidence=round(raw_confidence / 100.0, 3),
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
                    confidence=round(raw_confidence / 100.0, 3),
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
                    confidence=confidence,
                    warnings=tesseract_warnings,
                )

            provider_errors.append(f"unsupported_local_ocr_engine:{engine_name}")
        except Exception as exc:
            provider_errors.append(f"{engine_name}_failed:{exc}")

    raise RuntimeError("local_ocr_unavailable:" + ";".join(provider_errors or ["unknown"]))


def _score_local_ocr_confidence(text: str, local_confidence: float, warnings: List[str]) -> float:
    """Blend heuristic markdown score with engine-provided local OCR confidence."""
    heuristic = _score_markdown_confidence(text, "local-ocr", warnings)
    if local_confidence <= 0:
        return heuristic
    return round(max(0.0, min(0.99, heuristic * 0.6 + local_confidence * 0.4)), 3)


def _needs_reprocess_block(page_index: int, confidence: float, min_confidence: float) -> str:
    """Build explicit fail-closed block text for low-confidence page output."""
    return (
        f"\n[Page {page_index + 1} status: needs_reprocess; "
        f"confidence {confidence:.3f} below minimum {min_confidence:.3f}]\n"
    )


async def _enforce_fail_closed_policy(
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


async def _enforce_medical_strict_review(
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


async def _call_zai_vision(
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

    warning_hint = f";discovery_warnings={','.join(discovery_warnings[:2])}" if discovery_warnings else ""
    raise RuntimeError(f"all_routed_models_failed:{last_error}{warning_hint}")


async def _call_gemini_visual_qa(
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


async def _call_openrouter_nlp(
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


async def _process_page(
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
                cached_file = _cache_path(
                    cache_dir,
                    "text",
                    page_index,
                    f"{doc_fingerprint}:{len(inspection.text)}:{inspection.word_count}",
                )
                if cfg.cache_enabled and cached_file.exists() and not (
                    cfg.medical_strict and cfg.llm_enabled
                ):
                    progress.update(1)
                    cached_text = cached_file.read_text(encoding="utf-8")
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
                    qa_image_b64 = _get_rendered_page_image_b64(
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
                    cached_file.write_text(text, encoding="utf-8")

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
                f"{doc_fingerprint}:{cfg.zoom_matrix}:{cfg.max_image_side_px}:"
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

            cached_file: Optional[Path] = None
            cache_source = "vision-ocr"
            if cfg.cache_enabled:
                if local_cached_file.exists():
                    cached_file = local_cached_file
                    cache_source = "local-ocr"
                elif vision_cached_file.exists():
                    cached_file = vision_cached_file
                    cache_source = "vision-ocr"

            if cfg.cache_enabled and cached_file is not None and cached_file.exists():
                progress.update(1)
                cached_text = cached_file.read_text(encoding="utf-8")
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

            image_b64 = _get_rendered_page_image_b64(
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
            )
            selected_source = "vision-ocr"
            text = ""
            warnings: List[str] = []
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
                        local_result = _call_local_ocr(
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
                            warnings = local_warnings
                            confidence = local_confidence
                            selected_source = "local-ocr"
                            break

                        text = local_text
                        warnings = local_warnings + [
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
                                current_image = _get_rendered_page_image_b64(
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
                        warnings = _validate_markdown_text(text)
                        if cfg.scanned_fast:
                            warnings.append("scanned_fast_profile")
                        if remote_last_exc is not None:
                            warnings.append("ocr_fallback_used")
                        confidence = _score_markdown_confidence(text, "vision-ocr", warnings)
                        selected_source = "vision-ocr"
                        task_kind = classify_task_kind(selected_source, warnings, confidence)
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
                                    [
                                        f"routing:{line}"
                                        for line in route_decision.debug_lines[:8]
                                    ]
                                )
                            routing_notes.extend(
                                [f"routing_warning:{item}" for item in route_warnings[:4]]
                            )
                        break

            if not text:
                raise RuntimeError(
                    "all_ocr_providers_failed:" + ";".join(provider_errors or ["unknown"])
                )

            if _should_use_visual_qa(confidence, warnings, selected_source, cfg):
                text = await _call_gemini_visual_qa(session, cfg, image_b64, text)
                text = _normalize_markdown_document(text)
                warnings = _validate_markdown_text(text)
                confidence = _score_markdown_confidence(text, selected_source, warnings)
                qa_applied = True

            if _should_use_cleanup(confidence, warnings, selected_source, cfg):
                text = await _call_openrouter_nlp(session, cfg, text)
                text = _normalize_markdown_document(text)
                warnings = _validate_markdown_text(text)
                confidence = _score_markdown_confidence(text, selected_source, warnings)
                cleanup_applied = True

            if cfg.llm_enabled and _has_corruption_warning(warnings):
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
                    warnings = repaired_warnings + ["post_post_cleanup_applied"]
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
                        try:
                            strict_image = _get_rendered_page_image_b64(
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
                            )
                            strict_text = await _call_zai_vision(
                                session,
                                replace(cfg, ocr_retries=max(2, cfg.ocr_retries)),
                                strict_image,
                            )
                        except Exception as strict_exc:
                            warnings.append(f"strict_recovery_failed:{strict_exc}")
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
                            warnings = strict_warnings
                            confidence = strict_confidence

                        if confidence >= cfg.min_acceptable_confidence:
                            break

                if confidence < cfg.min_acceptable_confidence:
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
                        image_b64=image_b64,
                        source=selected_source,
                        text=text,
                        confidence=confidence,
                        warnings=warnings,
                    )

            if cfg.llm_routing_debug and routing_notes:
                warnings.extend(routing_notes)

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
                warnings=warnings,
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


def _render_page_image_b64(
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


def _get_rendered_page_image_b64(
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
    )
    cached_path = _render_cache_path(cache_dir, page_index, payload)
    if cache_enabled and cached_path.exists():
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


async def run_pipeline(pdf_file: Path, cfg: PipelineConfig) -> Tuple[str, Dict[str, Any]]:
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

    cache_root = pdf_file.parent / ".cache"
    cache_dir = cache_root / pdf_file.stem
    if cfg.cache_enabled:
        cache_dir.mkdir(parents=True, exist_ok=True)

    timeout = aiohttp.ClientTimeout(total=cfg.timeout_seconds)
    semaphore = asyncio.Semaphore(max(1, effective_cfg.concurrency))

    progress = tqdm(total=page_count, ncols=90, desc=f"Processing {pdf_file.name}")
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [
            _process_page(
                session, effective_cfg, semaphore, doc[i], cache_dir, doc_fingerprint, progress
            )
            for i in range(page_count)
        ]
        results = await asyncio.gather(*tasks)
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
            "llm_base_url": (effective_cfg.llm_base_url or get_env("LLM_BASE_URL", "")),
            "llm_routing_mode": effective_cfg.llm_routing_mode,
            "llm_routing_debug": effective_cfg.llm_routing_debug,
        },
    }
    return markdown_text, report


def render_html(markdown_text: str) -> str:
    """Convert markdown output to minimal styled HTML document."""
    import markdown  # type: ignore[import-not-found]

    body = markdown.markdown(markdown_text, extensions=["tables", "sane_lists"])
    return f"""<!DOCTYPE html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"UTF-8\" />
  <title>Laudo Processado</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; color: #222; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; table-layout: fixed; margin: 16px 0; }}
    th, td {{ border: 1px solid #ccc; padding: 6px; word-wrap: break-word; }}
    th {{ background: #f0f0f0; }}
  </style>
</head>
<body>{body}</body>
</html>
"""


def process_document(
    pdf_file: Path,
    output_dir: Path,
    suffix: str,
    html_enabled: bool,
    cfg: PipelineConfig,
) -> Path:
    """Process one PDF and persist markdown/report/optional HTML artifacts.

    Args:
        pdf_file: Source PDF path.
        output_dir: Target output directory.
        suffix: Markdown filename suffix.
        html_enabled: Whether to persist HTML output.
        cfg: Runtime pipeline configuration.

    Returns:
        Path to generated markdown file.
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

    if html_enabled:
        html_file = output_dir / f"{pdf_file.stem}.canonical.html"
        html_file.write_text(render_html(markdown_text), encoding="utf-8")

    elapsed = time.time() - started
    print(f"[OK] {pdf_file.name} -> {md_file.name} ({elapsed:.1f}s)")
    return md_file


def platform_is_windows() -> bool:
    """Return whether runtime OS is Windows."""
    return os.name == "nt"
