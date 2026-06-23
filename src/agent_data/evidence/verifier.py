from __future__ import annotations

import hashlib
import unicodedata

from agent_data.domain.models import (
    ClaimCandidate,
    ContentBlock,
    Evidence,
    EvidenceLocation,
    VerificationResult,
    VerifiedClaim,
)


class EvidenceVerifier:
    def verify(
        self,
        claims: list[ClaimCandidate],
        blocks: list[ContentBlock],
        content_hash: str,
    ) -> VerificationResult:
        by_id = {block.block_id: block for block in blocks}
        verified: list[VerifiedClaim] = []
        for claim in claims:
            candidate = by_id.get(claim.candidate_block_id)
            match = self._match(candidate, claim.quote) if candidate else None
            matched_block = candidate if match else None
            if match is None:
                matches = [
                    (block, found)
                    for block in blocks
                    if (found := self._match(block, claim.quote)) is not None
                ]
                if len(matches) == 1:
                    matched_block, match = matches[0]
                elif len(matches) > 1:
                    verified.append(self._unverified(claim, "needs_review", "quote is ambiguous"))
                    continue
                else:
                    verified.append(self._unverified(claim, "rejected", "quote not found"))
                    continue
            assert matched_block is not None and match is not None
            if not self._directly_supported(claim.text, claim.quote):
                verified.append(
                    self._unverified(
                        claim,
                        "needs_review",
                        "quote exists but does not directly support claim text",
                    )
                )
                continue
            start, end = match
            location = self._location(matched_block, start, end)
            evidence_id = hashlib.sha256(
                f"{content_hash}|{matched_block.block_id}|{claim.quote}|{start}|{end}".encode()
            ).hexdigest()[:16]
            evidence = Evidence(
                id=f"evidence_{evidence_id}",
                block_id=matched_block.block_id,
                quote=claim.quote,
                location=location,
                content_hash=content_hash,
            )
            verified.append(
                VerifiedClaim(
                    text=claim.text,
                    claim_type=claim.claim_type,
                    confidence=claim.confidence,
                    verification_status="verified",
                    evidence=evidence,
                )
            )
        return VerificationResult(claims=verified)

    @staticmethod
    def _unverified(claim: ClaimCandidate, status: str, reason: str) -> VerifiedClaim:
        return VerifiedClaim(
            text=claim.text,
            claim_type=claim.claim_type,
            confidence=claim.confidence,
            verification_status=status,  # type: ignore[arg-type]
            reason=reason,
        )

    def _match(self, block: ContentBlock | None, quote: str) -> tuple[int, int] | None:
        if block is None or not quote.strip():
            return None
        exact = block.text.find(quote)
        if exact >= 0:
            return exact, exact + len(quote)
        normalized_text, mapping = self._normalize_with_map(block.text)
        normalized_quote, _ = self._normalize_with_map(quote)
        if not normalized_quote:
            return None
        start = normalized_text.find(normalized_quote)
        if start < 0:
            return None
        original_start = mapping[start]
        original_end = mapping[start + len(normalized_quote) - 1] + 1
        return original_start, original_end

    def _directly_supported(self, claim: str, quote: str) -> bool:
        normalized_claim = self._normalize_with_map(claim)[0].strip().casefold()
        normalized_quote = self._normalize_with_map(quote)[0].strip().casefold()
        return bool(
            normalized_claim
            and normalized_quote
            and (normalized_claim in normalized_quote or normalized_quote in normalized_claim)
        )

    @staticmethod
    def _normalize_with_map(value: str) -> tuple[str, list[int]]:
        chars: list[str] = []
        mapping: list[int] = []
        for index, original in enumerate(value):
            for char in unicodedata.normalize("NFKC", original):
                if char.isspace():
                    continue
                chars.append(char)
                mapping.append(index)
        return "".join(chars), mapping

    @staticmethod
    def _location(block: ContentBlock, local_start: int, local_end: int) -> EvidenceLocation:
        if block.page is not None:
            return EvidenceLocation(
                page=block.page,
                page_index=block.page_index,
                bbox=block.bbox,
            )
        global_start = (
            block.start_offset + local_start if block.start_offset is not None else local_start
        )
        global_end = block.start_offset + local_end if block.start_offset is not None else local_end
        return EvidenceLocation(start_offset=global_start, end_offset=global_end)
