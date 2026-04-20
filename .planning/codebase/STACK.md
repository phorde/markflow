# Stack

**Mapped:** 2026-04-19

## Runtime

- Python 3.10+ package named `markflow`.
- CLI entrypoint: `app.py` -> `markflow.cli:main`.
- Local development shell observed on Windows PowerShell.

## Core Dependencies

- `aiohttp` for async HTTP calls to OpenAI-compatible providers.
- `PyMuPDF` (`fitz`) for PDF reading and rendering.
- `Pillow`, `numpy` for image preprocessing and OCR payload handling.
- `easyocr`, `rapidocr-onnxruntime`, `pytesseract` for local OCR engines.
- `markdown`, `bleach` for HTML generation and sanitization.
- `questionary`, `rich` for interactive terminal setup.
- `tqdm` for progress reporting.

## Development Dependencies

- `pytest`, `pytest-cov`, `pytest-asyncio`, `pytest-mock`.
- `hypothesis` for property/fuzz tests.
- `coverage[toml]` for coverage gates.
- `ruff`, `black`, `flake8`, `mypy` for static quality gates.

## Configuration

- Runtime config comes from CLI args plus environment variables.
- Environment sample: `.env.example`.
- Tool config: `pyproject.toml` and `.flake8`.
- GSD config: `.planning/config.json`.

## Gates

- Compile: `python -m compileall -q app.py markflow tests`
- Lint/format: `ruff`, `black --check`, `flake8`
- Typecheck: `mypy markflow`
- Tests: marker-specific pytest plus full coverage run
