# Architecture

**Mapped:** 2026-04-19

## Entry Points

- `app.py` is a thin script entrypoint.
- `markflow/cli.py` parses arguments, applies mode profiles, builds `PipelineConfig`, discovers PDFs, and calls `process_document`.
- `markflow/pipeline.py` orchestrates page processing, OCR, review, cache, report, and output persistence.

## Core Flow

1. CLI builds a `PipelineConfig`.
2. `discover_pdfs` resolves input files.
3. `process_document` calls `run_pipeline`.
4. `run_pipeline` opens the PDF, computes fingerprint, applies effective cache policy, and processes pages in bounded batches.
5. `_process_page` chooses text-layer, local OCR, or remote OCR paths.
6. Optional QA/review stages update text, warnings, confidence, and status.
7. Report summary derives final document status.
8. Markdown/report/HTML are written.

## Extracted Subsystems

- `markflow/extraction/page_analysis.py`: pure text-layer and Markdown normalization helpers.
- `markflow/extraction/review.py`: warnings, confidence scoring, strict review policy helpers.
- `markflow/extraction/local_ocr.py`: local OCR confidence/language helpers.
- `markflow/extraction/rendering.py`: OCR image preprocessing and HTML rendering/sanitization.
- `markflow/extraction/cache.py`: cache key/path/TTL helpers.
- `markflow/extraction/reporting.py`: final status and observability summary helpers.
- `markflow/extraction/orchestrator.py`: batch and effective cache policy helpers.

## Important Invariants

- OCR confidence is canonicalized to `0.0..1.0`.
- `medical_strict` must prefer fail-closed results over permissive success.
- HTML output must pass sanitization after Markdown rendering.
- Sensitive cache persistence is opt-in for strict mode.
- External provider failures must not leak secrets.
