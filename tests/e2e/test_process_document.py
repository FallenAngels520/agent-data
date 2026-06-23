import json
from pathlib import Path

import httpx
import pytest

from agent_data.application.process_document import ProcessDocument
from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import (
    ClaimCandidate,
    ExtractionLineage,
    ExtractionResult,
    ParsedDocument,
)
from agent_data.evidence.verifier import EvidenceVerifier
from agent_data.export.exporters import ArtifactExporter
from agent_data.extraction.extractor import DocumentExtractor
from agent_data.parsers.mineru import MinerUParser
from agent_data.parsers.registry import ParserRegistry
from agent_data.parsers.trafilatura_parser import TrafilaturaParser
from agent_data.quality.gates import QualityGateRunner
from agent_data.quality.scorer import QualityScorer
from agent_data.sources.resolver import SourceResolver


class FixtureParser:
    name = "fixture"

    def supports(self, source) -> bool:
        return source.kind == "pdf"

    def parse(self, source) -> ParsedDocument:
        text = "Revenue increased 10%. " + "Supporting context. " * 15
        blocks = MinerUParser._convert(  # exercise the real normalization contract
            MinerUParser("http://unused"),
            {
                "backend": "pipeline",
                "version": "fixture",
                "results": {
                    "sample": {
                        "md_content": text,
                        "content_list": [
                            {"type": "text", "text": text, "page_idx": 0, "bbox": [1, 2, 3, 4]}
                        ],
                    }
                },
            },
            source,
        )
        return blocks.model_copy(update={"parser_name": self.name})


class FixtureLLM:
    def __init__(self, quote: str = "Revenue increased 10%.") -> None:
        self.quote = quote

    def extract(self, blocks, task_context=None) -> ExtractionResult:
        return ExtractionResult(
            summary="Revenue grew.",
            key_points=["Revenue increased."],
            claims=[
                ClaimCandidate(
                    text=self.quote,
                    claim_type="fact",
                    confidence=0.9,
                    quote=self.quote,
                    candidate_block_id=blocks[0].block_id,
                )
            ],
            entities=["Revenue"],
            topics=["Growth"],
            tags=["finance"],
            relevance=0.8 if task_context else None,
            actionability=0.6 if task_context else None,
            lineage=ExtractionLineage(
                provider="fixture", model="fixture", prompt_version="extract-v1"
            ),
        )


def processor(tmp_path: Path, quote: str = "Revenue increased 10%.") -> ProcessDocument:
    parser = FixtureParser()
    return ProcessDocument(
        source_resolver=SourceResolver(),
        parser_registry=ParserRegistry({"fixture": parser}, {"pdf": "fixture"}),
        extractor=DocumentExtractor(FixtureLLM(quote)),
        verifier=EvidenceVerifier(),
        gates=QualityGateRunner(),
        scorer=QualityScorer(),
        exporter=ArtifactExporter(tmp_path / "output"),
    )


def test_offline_pdf_flow_exports_ready_package_with_traceable_evidence(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF fixture")
    result = processor(tmp_path).run(str(pdf))

    assert result.status == "ready"
    assert result.exit_code == 0
    payload = json.loads((result.output_dir / "agent-ready.json").read_text(encoding="utf-8"))
    claim = payload["knowledge"]["claims"][0]
    assert claim["verification_status"] == "verified"
    assert claim["evidence"]["location"]["page"] == 1
    assert claim["evidence"]["location"]["bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert payload["quality"]["gate_status"] == "passed"


def test_ungrounded_claim_is_rejected_but_reports_are_preserved(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF fixture")
    result = processor(tmp_path, quote="Invented quote").run(str(pdf))

    assert result.status == "rejected"
    assert result.exit_code == 2
    assert not (result.output_dir / "agent-ready.json").exists()
    report = json.loads((result.output_dir / "quality-report.json").read_text(encoding="utf-8"))
    assert "CLAIM_UNGROUNDED" in report["failed_codes"]
    claim_result = report["claim_results"][0]
    assert claim_result["text"] == "Invented quote"
    assert claim_result["claim_type"] == "fact"
    assert claim_result["verification_status"] == "rejected"
    assert claim_result["reason"] == "quote not found"
    assert claim_result["evidence"] is None


def test_duplicate_input_uses_same_document_id_without_overwriting(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF fixture")
    process = processor(tmp_path)
    first = process.run(str(pdf))
    second = process.run(str(pdf))
    assert first.document_id == second.document_id
    assert first.output_dir != second.output_dir


def test_task_context_produces_task_score(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF fixture")
    result = processor(tmp_path).run(str(pdf), task_context="Analyze growth")
    assert result.package is not None
    assert result.package.quality.task_score == 0.74


def test_technical_failure_writes_reports_and_exposes_output_path(tmp_path: Path) -> None:
    class FailingParser(FixtureParser):
        def parse(self, source) -> ParsedDocument:
            raise PipelineError(ErrorCode.PARSER_FAILED, "offline", stage="parse")

    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF fixture")
    process = processor(tmp_path)
    failing = FailingParser()
    process.parser_registry = ParserRegistry({"fixture": failing}, {"pdf": "fixture"})

    with pytest.raises(PipelineError) as exc:
        process.run(str(pdf))

    output = Path(exc.value.details["output"])
    assert (output / "quality-report.json").exists()
    assert (output / "run.json").exists()


def test_offline_url_flow_uses_real_trafilatura_adapter(tmp_path: Path) -> None:
    html = (Path(__file__).parents[1] / "fixtures" / "article.html").read_bytes()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=html))
    client = httpx.Client(transport=transport)
    try:
        parser = TrafilaturaParser()
        process = ProcessDocument(
            source_resolver=SourceResolver(client=client),
            parser_registry=ParserRegistry({"trafilatura": parser}, {"url": "trafilatura"}),
            extractor=DocumentExtractor(FixtureLLM("Revenue increased 10% in 2025.")),
            verifier=EvidenceVerifier(),
            gates=QualityGateRunner(),
            scorer=QualityScorer(),
            exporter=ArtifactExporter(tmp_path / "output"),
        )
        result = process.run("https://93.184.216.34/article")
    finally:
        client.close()

    assert result.status == "ready"
    assert result.package is not None
    evidence = result.package.knowledge.claims[0].evidence
    assert evidence is not None
    assert evidence.location.start_offset is not None
    assert result.package.lineage.parser_name == "trafilatura"
