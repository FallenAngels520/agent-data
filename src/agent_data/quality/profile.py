from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from agent_data.domain.models import (
    CrossVerificationResult,
    ExtractionResult,
    FreshnessProfile,
    NoiseProfile,
    ParsedDocument,
    QualityMetric,
    QualityProfile,
    ResolvedSource,
    SourceTrustProfile,
    TaskScores,
    VerifiabilityProfile,
    VerificationResult,
)


class QualityProfiler:
    def build(
        self,
        *,
        source: ResolvedSource,
        parsed: ParsedDocument,
        extraction: ExtractionResult,
        verification: VerificationResult,
        task_scores: TaskScores,
    ) -> QualityProfile:
        source_trust = self._source_trust(source)
        policy = self._policy(source_trust)
        return QualityProfile(
            source_trust=source_trust,
            data_type=policy["data_type"],
            verification_level=policy["verification_level"],
            store_target=policy["store_target"],
            agent_ready=policy["agent_ready"],
            policy_reasons=policy["policy_reasons"],
            freshness=self._freshness(source, parsed),
            verifiability=self._verifiability(verification),
            structure=self._structure(parsed, extraction),
            task_relevance=self._task_relevance(task_scores),
            noise=self._noise(parsed, verification, source_trust),
        )

    @staticmethod
    def with_cross_verification(
        profile: QualityProfile,
        cross_verification: CrossVerificationResult,
    ) -> QualityProfile:
        if cross_verification.status != "supported":
            return profile.model_copy(update={"cross_verification": cross_verification})
        policy_reasons = [
            *profile.policy_reasons,
            "cross_verified_by_independent_source",
        ]
        update = {
            "cross_verification": cross_verification,
            "store_target": "verified_knowledge_base",
            "policy_reasons": list(dict.fromkeys(policy_reasons)),
        }
        if profile.data_type == "signal_data":
            update["data_type"] = "evidence_data"
        return profile.model_copy(update=update)

    @staticmethod
    def _source_trust(source: ResolvedSource) -> SourceTrustProfile:
        reasons = [f"source_kind={source.kind}"]
        if source.kind == "pdf":
            return SourceTrustProfile(
                score=0.8,
                tier="S",
                category="local_pdf",
                requires_cross_verification=False,
                allowed_uses=["fact_base", "retrieval", "agent_decision"],
                reasons=reasons,
            )
        score = 0.55
        tier = "D"
        category = "unknown_web"
        requires_cross_verification = True
        allowed_uses = ["candidate_evidence"]
        risk_tags = ["unverified_source", "requires_cross_verification"]
        if source.canonical_url:
            parsed_url = urlsplit(source.canonical_url)
            if parsed_url.scheme == "https":
                reasons.append("https_source")
            hostname = (parsed_url.hostname or "").casefold()
            if hostname:
                reasons.append(f"domain={hostname}")
                classification = QualityProfiler._classify_domain(hostname)
                score = classification["score"]
                tier = classification["tier"]
                category = classification["category"]
                requires_cross_verification = classification["requires_cross_verification"]
                allowed_uses = classification["allowed_uses"]
                risk_tags = classification["risk_tags"]
                reasons.append(category)
        return SourceTrustProfile(
            score=min(score, 1.0),
            tier=tier,  # type: ignore[arg-type]
            category=category,
            requires_cross_verification=requires_cross_verification,
            allowed_uses=allowed_uses,
            risk_tags=risk_tags,
            reasons=reasons,
        )

    @staticmethod
    def _classify_domain(hostname: str) -> dict:
        primary_domains = {
            "anthropic.com",
            "claude.com",
            "docs.github.com",
            "github.com",
            "openai.com",
            "platform.openai.com",
        }
        community_domains = {
            "reddit.com",
            "news.ycombinator.com",
        }
        social_domains = {
            "x.com",
            "twitter.com",
            "linkedin.com",
            "youtube.com",
            "tiktok.com",
        }
        secondary_domains = {
            "medium.com",
            "substack.com",
            "mp.weixin.qq.com",
            "dev.to",
        }
        if any(hostname == domain or hostname.endswith(f".{domain}") for domain in primary_domains):
            return {
                "score": 0.9,
                "tier": "S",
                "category": "authoritative_source",
                "requires_cross_verification": False,
                "allowed_uses": ["fact_base", "retrieval", "agent_decision"],
                "risk_tags": [],
            }
        if any(
            hostname == domain or hostname.endswith(f".{domain}") for domain in community_domains
        ):
            return {
                "score": 0.6,
                "tier": "B",
                "category": "community_feedback",
                "requires_cross_verification": True,
                "allowed_uses": ["pain_point_discovery", "trend_signal", "user_feedback"],
                "risk_tags": [
                    "community_feedback",
                    "needs_aggregation",
                    "requires_cross_verification",
                ],
            }
        if any(hostname == domain or hostname.endswith(f".{domain}") for domain in social_domains):
            return {
                "score": 0.45,
                "tier": "C",
                "category": "social_discussion",
                "requires_cross_verification": True,
                "allowed_uses": ["trend_signal", "lead_generation"],
                "risk_tags": [
                    "community_signal",
                    "high_noise",
                    "opinion_heavy",
                    "requires_cross_verification",
                ],
            }
        if any(
            hostname == domain or hostname.endswith(f".{domain}") for domain in secondary_domains
        ):
            return {
                "score": 0.65,
                "tier": "A",
                "category": "secondary_source",
                "requires_cross_verification": True,
                "allowed_uses": ["background", "candidate_evidence"],
                "risk_tags": ["secondary_source", "requires_cross_verification"],
            }
        return {
            "score": 0.55,
            "tier": "D",
            "category": "unknown_web",
            "requires_cross_verification": True,
            "allowed_uses": ["candidate_evidence"],
            "risk_tags": ["unverified_source", "requires_cross_verification"],
        }

    @staticmethod
    def _policy(source_trust: SourceTrustProfile) -> dict:
        if source_trust.tier == "S":
            return {
                "data_type": "fact_data",
                "verification_level": "strong",
                "store_target": "agent_ready_data_store",
                "agent_ready": True,
                "policy_reasons": ["authoritative_source"],
            }
        if source_trust.tier == "A":
            return {
                "data_type": "evidence_data",
                "verification_level": "medium",
                "store_target": "verified_knowledge_base",
                "agent_ready": False,
                "policy_reasons": ["secondary_source_requires_cross_check"],
            }
        if source_trust.tier in {"B", "C"}:
            return {
                "data_type": "signal_data",
                "verification_level": "medium",
                "store_target": "signal_pool",
                "agent_ready": False,
                "policy_reasons": ["signal_source_requires_cross_check"],
            }
        return {
            "data_type": "evidence_data",
            "verification_level": "medium",
            "store_target": "signal_pool",
            "agent_ready": False,
            "policy_reasons": ["unverified_source_requires_review"],
        }

    @staticmethod
    def _freshness(source: ResolvedSource, parsed: ParsedDocument) -> FreshnessProfile:
        published_at = parsed.metadata.get("published_at")
        reasons = ["last_checked_at_recorded"]
        risk = "unknown"
        score = 0.5
        published_dt = QualityProfiler._parse_date(str(published_at)) if published_at else None
        if published_dt:
            age_days = (source.collected_at - published_dt).days
            if age_days <= 30:
                score = 0.9
                risk = "low"
            elif age_days <= 180:
                score = 0.75
                risk = "medium"
            else:
                score = 0.45
                risk = "high"
            reasons.append(f"published_age_days={age_days}")
        else:
            reasons.append("published_at_unavailable")
        return FreshnessProfile(
            score=score,
            reasons=reasons,
            last_checked_at=source.collected_at,
            published_at=str(published_at) if published_at else None,
            staleness_risk=risk,
        )

    @staticmethod
    def _verifiability(verification: VerificationResult) -> VerifiabilityProfile:
        facts = [claim for claim in verification.claims if claim.claim_type == "fact"]
        verified = [
            claim
            for claim in facts
            if claim.verification_status == "verified" and claim.evidence is not None
        ]
        score = len(verified) / len(facts) if facts else 0.7
        return VerifiabilityProfile(
            score=score,
            reasons=[f"verified_fact_claims={len(verified)}/{len(facts)}"],
            verified_fact_claims=len(verified),
            total_fact_claims=len(facts),
            evidence_count=sum(claim.evidence is not None for claim in verification.claims),
        )

    @staticmethod
    def _structure(parsed: ParsedDocument, extraction: ExtractionResult) -> QualityMetric:
        signals = [
            bool(parsed.content_blocks),
            bool(extraction.summary),
            bool(extraction.key_points),
            bool(extraction.claims),
            bool(extraction.entities or extraction.topics or extraction.tags),
        ]
        score = sum(signals) / len(signals)
        return QualityMetric(
            score=score,
            reasons=[
                f"content_blocks={len(parsed.content_blocks)}",
                f"claims={len(extraction.claims)}",
                f"key_points={len(extraction.key_points)}",
            ],
        )

    @staticmethod
    def _task_relevance(task_scores: TaskScores) -> QualityMetric | None:
        if task_scores.task_score is None:
            return None
        return QualityMetric(
            score=task_scores.task_score,
            reasons=[
                f"relevance={task_scores.relevance}",
                f"actionability={task_scores.actionability}",
            ],
        )

    @staticmethod
    def _noise(
        parsed: ParsedDocument,
        verification: VerificationResult,
        source_trust: SourceTrustProfile,
    ) -> NoiseProfile:
        risk_tags = [*source_trust.risk_tags, *parsed.warnings]
        if any(claim.verification_status != "verified" for claim in verification.claims):
            risk_tags.append("unverified_claims")
        risk_tags = list(dict.fromkeys(risk_tags))
        penalty = min(1.0, len(risk_tags) * 0.2)
        return NoiseProfile(
            score=penalty,
            reasons=[f"risk_tag_count={len(risk_tags)}"],
            risk_tags=risk_tags,
        )

    @staticmethod
    def _parse_date(value: str) -> datetime | None:
        for candidate in (value, value.replace("Z", "+00:00")):
            try:
                parsed = datetime.fromisoformat(candidate)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
