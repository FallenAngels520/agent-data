from agent_data.domain.models import (
    ClaimCandidate,
    ContentBlock,
    ExtractionLineage,
    ExtractionResult,
)
from agent_data.extraction.extractor import DocumentExtractor


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[list[ContentBlock]] = []

    def extract(
        self, blocks: list[ContentBlock], task_context: str | None = None
    ) -> ExtractionResult:
        self.calls.append(blocks)
        first = blocks[0]
        return ExtractionResult(
            summary=f"Summary {len(self.calls)}",
            key_points=[first.text],
            claims=[
                ClaimCandidate(
                    text="Same claim",
                    claim_type="fact",
                    confidence=0.8,
                    quote=first.text,
                    candidate_block_id=first.block_id,
                )
            ],
            entities=["Entity"],
            topics=["Topic"],
            tags=["Tag"],
            lineage=ExtractionLineage(provider="fake", model="fake", prompt_version="extract-v1"),
        )


def make_block(index: int, text: str) -> ContentBlock:
    return ContentBlock(block_id=f"block_{index}", type="text", text=text, order=index)


def test_chunks_without_dropping_blocks_and_merges_duplicate_claims() -> None:
    client = FakeClient()
    extractor = DocumentExtractor(client, max_chunk_chars=12)
    blocks = [make_block(0, "1234567890"), make_block(1, "abcdefghij")]

    result = extractor.extract(blocks)

    assert len(client.calls) == 2
    assert [block.block_id for call in client.calls for block in call] == ["block_0", "block_1"]
    assert len(result.claims) == 1
    assert result.key_points == ["1234567890", "abcdefghij"]
    assert result.entities == ["Entity"]


def test_empty_document_returns_empty_extraction_without_llm_call() -> None:
    client = FakeClient()
    result = DocumentExtractor(client).extract([])
    assert client.calls == []
    assert result.claims == []
    assert result.summary == ""
