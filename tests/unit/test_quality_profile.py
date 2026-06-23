from datetime import datetime, timezone

from agent_data.domain.models import (
    ClaimCandidate,
    ContentBlock,
    Evidence,
    EvidenceLocation,
    ExtractionResult,
    ParsedDocument,
    ResolvedSource,
    TaskScores,
    VerificationResult,
    VerifiedClaim,
)
from agent_data.quality.profile import QualityProfiler


def test_quality_profile_explains_source_freshness_verifiability_and_noise() -> None:
    collected_at = datetime(2026, 6, 23, tzinfo=timezone.utc)
    source = ResolvedSource(
        kind="url",
        original="https://example.com/article",
        filename="article",
        media_type="text/html",
        raw_bytes=b"raw",
        raw_hash="sha256:raw",
        canonical_url="https://example.com/article",
        collected_at=collected_at,
    )
    block = ContentBlock(
        block_id="block_1",
        type="text",
        text="Revenue increased 10%.",
        order=0,
        start_offset=0,
        end_offset=22,
    )
    parsed = ParsedDocument(
        markdown="Revenue increased 10%.",
        content_blocks=[block],
        metadata={"published_at": "2026-06-01T00:00:00+00:00"},
        parser_name="fixture",
        parser_version="1",
        warnings=["parser_warning"],
    )
    extraction = ExtractionResult(
        summary="Revenue grew.",
        key_points=["Revenue increased."],
        claims=[
            ClaimCandidate(
                text="Revenue increased 10%.",
                claim_type="fact",
                confidence=0.9,
                quote="Revenue increased 10%.",
                candidate_block_id="block_1",
            )
        ],
        entities=["Revenue"],
    )
    verification = VerificationResult(
        claims=[
            VerifiedClaim(
                text="Revenue increased 10%.",
                claim_type="fact",
                confidence=0.9,
                verification_status="verified",
                evidence=Evidence(
                    id="evidence_1",
                    block_id="block_1",
                    quote="Revenue increased 10%.",
                    location=EvidenceLocation(start_offset=0, end_offset=22),
                    content_hash="sha256:raw",
                ),
            )
        ]
    )

    profile = QualityProfiler().build(
        source=source,
        parsed=parsed,
        extraction=extraction,
        verification=verification,
        task_scores=TaskScores(relevance=0.8, actionability=0.6, task_score=0.74),
    )

    assert profile.source_trust.score == 0.55
    assert profile.source_trust.tier == "unverified"
    assert profile.source_trust.requires_cross_verification is True
    assert profile.freshness.staleness_risk == "low"
    assert profile.verifiability.verified_fact_claims == 1
    assert profile.structure.score == 1
    assert profile.task_relevance is not None
    assert profile.task_relevance.score == 0.74
    assert profile.noise.risk_tags == [
        "unverified_source",
        "requires_cross_verification",
        "parser_warning",
    ]


def test_source_tier_policy_marks_primary_sources_as_fact_usable() -> None:
    source = ResolvedSource(
        kind="url",
        original="https://claude.com/blog/example",
        filename="example",
        media_type="text/html",
        raw_bytes=b"raw",
        raw_hash="sha256:raw",
        canonical_url="https://claude.com/blog/example",
    )

    profile = QualityProfiler().build(
        source=source,
        parsed=ParsedDocument(
            markdown="Text",
            content_blocks=[],
            parser_name="fixture",
            parser_version="1",
        ),
        extraction=ExtractionResult(),
        verification=VerificationResult(),
        task_scores=TaskScores(),
    )

    assert profile.source_trust.tier == "primary"
    assert profile.source_trust.requires_cross_verification is False
    assert "agent_decision" in profile.source_trust.allowed_uses
    assert profile.noise.risk_tags == []


def test_source_tier_policy_marks_community_sources_as_signal_only() -> None:
    source = ResolvedSource(
        kind="url",
        original="https://x.com/example/status/1",
        filename="1",
        media_type="text/html",
        raw_bytes=b"raw",
        raw_hash="sha256:raw",
        canonical_url="https://x.com/example/status/1",
    )

    profile = QualityProfiler().build(
        source=source,
        parsed=ParsedDocument(
            markdown="Text",
            content_blocks=[],
            parser_name="fixture",
            parser_version="1",
        ),
        extraction=ExtractionResult(),
        verification=VerificationResult(),
        task_scores=TaskScores(),
    )

    assert profile.source_trust.tier == "community_signal"
    assert profile.source_trust.requires_cross_verification is True
    assert profile.source_trust.allowed_uses == ["trend_signal", "lead_generation"]
    assert "high_noise" in profile.noise.risk_tags


def test_source_tier_policy_marks_blogs_as_secondary_sources() -> None:
    source = ResolvedSource(
        kind="url",
        original="https://mp.weixin.qq.com/s/example",
        filename="example",
        media_type="text/html",
        raw_bytes=b"raw",
        raw_hash="sha256:raw",
        canonical_url="https://mp.weixin.qq.com/s/example",
    )

    profile = QualityProfiler().build(
        source=source,
        parsed=ParsedDocument(
            markdown="Text",
            content_blocks=[],
            parser_name="fixture",
            parser_version="1",
        ),
        extraction=ExtractionResult(),
        verification=VerificationResult(),
        task_scores=TaskScores(),
    )

    assert profile.source_trust.tier == "secondary"
    assert profile.source_trust.requires_cross_verification is True
    assert "secondary_source" in profile.noise.risk_tags
