# Agent-ready CLI MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved Python CLI that converts a URL or PDF into a traceable, evidence-grounded Agent-ready JSON/Markdown package with deterministic quality gates.

**Architecture:** A synchronous lightweight harness coordinates source resolution, a parser registry, OpenAI-compatible extraction, deterministic evidence verification, quality gates/scoring, and atomic export. Parser and LLM integrations are ports/adapters; all trust boundaries remain deterministic domain code.

**Tech Stack:** Python 3.10, Pydantic 2, Typer, HTTPX, Trafilatura, OpenAI-compatible HTTP API, pytest, Ruff.

---

## File map

- `pyproject.toml`: package metadata, runtime/dev dependencies, CLI entry point, pytest and Ruff configuration.
- `src/agent_data/config.py`: environment-backed immutable runtime configuration.
- `src/agent_data/domain/models.py`: source, parsed blocks, claims, evidence, quality, run and package models.
- `src/agent_data/domain/errors.py`: stable error codes and typed pipeline exception.
- `src/agent_data/domain/schema.py`: package schema export and validation.
- `src/agent_data/sources/resolver.py`: URL/PDF recognition, safe URL policy, content retrieval and hashes.
- `src/agent_data/parsers/base.py`: parser protocol and parse context.
- `src/agent_data/parsers/registry.py`: explicit parser selection.
- `src/agent_data/parsers/mineru.py`: MinerU multipart adapter and content-list normalization.
- `src/agent_data/parsers/trafilatura_parser.py`: webpage extraction adapter.
- `src/agent_data/extraction/llm_client.py`: OpenAI-compatible structured request adapter.
- `src/agent_data/extraction/extractor.py`: chunking, extraction and claim merge.
- `src/agent_data/evidence/verifier.py`: deterministic quote matching and locations.
- `src/agent_data/quality/gates.py`: hard gate checks and stable failures.
- `src/agent_data/quality/scorer.py`: intrinsic/task scores and levels.
- `src/agent_data/export/exporters.py`: atomic JSON/Markdown/report/run outputs.
- `src/agent_data/application/harness.py`: stage runner and result/exit mapping.
- `src/agent_data/application/process_document.py`: V0.1 fixed orchestration.
- `src/agent_data/cli.py`: Typer command.
- `tests/fixtures/`: recorded HTML, MinerU and LLM payloads.
- `tests/unit/`: focused domain and adapter tests.
- `tests/contract/`: upstream response contract tests.
- `tests/e2e/`: offline full-flow tests with injected adapters.

### Task 1: Package and domain foundation

**Files:** `pyproject.toml`, `src/agent_data/domain/models.py`, `src/agent_data/domain/errors.py`, `src/agent_data/config.py`, `tests/unit/test_models.py`, `tests/unit/test_config.py`

- [ ] Write tests proving score range validation, page/page-index invariants, null task scores without task context, stable error fields, and environment configuration defaults.
- [ ] Run `python -m pytest tests/unit/test_models.py tests/unit/test_config.py -q` and verify failure because package modules do not exist.
- [ ] Add package metadata and the minimum Pydantic models/config needed by the tests.
- [ ] Re-run the focused tests and verify they pass.

### Task 2: Source resolution and raw retention

**Files:** `src/agent_data/sources/resolver.py`, `tests/unit/test_source_resolver.py`

- [ ] Write tests for local PDF recognition, missing file, HTTP/HTTPS normalization, unsupported scheme, private/loopback URL rejection, explicit private-network override, response-size limit and SHA-256 stability.
- [ ] Run the focused test and verify expected missing-feature failures.
- [ ] Implement `SourceResolver` with injected HTTP transport and deterministic hashing.
- [ ] Re-run tests and verify green.

### Task 3: Parser protocol and registry

**Files:** `src/agent_data/parsers/base.py`, `src/agent_data/parsers/registry.py`, `tests/unit/test_parser_registry.py`

- [ ] Write tests for configured parser selection and unsupported-source/unknown-provider errors.
- [ ] Verify red.
- [ ] Implement the minimal protocol, parse context and explicit registry.
- [ ] Verify green.

### Task 4: MinerU parser contract

**Files:** `src/agent_data/parsers/mineru.py`, `tests/fixtures/mineru_success.json`, `tests/fixtures/mineru_missing_content_list.json`, `tests/contract/test_mineru_contract.py`

- [ ] Add representative recorded payloads where `content_list` is both a JSON string and decoded list.
- [ ] Write tests for multipart fields, full-document default page range, text/table/list/equation normalization, page-index conversion, bbox preservation, missing result, malformed content list and HTTP error mapping.
- [ ] Verify red.
- [ ] Implement `MinerUParser` using HTTPX, context-managed file upload and adapter-local contract conversion.
- [ ] Verify green.

### Task 5: Trafilatura URL parser

**Files:** `src/agent_data/parsers/trafilatura_parser.py`, `tests/fixtures/article.html`, `tests/unit/test_trafilatura_parser.py`

- [ ] Write tests for title/author/date metadata, markdown extraction, ordered blocks, soft-404/empty-content rejection and parser warnings.
- [ ] Verify red.
- [ ] Implement extraction behind a small injectable extractor function so tests remain offline.
- [ ] Verify green.

### Task 6: OpenAI-compatible extraction

**Files:** `src/agent_data/extraction/llm_client.py`, `src/agent_data/extraction/extractor.py`, `src/agent_data/extraction/prompts.py`, `tests/fixtures/llm_extraction.json`, `tests/unit/test_extractor.py`, `tests/contract/test_llm_contract.py`

- [ ] Write tests for structured response parsing, candidate block IDs/quotes, token-safe chunking, duplicate-claim merge, provider error mapping and model/prompt lineage.
- [ ] Verify red.
- [ ] Implement a client port plus HTTP adapter and deterministic chunk/merge logic.
- [ ] Verify green.

### Task 7: Evidence verification

**Files:** `src/agent_data/evidence/verifier.py`, `tests/unit/test_evidence_verifier.py`

- [ ] Write tests for candidate-block exact match, Unicode/whitespace normalization, unique full-document fallback, ambiguous matches, mismatch rejection, PDF page/bbox inheritance and URL character offsets.
- [ ] Verify red.
- [ ] Implement conservative normalization and verification without semantic fuzzy matching.
- [ ] Verify green.

### Task 8: Schema and quality gates

**Files:** `src/agent_data/domain/schema.py`, `src/agent_data/quality/gates.py`, `tests/unit/test_schema.py`, `tests/unit/test_gates.py`

- [ ] Write tests for all documented gates: schema, provenance, raw retention, usable content, hash integrity, grounded claims, evidence location/fidelity, critical issues and rights restrictions.
- [ ] Verify red.
- [ ] Implement schema validation and ordered gate results with codes/remediation.
- [ ] Verify green.

### Task 9: Quality scoring

**Files:** `src/agent_data/quality/scorer.py`, `tests/unit/test_scorer.py`

- [ ] Write tests for the documented intrinsic weights, A/B/C/rejected thresholds, task-score nullability, reason/method/confidence fields and rejection precedence.
- [ ] Verify red.
- [ ] Implement deterministic score composition and level assignment.
- [ ] Verify green.

### Task 10: Exporters and run artifacts

**Files:** `src/agent_data/export/exporters.py`, `tests/unit/test_exporters.py`

- [ ] Write tests for output tree, atomic JSON/Markdown writes, always-present quality/run reports, no formal Agent-ready files on rejection, secret redaction and non-overwriting run records.
- [ ] Verify red.
- [ ] Implement exporters using temporary sibling files and `Path.replace`.
- [ ] Verify green.

### Task 11: Harness and CLI

**Files:** `src/agent_data/application/harness.py`, `src/agent_data/application/process_document.py`, `src/agent_data/cli.py`, `tests/unit/test_harness.py`, `tests/e2e/test_cli.py`

- [ ] Write tests for stage order, bounded retry behavior, technical-vs-quality failure mapping, exit codes 0/2/3/4/5/6 and CLI options.
- [ ] Verify red.
- [ ] Implement the fixed V0.1 harness and thin Typer command with injected dependencies for tests.
- [ ] Verify green.

### Task 12: Offline end-to-end acceptance

**Files:** `tests/e2e/test_process_document.py`, `tests/fixtures/sample.pdf`, `README.md`

- [ ] Write acceptance tests covering the 15 design requirements with fake parser/LLM ports and real gates/verifier/exporters.
- [ ] Verify red for uncovered requirements.
- [ ] Complete only the missing orchestration behavior.
- [ ] Run `python -m pytest -q` and verify all tests pass offline.
- [ ] Run `uv run ruff check .` and `uv run ruff format --check .` and verify clean output.
- [ ] Run `uv run agent-data --help` and an offline fixture flow; verify documented files and exit codes.
- [ ] Document setup, configuration, CLI examples, output contract and optional live integration commands.

### Task 13: Optional live integration verification

**Files:** `tests/integration/test_live_mineru.py`, `tests/integration/test_live_llm.py`

- [ ] Add tests guarded by `RUN_LIVE_INTEGRATION=1` and required environment variables.
- [ ] Verify default test collection skips them without network access.
- [ ] When services are reachable, run the live MinerU and LLM tests and record actual service versions; otherwise report them as explicitly unverified rather than weakening acceptance.

## Completion audit

- [ ] Map each of the 15 MVP acceptance requirements in `mvp-cli-implementation-design.md` to at least one passing test or runtime artifact.
- [ ] Confirm parser, LLM, evidence and exporter ports can be replaced independently.
- [ ] Confirm no secrets are written to output.
- [ ] Confirm default tests make no network calls.
- [ ] Confirm the CLI produces traceable evidence and deterministic gate results, not merely syntactically valid files.
