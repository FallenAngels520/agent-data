from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceLocation(DomainModel):
    page: int | None = Field(default=None, ge=1)
    page_index: int | None = Field(default=None, ge=0)
    bbox: list[float] | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def pages_are_consistent(self) -> EvidenceLocation:
        if (self.page is None) != (self.page_index is None):
            raise ValueError("page and page_index must be provided together")
        if self.page is not None and self.page != self.page_index + 1:  # type: ignore[operator]
            raise ValueError("page must equal page_index + 1")
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must be provided together")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset must not precede start_offset")
        return self


class QualityDimension(DomainModel):
    score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    method: str
    reasons: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)


class TaskScores(DomainModel):
    relevance: float | None = Field(default=None, ge=0, le=1)
    actionability: float | None = Field(default=None, ge=0, le=1)
    task_score: float | None = Field(default=None, ge=0, le=1)

    @classmethod
    def for_context(
        cls,
        task_context: str | None,
        relevance: float | None,
        actionability: float | None,
    ) -> TaskScores:
        if not task_context:
            return cls()
        if relevance is None or actionability is None:
            raise ValueError("task-aware scores require relevance and actionability")
        return cls(
            relevance=relevance,
            actionability=actionability,
            task_score=0.7 * relevance + 0.3 * actionability,
        )


Severity = Literal["critical", "high", "medium", "low"]


class ResolvedSource(DomainModel):
    kind: Literal["pdf", "url"]
    original: str
    filename: str
    media_type: str
    raw_bytes: bytes
    raw_hash: str
    canonical_url: str | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    response_metadata: dict[str, Any] = Field(default_factory=dict)


class ContentBlock(DomainModel):
    block_id: str
    type: str
    text: str
    order: int = Field(ge=0)
    page: int | None = Field(default=None, ge=1)
    page_index: int | None = Field(default=None, ge=0)
    bbox: list[float] | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    source_location: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def pages_are_consistent(self) -> ContentBlock:
        if (self.page is None) != (self.page_index is None):
            raise ValueError("page and page_index must be provided together")
        if self.page is not None and self.page != self.page_index + 1:  # type: ignore[operator]
            raise ValueError("page must equal page_index + 1")
        return self


class ParsedDocument(DomainModel):
    markdown: str
    content_blocks: list[ContentBlock] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    parser_name: str
    parser_version: str
    warnings: list[str] = Field(default_factory=list)


ClaimType = Literal["fact", "opinion", "prediction", "instruction", "derived"]


class ClaimCandidate(DomainModel):
    text: str
    claim_type: ClaimType
    confidence: float = Field(ge=0, le=1)
    quote: str
    candidate_block_id: str


class ExtractionLineage(DomainModel):
    provider: str
    model: str
    prompt_version: str


class ExtractionResult(DomainModel):
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    claims: list[ClaimCandidate] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    relevance: float | None = Field(default=None, ge=0, le=1)
    actionability: float | None = Field(default=None, ge=0, le=1)
    lineage: ExtractionLineage | None = None


VerificationStatus = Literal["verified", "rejected", "needs_review"]


class Evidence(DomainModel):
    id: str
    block_id: str
    quote: str
    location: EvidenceLocation
    content_hash: str
    verification_status: Literal["verified"] = "verified"


class VerifiedClaim(DomainModel):
    text: str
    claim_type: ClaimType
    confidence: float = Field(ge=0, le=1)
    verification_status: VerificationStatus
    evidence: Evidence | None = None
    reason: str | None = None


class VerificationResult(DomainModel):
    claims: list[VerifiedClaim] = Field(default_factory=list)


class QualityIssue(DomainModel):
    code: str
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    message: str
    affected_paths: list[str] = Field(default_factory=list)
    likely_cause: str | None = None
    remediation: str | None = None


class GateContext(DomainModel):
    schema_valid: bool
    source_locator: str
    collected_at: datetime | None
    raw_content_ref: str
    raw_hash: str
    clean_content: str
    clean_hash: str
    content_blocks: list[ContentBlock]
    claims: list[VerifiedClaim]
    issues: list[QualityIssue] = Field(default_factory=list)
    access_rights: str = "unknown"


class GateCheck(DomainModel):
    name: str
    passed: bool
    code: str
    message: str
    severity: Severity = "critical"
    remediation: str | None = None


class GateReport(DomainModel):
    status: Literal["passed", "failed"]
    checks: list[GateCheck]

    @property
    def failed_codes(self) -> list[str]:
        return [check.code for check in self.checks if not check.passed]


class QualityMetric(DomainModel):
    score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


SourceTier = Literal["primary", "secondary", "community_signal", "unverified", "blocked"]


class SourceTrustProfile(QualityMetric):
    tier: SourceTier
    category: str
    requires_cross_verification: bool = False
    allowed_uses: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)


class FreshnessProfile(QualityMetric):
    last_checked_at: datetime
    published_at: str | None = None
    staleness_risk: Literal["low", "medium", "high", "unknown"] = "unknown"


class VerifiabilityProfile(QualityMetric):
    verified_fact_claims: int = Field(ge=0)
    total_fact_claims: int = Field(ge=0)
    evidence_count: int = Field(ge=0)


class NoiseProfile(QualityMetric):
    risk_tags: list[str] = Field(default_factory=list)


class QualityProfile(DomainModel):
    source_trust: SourceTrustProfile
    freshness: FreshnessProfile
    verifiability: VerifiabilityProfile
    structure: QualityMetric
    task_relevance: QualityMetric | None = None
    noise: NoiseProfile


class QualityResult(DomainModel):
    gate_status: Literal["passed", "failed"]
    quality_level: Literal["A", "B", "C", "Rejected"]
    intrinsic_score: float = Field(ge=0, le=1)
    task_score: float | None = Field(default=None, ge=0, le=1)
    dimensions: dict[str, QualityDimension]
    checks: list[GateCheck]
    issues: list[QualityIssue] = Field(default_factory=list)
    quality_profile: QualityProfile | None = None


class SourceMetadata(DomainModel):
    url: str | None = None
    domain: str | None = None
    source_type: str
    title: str | None = None
    author: str | None = None
    publisher: str | None = None
    published_at: str | None = None
    collected_at: datetime
    language: str | None = None
    access_rights: str = "unknown"
    license: str | None = None


class ContentData(DomainModel):
    raw_content_ref: str
    raw_content_hash: str
    clean_content: str
    clean_content_hash: str
    content_format: str = "markdown"
    is_complete: bool = True
    truncation_reason: str | None = None


class KnowledgeData(DomainModel):
    summary: str
    key_points: list[str]
    claims: list[VerifiedClaim]
    entities: list[str]
    topics: list[str]
    tags: list[str]
    risks: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)


class LineageData(DomainModel):
    document_version: int = Field(default=1, ge=1)
    pipeline_version: str
    processed_at: datetime
    extractor: ExtractionLineage | None = None
    parser_name: str
    parser_version: str


class UsageData(DomainModel):
    recommended_uses: list[str] = Field(default_factory=list)
    prohibited_uses: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class AgentReadyPackage(DomainModel):
    id: str
    schema_version: str
    status: Literal["ready", "failed", "needs_review", "superseded"]
    source: SourceMetadata
    content: ContentData
    knowledge: KnowledgeData
    lineage: LineageData
    quality: QualityResult
    usage: UsageData = Field(default_factory=UsageData)
    export_formats: list[str] = Field(default_factory=lambda: ["json", "markdown"])
