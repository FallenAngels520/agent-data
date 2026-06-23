import json
from datetime import datetime, timezone
from pathlib import Path

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import (
    AgentReadyPackage,
    ContentData,
    ExtractionLineage,
    KnowledgeData,
    LineageData,
    ParsedDocument,
    QualityDimension,
    QualityResult,
    ResolvedSource,
    SourceMetadata,
)
from agent_data.export.exporters import ArtifactExporter


def source() -> ResolvedSource:
    return ResolvedSource(
        kind="url",
        original="https://example.com",
        canonical_url="https://example.com/",
        filename="index.html",
        media_type="text/html",
        raw_bytes=b"<html>raw</html>",
        raw_hash="sha256:raw",
    )


def package() -> AgentReadyPackage:
    now = datetime.now(timezone.utc)
    dimensions = {
        name: QualityDimension(score=0.9, confidence=1, method="test")
        for name in (
            "source_trust",
            "freshness",
            "completeness",
            "evidence_quality",
            "structure_quality",
        )
    }
    return AgentReadyPackage(
        id="doc_test",
        schema_version="0.1.0",
        status="ready",
        source=SourceMetadata(url="https://example.com/", source_type="web", collected_at=now),
        content=ContentData(
            raw_content_ref="raw/index.html",
            raw_content_hash="sha256:raw",
            clean_content="clean",
            clean_content_hash="sha256:clean",
        ),
        knowledge=KnowledgeData(
            summary="Summary", key_points=["Point"], claims=[], entities=[], topics=[], tags=[]
        ),
        lineage=LineageData(
            pipeline_version="0.1.0",
            processed_at=now,
            extractor=ExtractionLineage(provider="test", model="test", prompt_version="extract-v1"),
            parser_name="test",
            parser_version="1",
        ),
        quality=QualityResult(
            gate_status="passed",
            quality_level="A",
            intrinsic_score=0.9,
            dimensions=dimensions,
            checks=[],
        ),
    )


def test_ready_export_writes_complete_tree_and_redacts_secrets(tmp_path: Path) -> None:
    exporter = ArtifactExporter(tmp_path)
    paths = exporter.export(
        document_id="doc_test",
        source=source(),
        parsed=ParsedDocument(markdown="# Parsed", parser_name="test", parser_version="1"),
        package=package(),
        quality_report={"status": "passed"},
        run_record={"status": "ready", "llm_api_key": "secret", "authorization": "Bearer x"},
    )
    assert paths.root.name == "doc_test"
    assert paths.raw.exists()
    assert (paths.root / "parsed" / "document.md").exists()
    assert (paths.root / "parsed" / "content-blocks.json").exists()
    assert (paths.root / "agent-ready.json").exists()
    assert (paths.root / "agent-ready.md").exists()
    assert (paths.root / "quality-report.json").exists()
    run = json.loads((paths.root / "run.json").read_text(encoding="utf-8"))
    assert run["llm_api_key"] == "[REDACTED]"
    assert run["authorization"] == "[REDACTED]"


def test_rejected_export_omits_formal_agent_ready_files(tmp_path: Path) -> None:
    paths = ArtifactExporter(tmp_path).export(
        document_id="doc_test",
        source=source(),
        parsed=ParsedDocument(markdown="# Parsed", parser_name="test", parser_version="1"),
        package=None,
        quality_report={"status": "failed"},
        run_record={"status": "rejected"},
    )
    assert not (paths.root / "agent-ready.json").exists()
    assert (paths.root / "quality-report.json").exists()
    assert (paths.root / "run.json").exists()


def test_repeated_export_does_not_overwrite_previous_run(tmp_path: Path) -> None:
    exporter = ArtifactExporter(tmp_path)
    first = exporter.export(
        "doc_test",
        source(),
        ParsedDocument(markdown="a", parser_name="p", parser_version="1"),
        None,
        {},
        {},
    )
    second = exporter.export(
        "doc_test",
        source(),
        ParsedDocument(markdown="b", parser_name="p", parser_version="1"),
        None,
        {},
        {},
    )
    assert first.root != second.root
    assert (first.root / "parsed" / "document.md").read_text(encoding="utf-8") == "a"


def test_technical_failure_always_writes_quality_and_run_reports(tmp_path: Path) -> None:
    error = PipelineError(ErrorCode.LLM_FAILED, "offline", stage="extract", retryable=True)
    root = ArtifactExporter(tmp_path).export_failure(
        error=error,
        run_record={"status": "failed", "llm_api_key": "secret"},
    )
    assert (root / "quality-report.json").exists()
    assert (root / "run.json").exists()
    report = json.loads((root / "quality-report.json").read_text(encoding="utf-8"))
    assert report["error"]["code"] == "LLM_FAILED"
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
    assert run["llm_api_key"] == "[REDACTED]"
