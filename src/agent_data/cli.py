from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from agent_data.application.harness import exit_code_for_error
from agent_data.application.process_document import ProcessDocument
from agent_data.config import Settings
from agent_data.domain.errors import PipelineError
from agent_data.evidence.verifier import EvidenceVerifier
from agent_data.export.exporters import ArtifactExporter
from agent_data.extraction.extractor import DocumentExtractor
from agent_data.extraction.llm_client import OpenAICompatibleClient
from agent_data.parsers.crawl4ai import Crawl4AIParser
from agent_data.parsers.mineru import MinerUParser
from agent_data.parsers.registry import ParserRegistry
from agent_data.parsers.trafilatura_parser import TrafilaturaParser
from agent_data.quality.gates import QualityGateRunner
from agent_data.quality.scorer import QualityScorer
from agent_data.sources.resolver import SourceResolver

app = typer.Typer(no_args_is_help=True, help="Build evidence-grounded Agent-ready data packages.")


@app.callback()
def main() -> None:
    """Agent-ready data command line interface."""


def build_processor(
    *,
    output: Path,
    start_page: int | None = None,
    end_page: int | None = None,
) -> ProcessDocument:
    settings = Settings.from_env()
    source_resolver = SourceResolver(
        allow_private_networks=settings.allow_private_networks,
        max_download_bytes=settings.max_download_bytes,
    )
    mineru = MinerUParser(
        settings.mineru_base_url,
        timeout_seconds=settings.mineru_timeout_seconds,
        start_page=settings.mineru_start_page if start_page is None else start_page,
        end_page=settings.mineru_end_page if end_page is None else end_page,
    )
    crawl4ai = Crawl4AIParser(
        settings.crawl4ai_base_url,
        api_token=settings.crawl4ai_api_token,
        timeout_seconds=settings.crawl4ai_timeout_seconds,
        poll_interval_seconds=settings.crawl4ai_poll_interval_seconds,
    )
    trafilatura = TrafilaturaParser()
    registry = ParserRegistry(
        {"mineru": mineru, "crawl4ai": crawl4ai, "trafilatura": trafilatura},
        {"pdf": settings.pdf_parser, "url": settings.url_parser},
    )
    llm = OpenAICompatibleClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url or "https://api.openai.com/v1",
        timeout_seconds=settings.llm_timeout_seconds,
    )
    return ProcessDocument(
        source_resolver=source_resolver,
        parser_registry=registry,
        extractor=DocumentExtractor(llm),
        verifier=EvidenceVerifier(),
        gates=QualityGateRunner(),
        scorer=QualityScorer(),
        exporter=ArtifactExporter(output),
    )


@app.command()
def process(
    source: Annotated[str, typer.Argument(help="HTTP(S) URL or local PDF path.")],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("output"),
    task_context: Annotated[str | None, typer.Option("--task-context")] = None,
    start_page: Annotated[int | None, typer.Option("--start-page", min=0)] = None,
    end_page: Annotated[int | None, typer.Option("--end-page", min=0)] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Reprocess even when content was seen before.")
    ] = False,
    keep_raw: Annotated[bool, typer.Option("--keep-raw/--no-keep-raw")] = True,
    log_level: Annotated[str, typer.Option("--log-level")] = "INFO",
) -> None:
    """Process one source into an Agent-ready data package."""
    try:
        if not keep_raw:
            raise ValueError("Raw retention is required for an Agent-ready package")
        level = getattr(logging, log_level.upper(), None)
        if not isinstance(level, int):
            raise ValueError(f"Invalid log level: {log_level}")
        logging.basicConfig(level=level)
        _ = force  # Every MVP invocation is a fresh run; retained for the stable CLI contract.
        processor = build_processor(output=output, start_page=start_page, end_page=end_page)
        result = processor.run(source, task_context=task_context)
    except ValueError as exc:
        typer.echo(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        raise typer.Exit(3) from exc
    except PipelineError as exc:
        typer.echo(json.dumps({"status": "error", **exc.as_dict()}, ensure_ascii=False))
        raise typer.Exit(exit_code_for_error(exc.code)) from exc
    typer.echo(
        json.dumps(
            {
                "status": result.status,
                "document_id": result.document_id,
                "output": str(result.output_dir),
            },
            ensure_ascii=False,
        )
    )
    if result.exit_code:
        raise typer.Exit(result.exit_code)


if __name__ == "__main__":
    app()
