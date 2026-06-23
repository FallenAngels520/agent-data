from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from agent_data.domain.models import (
    ClaimCandidate,
    CrossVerificationResult,
    CrossVerificationSource,
    ParsedDocument,
    ResolvedSource,
    SourceTrustProfile,
    VerifiedClaim,
)
from agent_data.evidence.verifier import EvidenceVerifier
from agent_data.parsers.registry import ParserRegistry
from agent_data.quality.profile import QualityProfiler
from agent_data.sources.resolver import SourceResolver


class CrossVerifier:
    def __init__(
        self,
        *,
        source_resolver: SourceResolver,
        parser_registry: ParserRegistry,
        verifier: EvidenceVerifier,
        max_candidates: int = 3,
    ) -> None:
        self.source_resolver = source_resolver
        self.parser_registry = parser_registry
        self.verifier = verifier
        self.max_candidates = max_candidates

    def verify(
        self,
        *,
        required: bool,
        source: ResolvedSource,
        parsed: ParsedDocument,
        claims: list[VerifiedClaim],
    ) -> CrossVerificationResult:
        facts = [
            claim
            for claim in claims
            if claim.claim_type == "fact" and claim.verification_status == "verified"
        ]
        if not required:
            return self._result(
                required=False,
                status="not_required",
                facts=facts,
                reasons=["source_policy_does_not_require_cross_verification"],
            )
        if not facts:
            return self._result(
                required=True,
                status="not_attempted",
                facts=facts,
                reasons=["no_verified_fact_claims_to_cross_check"],
            )

        candidate_urls = self._candidate_urls(
            parsed.markdown,
            source.canonical_url or source.original,
        )
        if not candidate_urls:
            return self._result(
                required=True,
                status="not_attempted",
                facts=facts,
                reasons=["no_candidate_links_found"],
            )

        sources: list[CrossVerificationSource] = []
        best_supported = 0
        origin_host = self._host(source.canonical_url or source.original)
        for url in candidate_urls[: self.max_candidates]:
            try:
                candidate_source = self.source_resolver.resolve(url)
                trust = QualityProfiler._source_trust(candidate_source)
                parser = self.parser_registry.for_source(candidate_source)
                candidate_parsed = parser.parse(candidate_source)
                supported = self._supported_claim_count(facts, candidate_parsed, candidate_source)
                independent = self._host(candidate_source.canonical_url or url) != origin_host
                status = "supported" if supported else "no_support"
                best_supported = max(best_supported, supported if independent else 0)
                sources.append(
                    self._source_result(
                        url=candidate_source.canonical_url or url,
                        trust=trust,
                        independent=independent,
                        status=status,
                        supported_claims=supported,
                    )
                )
            except Exception as exc:
                sources.append(
                    CrossVerificationSource(
                        url=url,
                        domain=self._host(url),
                        source_tier="D",
                        independent=self._host(url) != origin_host,
                        status="failed",
                        error=str(exc),
                    )
                )

        status = "supported" if best_supported == len(facts) else "insufficient"
        if sources and all(source.status == "failed" for source in sources):
            status = "failed"
        return CrossVerificationResult(
            required=True,
            status=status,
            checked_at=datetime.now(timezone.utc),
            candidate_count=len(candidate_urls),
            supported_claims=best_supported,
            total_claims=len(facts),
            sources=sources,
            reasons=[f"independent_supported_fact_claims={best_supported}/{len(facts)}"],
        )

    @staticmethod
    def _candidate_urls(markdown: str, base_url: str) -> list[str]:
        matches = re.findall(r"\[[^\]]*\]\(([^)]+)\)", markdown)
        matches.extend(re.findall(r"https?://[^\s)>\]]+", markdown))
        seen: set[str] = set()
        urls: list[str] = []
        for match in matches:
            url = urljoin(base_url, match.strip())
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue
            normalized = parsed._replace(fragment="").geturl()
            if (
                normalized == base_url
                or normalized in seen
                or CrossVerifier._is_noise_url(normalized)
            ):
                continue
            seen.add(normalized)
            urls.append(normalized)
        return urls

    @staticmethod
    def _is_noise_url(url: str) -> bool:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").casefold()
        path = parsed.path.rstrip("/") or "/"
        if hostname in {"pbs.twimg.com", "abs.twimg.com", "video.twimg.com"}:
            return True
        if path.casefold().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")):
            return True
        if hostname not in {"x.com", "twitter.com"}:
            return False
        if path.startswith("/i/article/"):
            return False
        parts = [part for part in path.split("/") if part]
        if len(parts) == 1:
            return True
        if path in {"/", "/tos", "/privacy", "/explore"}:
            return True
        if path.startswith(("/i/jf/onboarding", "/i/flow/login", "/login", "/signup")):
            return True
        if path.startswith(("/settings", "/help", "/intent/", "/share")):
            return True
        return False

    def _supported_claim_count(
        self,
        facts: list[VerifiedClaim],
        parsed: ParsedDocument,
        source: ResolvedSource,
    ) -> int:
        if not parsed.content_blocks:
            return 0
        candidates = [
            ClaimCandidate(
                text=claim.text,
                claim_type=claim.claim_type,
                confidence=claim.confidence,
                quote=claim.text,
                candidate_block_id=parsed.content_blocks[0].block_id,
            )
            for claim in facts
        ]
        verification = self.verifier.verify(candidates, parsed.content_blocks, source.raw_hash)
        return sum(
            claim.verification_status == "verified" and claim.evidence is not None
            for claim in verification.claims
        )

    @staticmethod
    def _source_result(
        *,
        url: str,
        trust: SourceTrustProfile,
        independent: bool,
        status: str,
        supported_claims: int,
    ) -> CrossVerificationSource:
        return CrossVerificationSource(
            url=url,
            domain=CrossVerifier._host(url),
            source_tier=trust.tier,
            independent=independent,
            status=status,  # type: ignore[arg-type]
            supported_claims=supported_claims,
        )

    @staticmethod
    def _result(
        *,
        required: bool,
        status: str,
        facts: list[VerifiedClaim],
        reasons: list[str],
    ) -> CrossVerificationResult:
        return CrossVerificationResult(
            required=required,
            status=status,  # type: ignore[arg-type]
            checked_at=datetime.now(timezone.utc),
            candidate_count=0,
            supported_claims=0,
            total_claims=len(facts),
            reasons=reasons,
        )

    @staticmethod
    def _host(url: str) -> str | None:
        return urlsplit(url).hostname
