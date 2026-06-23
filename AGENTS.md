# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python CLI for building evidence-grounded Agent-ready data packages from URLs and PDFs.

- `src/agent_data/cli.py` contains the Typer command entry point.
- `src/agent_data/application/` holds orchestration (`ProcessDocument`, harness events, exit mapping).
- `src/agent_data/domain/` defines Pydantic models, schema validation, and pipeline errors.
- `src/agent_data/sources/`, `parsers/`, `extraction/`, `evidence/`, `quality/`, and `export/` implement the pipeline stages.
- `tests/unit/`, `tests/contract/`, `tests/e2e/`, and `tests/integration/` mirror behavior scope.
- `docs/` contains design notes and implementation plans.

## Build, Test, and Development Commands

Use `uv` for local development:

```powershell
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run agent-data --help
```

`uv sync --extra dev` installs runtime and developer dependencies. `pytest` runs the offline test suite by default. Ruff checks linting and formatting. The CLI help command verifies the package entry point.

For deployment-only installs, use:

```powershell
pip install -r requirements.txt
```

## Coding Style & Naming Conventions

Target Python 3.10+. Use 4-space indentation, type hints, and explicit dataclass or Pydantic models for structured data. Match the existing stage-oriented module boundaries instead of adding broad utility layers.

Ruff is configured in `pyproject.toml` with line length `100` and lint rules `E`, `F`, `I`, `UP`, and `B`. Prefer clear names such as `SourceResolver`, `Crawl4AIParser`, and `QualityGateRunner`.

## Testing Guidelines

Tests use `pytest`. Name files `test_*.py` and test functions `test_*`. Keep default tests offline; integration tests must remain gated by environment variables such as `RUN_LIVE_INTEGRATION=1`.

Add focused unit tests for deterministic domain logic, contract tests for external adapters, and e2e tests for complete pipeline behavior.

## Commit & Pull Request Guidelines

This repository currently has no commit history, so use a simple Conventional Commits style going forward, for example `feat: add crawl4ai parser` or `test: cover source resolver limits`.

Pull requests should include a short summary, verification commands run, linked issue or design note when applicable, and any configuration or secret-handling impact.

## Security & Configuration Tips

Do not commit `.env` or real API tokens. Keep deployable defaults in `.env.example` and runtime dependencies in `requirements.txt`. Crawl4AI, MinerU, and LLM endpoints should be configured through environment variables.
