from agent_data.domain.models import ClaimCandidate, ContentBlock
from agent_data.evidence.verifier import EvidenceVerifier


def claim(block_id: str, quote: str = "Revenue increased 10%.") -> ClaimCandidate:
    return ClaimCandidate(
        text="Revenue increased 10%.",
        claim_type="fact",
        confidence=0.9,
        quote=quote,
        candidate_block_id=block_id,
    )


def test_verifies_exact_quote_in_candidate_pdf_block() -> None:
    block = ContentBlock(
        block_id="b1",
        type="text",
        text="In 2025, Revenue increased 10%.",
        order=0,
        page=3,
        page_index=2,
        bbox=[1, 2, 3, 4],
    )
    result = EvidenceVerifier().verify([claim("b1")], [block], "sha256:doc")
    verified = result.claims[0]
    assert verified.verification_status == "verified"
    assert verified.evidence is not None
    assert verified.evidence.location.page == 3
    assert verified.evidence.location.bbox == [1, 2, 3, 4]
    assert verified.evidence.content_hash == "sha256:doc"


def test_normalizes_unicode_and_whitespace_conservatively() -> None:
    block = ContentBlock(block_id="b1", type="text", text="Revenue\u3000increased   10%.", order=0)
    result = EvidenceVerifier().verify(
        [claim("b1", "Revenue increased 10%.")], [block], "sha256:doc"
    )
    assert result.claims[0].verification_status == "verified"


def test_matches_ocr_text_when_word_boundaries_are_missing() -> None:
    block = ContentBlock(
        block_id="b1",
        type="text",
        text="The model was able torepresentflowvariation for most percentiles.",
        order=0,
    )
    candidate = ClaimCandidate(
        text="The model was able to represent flow variation for most percentiles.",
        claim_type="fact",
        confidence=0.9,
        quote="The model was able to represent flow variation for most percentiles.",
        candidate_block_id="b1",
    )
    result = EvidenceVerifier().verify([candidate], [block], "sha256:doc")
    assert result.claims[0].verification_status == "verified"


def test_unique_full_document_fallback_repairs_wrong_candidate() -> None:
    blocks = [
        ContentBlock(block_id="b1", type="text", text="Other", order=0),
        ContentBlock(block_id="b2", type="text", text="Revenue increased 10%.", order=1),
    ]
    result = EvidenceVerifier().verify([claim("b1")], blocks, "sha256:doc")
    assert result.claims[0].verification_status == "verified"
    assert result.claims[0].evidence.block_id == "b2"  # type: ignore[union-attr]


def test_ambiguous_full_document_match_needs_review() -> None:
    blocks = [
        ContentBlock(block_id="b1", type="text", text="Other", order=0),
        ContentBlock(block_id="b2", type="text", text="Revenue increased 10%.", order=1),
        ContentBlock(block_id="b3", type="text", text="Revenue increased 10%.", order=2),
    ]
    result = EvidenceVerifier().verify([claim("b1")], blocks, "sha256:doc")
    assert result.claims[0].verification_status == "needs_review"
    assert result.claims[0].evidence is None


def test_missing_quote_is_rejected() -> None:
    block = ContentBlock(block_id="b1", type="text", text="Other", order=0)
    result = EvidenceVerifier().verify([claim("b1")], [block], "sha256:doc")
    assert result.claims[0].verification_status == "rejected"


def test_url_location_uses_document_offsets() -> None:
    block = ContentBlock(
        block_id="b1",
        type="text",
        text="Before Revenue increased 10%. After",
        order=0,
        start_offset=100,
        end_offset=136,
    )
    result = EvidenceVerifier().verify([claim("b1")], [block], "sha256:doc")
    location = result.claims[0].evidence.location  # type: ignore[union-attr]
    assert location.start_offset == 107
    assert location.end_offset == 129


def test_quote_that_exists_but_does_not_directly_support_claim_needs_review() -> None:
    block = ContentBlock(block_id="b1", type="text", text="Revenue increased 10%.", order=0)
    contradictory = ClaimCandidate(
        text="Revenue decreased 10%.",
        claim_type="fact",
        confidence=0.9,
        quote="Revenue increased 10%.",
        candidate_block_id="b1",
    )
    result = EvidenceVerifier().verify([contradictory], [block], "sha256:doc")
    assert result.claims[0].verification_status == "needs_review"
    assert result.claims[0].evidence is None
