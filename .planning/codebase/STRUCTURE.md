# Structure

**Mapped:** 2026-04-19

## Root Files

- `app.py`: console entrypoint.
- `README.md`: user documentation.
- `EXECUTION_MODES.md`: execution mode notes.
- `requirements.txt`: runtime dependencies.
- `requirements-dev.txt`: development dependencies.
- `pyproject.toml`: project metadata and tool config.
- `.github/workflows/ci.yml`: CI gates.

## Package

- `markflow/cli.py`: CLI workflow.
- `markflow/pipeline.py`: orchestration and compatibility wrappers.
- `markflow/tui.py`: interactive setup.
- `markflow/llm_client.py`: provider client.
- `markflow/llm_types.py`: typed contracts.
- `markflow/model_selection.py`: model ranking.
- `markflow/routing.py`: task routing.
- `markflow/benchmark_ingestion.py`: benchmark ingestion.
- `markflow/security.py`: secret redaction.
- `markflow/extraction/`: extracted pure/helper subsystems.

## Tests

- `tests/unit/`: isolated policy, helper, routing, selection, CLI, TUI, and LLM tests.
- `tests/integration/`: multi-component document flow tests.
- `tests/functional/`: end-to-end output tests.
- `tests/spec/`: GSD requirement/spec/test traceability tests.

## Planning

- `.codex/`: local GSD runtime for Codex.
- `.planning/`: project context, requirements, roadmap, specs, phase docs, and codebase map.
