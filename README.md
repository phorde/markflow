# MarkFlow

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](#installation)
[![License](https://img.shields.io/badge/license-MIT-black)](LICENSE)

**MarkFlow** is a provider-agnostic, OCR-first extraction pipeline that converts mixed-quality PDFs into structured Markdown documents and auditable JSON reports. It combines dynamic model discovery, benchmark-driven selection, and intelligent OCR routing to deliver production-grade document extraction.

## Key Features

- **OCR-First Architecture**: Prioritizes document understanding quality through benchmark-driven model selection
- **Provider Agnostic**: Works with OpenAI, Anthropic, Gemini, OpenRouter, Z.AI, and custom OpenAI-compatible endpoints
- **Interactive Setup (TUI)**: User-friendly terminal interface for model discovery, configuration, and recommendations
- **Local OCR Support**: EasyOCR, RapidOCR, and Tesseract with intelligent fallback routing
- **Audit-Ready Output**: Detailed JSON reports with confidence scores, extraction metadata, and processing decisions
- **Medical-Grade Quality**: Fail-closed validation mode for regulated document workflows

## Table of Contents

- [Quick Start](#quick-start)
- [OCR-First Philosophy](#ocr-first-philosophy)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [CLI](#cli)
  - [Interactive Mode (TUI)](#interactive-mode-tui)
  - [Execution Modes](#execution-modes)
  - [Routing Modes](#routing-modes)
- [Benchmark-Driven Model Selection](#benchmark-driven-model-selection)
- [Output Formats](#output-formats)
- [Security](#security)
- [Development](#development)
- [License](#license)

## Quick Start

```bash
# Clone and setup
git clone https://github.com/yourusername/markflow.git
cd markflow
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run interactive setup
python app.py --tui

# Extract a document
python app.py --input ./documents --output-dir ./out --routing-mode balanced
```

## OCR-First Philosophy

MarkFlow is optimized for document transcription and OCR-extraction workloads where OCR quality is the primary determinant of downstream quality.

**Design Priorities:**

1. OCR/document understanding quality as primary signal
2. Structured extraction quality for forms, tables, and PDF artifacts
3. Long-context stability for multi-page parsing
4. Cost and latency as secondary optimization signals

## Architecture

```
app.py                           # Slim entrypoint
markflow/
├── cli.py                       # CLI argument parsing and workflow orchestration
├── pipeline.py                  # Core OCR pipeline and page processing logic
├── tui.py                       # Interactive terminal UI for setup and recommendations
├── llm_client.py                # OpenAI-compatible provider abstraction
├── llm_types.py                 # Shared typed contracts and data structures
├── benchmark_ingestion.py       # OCR benchmark data ingestion and normalization
├── model_selection.py           # OCR-aware model ranking and scoring
├── routing.py                   # Task-aware routing and escalation logic
└── provider_presets.py          # Provider-specific configuration presets
```

**Architectural Separation:**

- **OCR Core**: Document analysis, confidence scoring, page-level routing
- **LLM Abstraction**: Provider-agnostic client with async support
- **Benchmarking**: Canonical OCR benchmark integration and model normalization
- **Selection Engine**: Scoring, ranking, and recommendation with explainability
- **Routing**: Task classification and intelligent escalation
- **TUI Layer**: Interactive setup, discovery, and user guidance

## Installation

### Prerequisites

- Python 3.10+
- Optional: Tesseract binary for local OCR (Windows: `choco install tesseract` or download MSI)

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

MarkFlow loads configuration from environment variables. Copy `.env.example` to `.env` and configure:

### Core Settings

- **`LLM_API_KEY`** (required) – API key for your LLM provider
- **`LLM_BASE_URL`** (required) – OpenAI-compatible endpoint base URL
- **`LLM_PROVIDER_PRESET`** (optional) – Preset: `custom`, `openai`, `anthropic`, `gemini`, `openrouter`, `z-ai`
- **`LLM_PROVIDER_NAME`** (optional) – Human-readable provider label
- **`LLM_MODEL`** (optional) – Fixed model ID (disables dynamic selection if set)

### Provider-Specific Keys

The application auto-detects provider via preset and looks for official environment variables:

| Provider | Variable | Format |
|----------|----------|--------|
| OpenAI | `OPENAI_API_KEY` | Bearer token |
| Anthropic | `ANTHROPIC_API_KEY` | API key with `x-api-key` header |
| Gemini | `GEMINI_API_KEY` | Bearer token |
| OpenRouter | `OPENROUTER_API_KEY` | Bearer token |
| Z.AI | `ZAI_API_KEY` | Bearer token |

Fallback: Uses `LLM_API_KEY` if provider-specific variable is not set.

### Optional Settings

- **`TESSERACT_CMD`** – Path to Tesseract binary (Windows: `C:\Program Files\Tesseract-OCR\tesseract.exe`)
- **`LLM_ZAI_PLAN`** – Z.AI plan: `general` or `coding` (default: `general`)

## Usage

### CLI

Extract a single document:

```bash
python app.py --input ./documents/report.pdf --output-dir ./out
```

Batch extract with explicit provider and routing:

```bash
python app.py \
  --input ./documents \
  --output-dir ./out \
  --llm-provider-preset openai \
  --llm-base-url "https://api.openai.com" \
  --routing-mode high-accuracy-ocr
```

Extract with Z.AI coding endpoint:

```bash
python app.py \
  --input ./documents \
  --output-dir ./out \
  --llm-provider-preset z-ai \
  --zai-plan coding \
  --routing-mode balanced
```

Force a specific model (bypass dynamic selection):

```bash
python app.py --input ./documents --output-dir ./out --llm-model gpt-4-vision
```

List all available CLI options:

```bash
python app.py --help
```

### Interactive Mode (TUI)

Launch the interactive setup wizard:

```bash
python app.py --tui
```

The TUI guides you through:

1. **API Key Input** – Securely enter credentials (input is masked)
2. **Provider Selection** – Choose from presets or custom endpoint
3. **Model Discovery** – Auto-fetch available models from `/v1/models`
4. **OCR Benchmark Ingestion** – Score models against OCRBench v2 signals
5. **Routing Mode Selection** – Choose optimization strategy
6. **Recommendation Output** – View why each model was ranked, with tradeoff analysis

### Execution Modes

Select with `--mode`:

| Mode | Use Case |
|------|----------|
| `auto` | Adaptive behavior for mixed document quality (default) |
| `fast` | Speed-optimized; minimal post-processing for high-throughput |
| `quality` | Fail-closed with strict confidence enforcement and recovery |
| `local` | No remote LLM calls; text extraction and local OCR only |
| `remote` | Remote-first with intelligent fallback to local methods |

### Routing Modes

Select with `--routing-mode`:

| Mode | Optimization | Best For |
|------|--------------|----------|
| `fast` | Lowest latency and cost | Cost-sensitive, high-volume batches |
| `balanced` | OCR quality ↔ cost ↔ speed | General-purpose extraction |
| `high-accuracy-ocr` | Maximum document understanding quality | Medical, legal, regulated documents |

## Benchmark-Driven Model Selection

MarkFlow uses the canonical OCRBench v2 benchmark to inform model selection:

**Canonical Benchmark Source:** https://99franklin.github.io/ocrbench_v2/

**Selection Strategy:**

1. Discover available models from provider via `/v1/models`
2. Normalize model IDs against benchmark dataset
3. Score on OCR quality, structured extraction, and long-context signals
4. Weight by routing mode (e.g., `high-accuracy-ocr` emphasizes document understanding)
5. Rank and return with explainable reasoning

**Confidence Handling:**

- Models with strong benchmark evidence → high confidence in ranking
- Models without benchmark data → conservative fallback scoring with warnings
- Missing fields → heuristic proxies (context length, inference latency)

## Output Formats

### Markdown Output

`<filename>.canonical.md` – Clean, readable document in Markdown format.

```markdown
# Document Title

## Section 1

Content extracted and formatted as structured Markdown.

## Tables

| Column 1 | Column 2 |
|----------|----------|
| Value    | Value    |
```

### JSON Report

`<filename>.canonical.report.json` – Detailed audit trail and metadata.

```json
{
  "document_id": "report_001",
  "processing_summary": {
    "total_pages": 10,
    "extraction_confidence": 0.94,
    "llm_review_required_pages": 2,
    "llm_review_passed_pages": 1,
    "needs_reprocess_pages": 1
  },
  "pages": [
    {
      "page_number": 1,
      "status": "accepted",
      "confidence": 0.98,
      "extraction_source": "text-layer",
      "cache_hit": false
    }
  ]
}
```

## Security

### API Key Handling

MarkFlow implements strict API key security:

1. **No Persistence**: API key is never written to disk, logs, or output files
2. **Masked Input**: TUI masks API key entry in terminal
3. **Memory-Only**: Credentials kept in process memory only
4. **No CLI Arguments**: API key is never accepted as CLI argument (prevents shell history leaks)
5. **Error Redaction**: Error messages redact token-like values
6. **HTTPS Enforced**: LLM base URLs restricted to HTTPS (HTTP allowed only on `localhost`)
7. **Redirect Disabled**: Authenticated requests block redirects to prevent credential forwarding

### Important Limitations

While MarkFlow implements best-effort API key handling, no software can guarantee 100% security under every threat model. Use in secure environments and follow your organization's credential management policies.

## Development

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Quality Gates

Before submitting a PR, run:

```bash
# Syntax validation
python -m py_compile app.py markflow/*.py

# Code formatting
python -m black .

# Linting
python -m flake8 app.py markflow

# Type checking
python -m mypy markflow
```

### Standards

- **PEP 8** compliance with 100-char line length
- **Docstrings** required for all public functions (PEP 257)
- **Provider Neutrality**: No vendor-specific assumptions in core layers
- **Architecture Boundaries**: Clear separation across OCR, LLM, benchmarking, routing, and TUI layers
- **Data Privacy**: Never commit personal or sensitive sample documents

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development workflow and PR guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.

---

**Need Help?**

- Check [EXECUTION_MODES.md](EXECUTION_MODES.md) for detailed mode and routing documentation
- See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup
- Open an issue with reproduction steps and MarkFlow version (`cat VERSION`)
