# Contributing

Thank you for contributing to MarkFlow.

## Development Setup

1. Create and activate a virtual environment.
2. Install runtime dependencies:

```bash
pip install -r requirements.txt
```

3. Copy environment template:

```bash
cp .env.example .env
```

## Engineering Standards

- Follow PEP 8 and keep functions cohesive and auditable.
- Every function must have a clear PEP 257 docstring.
- Preserve provider-neutral design: avoid vendor-specific assumptions in core layers.
- Keep architecture boundaries clear across OCR core, LLM abstraction, benchmark ingestion, selection, routing, and TUI layers.
- Avoid introducing sensitive sample documents or personal data in commits.

## Quality Gates

Run checks before opening a PR:

```bash
python -m py_compile app.py markflow/cli.py markflow/pipeline.py markflow/tui.py markflow/llm_client.py markflow/benchmark_ingestion.py markflow/model_selection.py markflow/routing.py
python -m black --check .
python -m flake8 app.py markflow
python -m mypy markflow
```

## Pull Request Guidelines

- Keep PRs focused and explain risk/impact.
- Update README for CLI/TUI behavior changes.
- Update dependency manifests consistently when packages change.
- Document routing/selection rationale for LLM-related changes.
