from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from agent_data import __version__
from agent_data.application.harness import Harness
from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import (
    AgentReadyPackage,
    ContentData,
    GateContext,
    KnowledgeData,
    LineageData,
    QualityDimension,
    SourceMetadata,
    TaskScores,
    UsageData,
)
from agent_data.evidence.verifier import EvidenceVerifier
from agent_data.export.exporters import ArtifactExporter
from agent_data.extraction.extractor import DocumentExtractor
from agent_data.parsers.registry import ParserRegistry
from agent_data.quality.cross_verification import CrossVerifier
from agent_data.quality.gates import QualityGateRunner
from agent_data.quality.profile import QualityProfiler
from agent_data.quality.scorer import QualityScorer
from agent_data.sources.resolver import SourceResolver


@dataclass(frozen=True)
class ProcessResult:
    status: str
    exit_code: int
    document_id: str
    output_dir: Path
    package: AgentReadyPackage | None


class ProcessDocument:
    def __init__(
        self,
        *,
        source_resolver: SourceResolver,
        parser_registry: ParserRegistry,
        extractor: DocumentExtractor,
        verifier: EvidenceVerifier,
        gates: QualityGateRunner,
        scorer: QualityScorer,
        exporter: ArtifactExporter,
        profiler: QualityProfiler | None = None,
        cross_verifier: CrossVerifier | None = None,
        harness: Harness | None = None,
    ) -> None:
        self.source_resolver = source_resolver
        self.parser_registry = parser_registry
        self.extractor = extractor
        self.verifier = verifier
        self.gates = gates
        self.scorer = scorer
        self.exporter = exporter
        self.profiler = profiler or QualityProfiler()
        self.cross_verifier = cross_verifier or CrossVerifier(
            source_resolver=source_resolver,
            parser_registry=parser_registry,
            verifier=verifier,
        )
        self.harness = harness or Harness()

    def run(self, value: str, *, task_context: str | None = None) -> ProcessResult:
        self.harness.events.clear()
        try:
            return self._run(value, task_context=task_context)
        except Exception as exc:
            error = (
                exc
                if isinstance(exc, PipelineError)
                else PipelineError(
                    ErrorCode.INTERNAL_ERROR,
                    str(exc),
                    stage="internal",
                )
            )
            try:
                output = self.exporter.export_failure(
                    error=error,
                    run_record={
                        "status": "failed",
                        "source": value,
                        "events": [event.__dict__ for event in self.harness.events],
                    },
                )
                error.details = {**error.details, "output": str(output)}
            except Exception:
                pass
            raise error from exc if error is not exc else None

    def _run(self, value: str, *, task_context: str | None = None) -> ProcessResult:
        source = self.harness.execute(
            "source", lambda: self.source_resolver.resolve(value), retries=1
        )
        parser = self.parser_registry.for_source(source)
        parsed = self.harness.execute("parse", lambda: parser.parse(source), retries=1)
        extraction = self.harness.execute(
            "extract",
            lambda: self.extractor.extract(parsed.content_blocks, task_context=task_context),
            retries=2,
        )
        verification = self.harness.execute(
            "evidence",
            lambda: self.verifier.verify(extraction.claims, parsed.content_blocks, source.raw_hash),
        )
        source_trust = QualityProfiler._source_trust(source)
        clean_hash = "sha256:" + hashlib.sha256(parsed.markdown.encode()).hexdigest()
        gate_context = GateContext(
            schema_valid=True,
            source_locator=source.canonical_url or source.original,
            collected_at=source.collected_at,
            raw_content_ref=f"raw/{source.filename}",
            raw_hash=source.raw_hash,
            clean_content=parsed.markdown,
            clean_hash=clean_hash,
            content_blocks=parsed.content_blocks,
            claims=verification.claims,
            access_rights="unknown",
            strict_claim_gates=not source_trust.requires_cross_verification,
        )
        gate_report = self.harness.execute("quality_gates", lambda: self.gates.run(gate_context))
        task_scores = TaskScores.for_context(
            task_context,
            extraction.relevance,
            extraction.actionability,
        )
        quality_profile = self.harness.execute(
            "quality_profile",
            lambda: self.profiler.build(
                source=source,
                parsed=parsed,
                extraction=extraction,
                verification=verification,
                task_scores=task_scores,
            ),
        )
        cross_verification = self.harness.execute(
            "cross_verification",
            lambda: self.cross_verifier.verify(
                required=quality_profile.source_trust.requires_cross_verification,
                source=source,
                parsed=parsed,
                claims=verification.claims,
            ),
        )
        quality_profile = self.profiler.with_cross_verification(
            quality_profile,
            cross_verification,
        )
        dimensions = self._dimensions(
            source.kind,
            source.canonical_url,
            parsed.warnings,
            verification,
            source_trust_score=quality_profile.source_trust.score,
        )
        quality = self.harness.execute(
            "quality_score",
            lambda: self.scorer.score(dimensions, gate_report, task_scores),
        )
        quality = quality.model_copy(update={"quality_profile": quality_profile})
        document_id = f"doc_{source.raw_hash.removeprefix('sha256:')[:16]}"
        package = self._package(
            document_id,
            source,
            parsed,
            extraction,
            verification.claims,
            clean_hash,
            quality,
        )
        publishable = gate_report.status == "passed" and quality.quality_level != "Rejected"
        agent_ready = publishable and quality_profile.agent_ready
        package_status = "ready" if agent_ready else ("needs_review" if publishable else "failed")
        package = package.model_copy(update={"status": package_status})
        report = {
            "gate_status": gate_report.status,
            "quality_level": quality.quality_level,
            "intrinsic_score": quality.intrinsic_score,
            "quality_profile": quality_profile.model_dump(mode="json"),
            "cross_verification": cross_verification.model_dump(mode="json"),
            "failed_codes": gate_report.failed_codes,
            "checks": [check.model_dump(mode="json") for check in gate_report.checks],
            "claim_results": [claim.model_dump(mode="json") for claim in verification.claims],
        }
        run_record = {
            "status": package_status if publishable else "rejected",
            "document_id": document_id,
            "pipeline_version": __version__,
            "parser": {"name": parsed.parser_name, "version": parsed.parser_version},
            "extractor": extraction.lineage.model_dump(mode="json") if extraction.lineage else None,
            "events": [event.__dict__ for event in self.harness.events],
        }
        paths = self.harness.execute(
            "export",
            lambda: self.exporter.export(
                document_id,
                source,
                parsed,
                package if publishable else None,
                report,
                run_record,
            ),
        )
        return ProcessResult(
            status=package_status if publishable else "rejected",
            exit_code=0 if publishable else 2,
            document_id=document_id,
            output_dir=paths.root,
            package=package if publishable else None,
        )

    @staticmethod
    def _dimensions(source_kind, canonical_url, warnings, verification, source_trust_score=None):
        facts = [claim for claim in verification.claims if claim.claim_type == "fact"]
        verified_count = sum(claim.verification_status == "verified" for claim in facts)
        evidence_score = verified_count / len(facts) if facts else 0.7
        source_score = (
            source_trust_score
            if source_trust_score is not None
            else 0.7
            if canonical_url and urlsplit(canonical_url).scheme == "https"
            else 0.6
        )
        return {
            "source_trust": QualityDimension(
                score=source_score,
                confidence=0.6,
                method="rules_v1",
                reasons=[f"source_type={source_kind}"],
            ),
            "freshness": QualityDimension(
                score=0.5,
                confidence=0.4,
                method="rules_v1",
                reasons=["no reliable publication date rule available"],
            ),
            "completeness": QualityDimension(
                score=0.6 if warnings else 0.9,
                confidence=0.8,
                method="rules_v1",
                reasons=warnings or ["parser reported no completeness warning"],
            ),
            "evidence_quality": QualityDimension(
                score=evidence_score,
                confidence=1.0,
                method="deterministic_verifier_v1",
                reasons=[f"verified_fact_claims={verified_count}/{len(facts)}"],
            ),
            "structure_quality": QualityDimension(
                score=1.0,
                confidence=1.0,
                method="pydantic_schema_v1",
                reasons=["internal models validated"],
            ),
        }

    @staticmethod
    def _package(
        document_id,
        source,
        parsed,
        extraction,
        claims,
        clean_hash,
        quality,
    ) -> AgentReadyPackage:
        now = datetime.now(timezone.utc)
        domain = urlsplit(source.canonical_url).hostname if source.canonical_url else None
        return AgentReadyPackage(
            id=document_id,
            schema_version="0.1.0",
            status="ready",
            source=SourceMetadata(
                url=source.canonical_url,
                domain=domain,
                source_type="web" if source.kind == "url" else "pdf",
                title=parsed.metadata.get("title"),
                author=parsed.metadata.get("author"),
                published_at=parsed.metadata.get("published_at"),
                collected_at=source.collected_at,
                access_rights="unknown",
            ),
            content=ContentData(
                raw_content_ref=f"raw/{source.filename}",
                raw_content_hash=source.raw_hash,
                clean_content=parsed.markdown,
                clean_content_hash=clean_hash,
                is_complete=not parsed.warnings,
                truncation_reason="; ".join(parsed.warnings) or None,
            ),
            knowledge=KnowledgeData(
                summary=extraction.summary,
                key_points=extraction.key_points,
                claims=claims,
                entities=extraction.entities,
                topics=extraction.topics,
                tags=extraction.tags,
            ),
            lineage=LineageData(
                pipeline_version=__version__,
                processed_at=now,
                extractor=extraction.lineage,
                parser_name=parsed.parser_name,
                parser_version=parsed.parser_version,
            ),
            quality=quality,
            usage=ProcessDocument._usage(quality),
        )

    @staticmethod
    def _usage(quality) -> UsageData:
        profile = quality.quality_profile
        if profile is None:
            return UsageData(recommended_uses=["retrieval", "summarization"])
        caveats = []
        if not profile.agent_ready:
            caveats.append(f"Not agent-ready; route to {profile.store_target}")
        if (
            profile.source_trust.requires_cross_verification
            and profile.cross_verification is not None
            and profile.cross_verification.status == "supported"
        ):
            caveats.append("Cross-source verification supported by an independent source")
        elif profile.source_trust.requires_cross_verification:
            caveats.append("Requires cross-source verification before fact use")
        return UsageData(
            recommended_uses=profile.source_trust.allowed_uses,
            caveats=caveats,
        )
