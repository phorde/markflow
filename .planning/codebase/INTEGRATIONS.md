# Integrations

**Mapped:** 2026-04-19

## LLM Providers

- Provider-agnostic client: `markflow/llm_client.py`.
- Provider presets: `markflow/provider_presets.py`.
- Supported provider families include OpenAI-compatible endpoints, Anthropic, Gemini, OpenRouter, and Z.AI.
- Provider credentials are resolved from provider-specific environment variables or `LLM_API_KEY`.

## Model Discovery and Benchmarks

- Model discovery uses `/v1/models` or provider-specific equivalent endpoint candidates.
- OCR benchmark ingestion lives in `markflow/benchmark_ingestion.py`.
- Model scoring and ranking live in `markflow/model_selection.py`.
- Routing policy lives in `markflow/routing.py`.

## OCR Engines

- EasyOCR via cached reader creation.
- RapidOCR via cached `RapidOCR` instance.
- Tesseract via `pytesseract`, optionally configured by `TESSERACT_CMD`.

## Filesystem Outputs

- Markdown output: `*.canonical.md`.
- Report output: `*.canonical.report.json`.
- Optional sanitized HTML output: `*.canonical.html`.
- Cache output: `.cache/<pdf-stem>/`, disabled by default in strict sensitive mode.

## GSD

- Local Codex GSD runtime: `.codex/`.
- Planning and traceability: `.planning/`.
