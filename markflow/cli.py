"""CLI and orchestration entrypoint for ExtratorLaudos."""

from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import (
    PipelineConfig,
    _autotune_for_machine,
    discover_pdfs,
    process_document,
)
from .provider_presets import list_provider_preset_keys
from .tui import run_interactive_setup


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the extraction pipeline.

    Returns:
        Parsed argparse namespace with runtime options.
    """
    parser = argparse.ArgumentParser(
        description="Production-ready PDF extraction pipeline for structured markdown output."
    )
    parser.add_argument("--input", default=".", help="PDF file or directory containing PDFs.")
    parser.add_argument(
        "--output-dir",
        default="out",
        help="Directory where output markdown/report files are written.",
    )
    parser.add_argument("--suffix", default=".canonical.md", help="Suffix for markdown outputs.")
    parser.add_argument("--html", action="store_true", help="Also generate HTML output per PDF.")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--zoom", type=float, default=1.5)
    parser.add_argument("--max-image-side", type=int, default=1700)
    parser.add_argument("--rgb-ocr", action="store_true")
    parser.add_argument("--scanned-fast", action="store_true")
    parser.add_argument("--ocr-retries", type=int, default=2)
    parser.add_argument("--qa-retries", type=int, default=1)
    parser.add_argument("--cleanup-retries", type=int, default=1)
    parser.add_argument("--text-min-chars", type=int, default=40)
    parser.add_argument("--qa-confidence-threshold", type=float, default=0.82)
    parser.add_argument("--cleanup-confidence-threshold", type=float, default=0.68)
    parser.add_argument("--min-acceptable-confidence", type=float, default=0.88)
    parser.add_argument("--remote-first", action="store_true")
    parser.add_argument("--disable-local-ocr", action="store_true")
    parser.add_argument("--local-ocr-lang", default="pt,en")
    parser.add_argument(
        "--local-ocr-engine",
        default="easyocr",
        choices=["easyocr", "rapidocr", "tesseract", "auto"],
    )
    parser.add_argument("--local-min-confidence", type=float, default=0.84)
    parser.add_argument("--local-ocr-psm", type=int, default=6)
    parser.add_argument("--disable-ocr-preprocess", action="store_true")
    parser.add_argument("--no-autocontrast", action="store_true")
    parser.add_argument("--no-sharpen", action="store_true")
    parser.add_argument("--ocr-binarize-threshold", type=int, default=0)
    parser.add_argument("--disable-render-cache", action="store_true")
    parser.add_argument("--medical-strict", action="store_true")
    parser.add_argument("--strict-recovery-attempts", type=int, default=1)
    parser.add_argument("--allow-single-pass-llm-review", action="store_true")
    parser.add_argument("--disable-strict-llm-required", action="store_true")
    parser.add_argument("--no-text-layer", action="store_true")
    parser.add_argument("--disable-visual-qa", action="store_true")
    parser.add_argument("--disable-nlp-review", action="store_true")
    parser.add_argument("--disable-cache", action="store_true")
    parser.add_argument("--no-autotune-local", action="store_true")
    parser.add_argument(
        "--llm-base-url",
        default="",
        help="Base URL for OpenAI-compatible provider (e.g. https://api.openai.com).",
    )
    parser.add_argument(
        "--llm-provider-preset",
        choices=list_provider_preset_keys(),
        default="custom",
        help="Known provider preset for automatic base URL configuration.",
    )
    parser.add_argument(
        "--zai-plan",
        choices=["general", "coding"],
        default="general",
        help="Z.AI endpoint plan when llm-provider-preset is z-ai.",
    )
    parser.add_argument(
        "--llm-provider-name",
        default="",
        help="Optional provider label shown in routing/debug reports.",
    )
    parser.add_argument(
        "--llm-model",
        default="",
        help="Optional fixed model id. If omitted, the OCR-aware selector chooses dynamically.",
    )
    parser.add_argument(
        "--routing-mode",
        choices=["fast", "balanced", "high-accuracy-ocr"],
        default="balanced",
        help="Routing objective for OCR tasks.",
    )
    parser.add_argument(
        "--routing-debug",
        action="store_true",
        help="Emit routing decision details into page warnings and summary output.",
    )
    parser.add_argument(
        "--llm-discovery-timeout",
        type=int,
        default=8,
        help="Timeout in seconds for /v1/models and benchmark ingestion requests.",
    )
    parser.add_argument(
        "--disable-llm",
        action="store_true",
        help="Disable all remote LLM calls and keep extraction local/text-layer only.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "fast", "quality", "local", "remote"],
        default="auto",
        help="Execution profile: auto (adaptive), fast (speed), quality (accuracy), local (no remote), remote (remote-first).",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch interactive terminal setup for selecting mode and key options.",
    )
    return parser.parse_args()


def apply_mode_profile(args: argparse.Namespace) -> argparse.Namespace:
    """Apply a high-level mode profile over low-level flags.

    Execution profiles:
    - auto: Adaptive mode with intelligent routing (default)
    - fast: Speed-optimized for high-throughput batches
    - quality: Quality/accuracy-focused with fail-closed safeguards
    - local: Local extraction only; no remote OCR or LLM calls
    - remote: Remote-first with intelligent fallback to local

    Args:
        args: Parsed argument namespace to mutate.

    Returns:
        Updated namespace with mode-derived overrides.
    """
    mode = args.mode
    if mode == "fast":
        # Fast mode: optimize for throughput, minimal post-processing
        args.scanned_fast = True
        args.disable_visual_qa = True
        args.disable_nlp_review = True
        args.routing_mode = "fast"
    elif mode == "quality":
        # Quality mode: strict verification, fail-closed, high confidence threshold
        args.medical_strict = True
        args.min_acceptable_confidence = max(args.min_acceptable_confidence, 0.88)
        args.strict_recovery_attempts = max(args.strict_recovery_attempts, 1)
        args.routing_mode = "high-accuracy-ocr"
    elif mode == "remote":
        # Remote mode: prioritize remote OCR providers
        args.remote_first = True
    elif mode == "local":
        # Local mode: no remote calls, local-only extraction
        args.disable_visual_qa = True
        args.disable_nlp_review = True
        args.disable_strict_llm_required = True
        args.disable_llm = True
    # auto mode: no special flags, use defaults
    return args


def build_config(args: argparse.Namespace) -> PipelineConfig:
    """Build normalized runtime configuration from parsed CLI arguments.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Normalized PipelineConfig instance.
    """
    cfg = PipelineConfig(
        concurrency=max(1, args.concurrency),
        ocr_retries=max(1, args.ocr_retries),
        qa_retries=max(1, args.qa_retries),
        cleanup_retries=max(1, args.cleanup_retries),
        timeout_seconds=max(30, args.timeout),
        zoom_matrix=max(0.5, args.zoom),
        max_image_side_px=max(800, args.max_image_side),
        ocr_grayscale=not args.rgb_ocr,
        scanned_fast=args.scanned_fast,
        prefer_text_layer=not args.no_text_layer,
        text_min_chars=max(1, args.text_min_chars),
        qa_confidence_threshold=min(0.99, max(0.0, args.qa_confidence_threshold)),
        cleanup_confidence_threshold=min(0.99, max(0.0, args.cleanup_confidence_threshold)),
        min_acceptable_confidence=min(0.99, max(0.0, args.min_acceptable_confidence)),
        local_first=not args.remote_first,
        enable_local_ocr=not args.disable_local_ocr,
        local_ocr_engine=(args.local_ocr_engine or "easyocr").strip() or "easyocr",
        local_ocr_lang=(args.local_ocr_lang or "pt,en").strip() or "pt,en",
        local_min_confidence=min(0.99, max(0.0, args.local_min_confidence)),
        local_ocr_psm=max(1, min(13, args.local_ocr_psm)),
        enable_ocr_preprocess=not args.disable_ocr_preprocess,
        ocr_autocontrast=not args.no_autocontrast,
        ocr_sharpen=not args.no_sharpen,
        ocr_binarize_threshold=max(0, min(255, args.ocr_binarize_threshold)),
        cache_rendered_images=not args.disable_render_cache,
        medical_strict=args.medical_strict,
        strict_recovery_attempts=max(0, args.strict_recovery_attempts),
        strict_llm_required=not args.disable_strict_llm_required,
        llm_review_two_pass=not args.allow_single_pass_llm_review,
        enable_visual_qa=not args.disable_visual_qa,
        enable_nlp_review=not args.disable_nlp_review,
        cache_enabled=not args.disable_cache,
        llm_enabled=not args.disable_llm,
        llm_api_key="",
        llm_base_url=(args.llm_base_url or "").strip(),
        llm_provider_preset=(args.llm_provider_preset or "custom").strip(),
        llm_zai_plan=(args.zai_plan or "general").strip(),
        llm_provider_name=(args.llm_provider_name or "").strip(),
        llm_model=(args.llm_model or "").strip(),
        llm_routing_mode=(args.routing_mode or "balanced").strip(),
        llm_routing_debug=bool(args.routing_debug),
        llm_discovery_timeout_seconds=max(3, args.llm_discovery_timeout),
    )

    if not args.no_autotune_local:
        cfg = _autotune_for_machine(cfg)
    return cfg


def main() -> int:
    """Execute batch processing for discovered PDF files.

    Returns:
        Process exit code compatible with shell usage.
    """
    args = parse_args()
    if args.tui:
        args = run_interactive_setup(args)

    args = apply_mode_profile(args)
    cfg = build_config(args)

    try:
        pdfs = discover_pdfs(args.input)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    if not pdfs:
        print("[INFO] No PDF files found.")
        return 0

    output_dir = Path(args.output_dir)
    print(f"[INFO] Found {len(pdfs)} PDF file(s).")

    ok = 0
    failed = 0
    for pdf_file in pdfs:
        try:
            process_document(pdf_file, output_dir, args.suffix, args.html, cfg)
            ok += 1
        except Exception as exc:
            print(f"[FAIL] {pdf_file.name}: {exc}")
            failed += 1

    print(f"[DONE] Success: {ok} | Failed: {failed}")
    return 0 if failed == 0 else 2
