import json
from pathlib import Path

import httpx
import pytest

from agent_data.application.process_document import ProcessDocument
from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import (
    ClaimCandidate,
    ContentBlock,
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
    profile = payload["quality"]["quality_profile"]
    assert profile["verifiability"]["verified_fact_claims"] == 1
    assert profile["source_trust"]["tier"] == "S"
    assert profile["source_trust"]["requires_cross_verification"] is False
    assert profile["data_type"] == "fact_data"
    assert profile["store_target"] == "agent_ready_data_store"
    assert profile["agent_ready"] is True
    assert profile["source_trust"]["reasons"] == ["source_kind=pdf"]
    assert profile["noise"]["risk_tags"] == []


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

    assert result.status == "needs_review"
    assert result.package is not None
    evidence = result.package.knowledge.claims[0].evidence
    assert evidence is not None
    assert evidence.location.start_offset is not None
    assert result.package.lineage.parser_name == "trafilatura"
    assert result.package.quality.quality_profile is not None
    assert result.package.quality.quality_profile.store_target == "signal_pool"


def test_community_signal_exports_needs_review_package_for_signal_pool(tmp_path: Path) -> None:
    text = "AI tool discussion is trending. " + "Supporting context. " * 15

    class SignalParser:
        name = "signal"

        def supports(self, source) -> bool:
            return source.kind == "url"

        def parse(self, source) -> ParsedDocument:
            return ParsedDocument(
                markdown=text,
                content_blocks=[
                    ContentBlock(
                        block_id="block_1",
                        type="text",
                        text=text,
                        order=0,
                        start_offset=0,
                        end_offset=len(text),
                    )
                ],
                parser_name=self.name,
                parser_version="1",
            )

    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"<html></html>"))
    client = httpx.Client(transport=transport)
    try:
        process = ProcessDocument(
            source_resolver=SourceResolver(client=client),
            parser_registry=ParserRegistry({"signal": SignalParser()}, {"url": "signal"}),
            extractor=DocumentExtractor(FixtureLLM("AI tool discussion is trending.")),
            verifier=EvidenceVerifier(),
            gates=QualityGateRunner(),
            scorer=QualityScorer(),
            exporter=ArtifactExporter(tmp_path / "output"),
        )
        result = process.run("https://x.com/example/status/1")
    finally:
        client.close()

    assert result.status == "needs_review"
    assert result.exit_code == 0
    payload = json.loads((result.output_dir / "agent-ready.json").read_text(encoding="utf-8"))
    assert payload["status"] == "needs_review"
    profile = payload["quality"]["quality_profile"]
    assert profile["source_trust"]["tier"] == "C"
    assert profile["data_type"] == "signal_data"
    assert profile["store_target"] == "signal_pool"
    assert profile["agent_ready"] is False
    assert profile["cross_verification"]["status"] == "not_attempted"
    assert profile["cross_verification"]["reasons"] == ["no_candidate_links_found"]
    assert payload["usage"]["recommended_uses"] == ["trend_signal", "lead_generation"]


def test_social_signal_with_ungrounded_claim_exports_needs_review(tmp_path: Path) -> None:
    text = "AI tool discussion is trending. " + "Supporting context. " * 15

    class SignalParser:
        name = "signal"

        def supports(self, source) -> bool:
            return source.kind == "url"

        def parse(self, source) -> ParsedDocument:
            return ParsedDocument(
                markdown=text,
                content_blocks=[
                    ContentBlock(
                        block_id="block_1",
                        type="text",
                        text=text,
                        order=0,
                        start_offset=0,
                        end_offset=len(text),
                    )
                ],
                parser_name=self.name,
                parser_version="1",
            )

    class MixedClaimLLM:
        def extract(self, blocks, task_context=None) -> ExtractionResult:
            return ExtractionResult(
                summary="Signal summary.",
                key_points=["A social signal was found."],
                claims=[
                    ClaimCandidate(
                        text="AI tool discussion is trending.",
                        claim_type="fact",
                        confidence=0.9,
                        quote="AI tool discussion is trending.",
                        candidate_block_id=blocks[0].block_id,
                    ),
                    ClaimCandidate(
                        text="The tweet has 116 replies.",
                        claim_type="fact",
                        confidence=0.7,
                        quote="116 replies",
                        candidate_block_id=blocks[0].block_id,
                    ),
                ],
                lineage=ExtractionLineage(
                    provider="fixture", model="fixture", prompt_version="extract-v1"
                ),
            )

    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"<html></html>"))
    client = httpx.Client(transport=transport)
    try:
        process = ProcessDocument(
            source_resolver=SourceResolver(client=client),
            parser_registry=ParserRegistry({"signal": SignalParser()}, {"url": "signal"}),
            extractor=DocumentExtractor(MixedClaimLLM()),
            verifier=EvidenceVerifier(),
            gates=QualityGateRunner(),
            scorer=QualityScorer(),
            exporter=ArtifactExporter(tmp_path / "output"),
        )
        result = process.run("https://x.com/example/status/1")
    finally:
        client.close()

    assert result.status == "needs_review"
    assert result.package is not None
    report = json.loads((result.output_dir / "quality-report.json").read_text(encoding="utf-8"))
    assert report["gate_status"] == "passed"
    assert report["claim_results"][1]["verification_status"] == "rejected"
    assert (result.output_dir / "agent-ready.json").exists()


def test_social_signal_cross_verifies_against_authoritative_link(tmp_path: Path) -> None:
    signal_text = (
        "Claude Code supports artifacts. "
        "[Official source](https://claude.com/blog/artifacts-in-claude-code) "
        + "Supporting context. "
        * 15
    )
    official_text = "Claude Code supports artifacts. " + "Official context. " * 15

    class LinkedParser:
        name = "linked"

        def supports(self, source) -> bool:
            return source.kind == "url"

        def parse(self, source) -> ParsedDocument:
            text = official_text if "claude.com" in (source.canonical_url or "") else signal_text
            return ParsedDocument(
                markdown=text,
                content_blocks=[
                    ContentBlock(
                        block_id="block_1",
                        type="text",
                        text=text,
                        order=0,
                        start_offset=0,
                        end_offset=len(text),
                    )
                ],
                parser_name=self.name,
                parser_version="1",
            )

    def handler(request: httpx.Request) -> httpx.Response:
        content = official_text if request.url.host == "claude.com" else signal_text
        return httpx.Response(
            200,
            content=f"<html><body>{content}</body></html>".encode(),
            headers={"content-type": "text/html; charset=utf-8"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        process = ProcessDocument(
            source_resolver=SourceResolver(client=client),
            parser_registry=ParserRegistry({"linked": LinkedParser()}, {"url": "linked"}),
            extractor=DocumentExtractor(FixtureLLM("Claude Code supports artifacts.")),
            verifier=EvidenceVerifier(),
            gates=QualityGateRunner(),
            scorer=QualityScorer(),
            exporter=ArtifactExporter(tmp_path / "output"),
        )
        result = process.run("https://x.com/example/status/1")
    finally:
        client.close()

    assert result.status == "needs_review"
    payload = json.loads((result.output_dir / "agent-ready.json").read_text(encoding="utf-8"))
    profile = payload["quality"]["quality_profile"]
    cross = profile["cross_verification"]
    assert cross["status"] == "supported"
    assert cross["supported_claims"] == 1
    assert cross["sources"][0]["url"] == "https://claude.com/blog/artifacts-in-claude-code"
    assert cross["sources"][0]["source_tier"] == "S"
    assert cross["sources"][0]["independent"] is True
    assert profile["store_target"] == "verified_knowledge_base"
    report = json.loads((result.output_dir / "quality-report.json").read_text(encoding="utf-8"))
    assert report["cross_verification"]["status"] == "supported"
