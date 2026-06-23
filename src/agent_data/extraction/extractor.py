from __future__ import annotations

import re
from typing import Protocol

from agent_data.domain.models import ContentBlock, ExtractionResult


class ExtractionClient(Protocol):
    def extract(
        self, blocks: list[ContentBlock], task_context: str | None = None
    ) -> ExtractionResult: ...


class DocumentExtractor:
    def __init__(self, client: ExtractionClient, *, max_chunk_chars: int = 12000) -> None:
        if max_chunk_chars <= 0:
            raise ValueError("max_chunk_chars must be positive")
        self.client = client
        self.max_chunk_chars = max_chunk_chars

    def extract(
        self, blocks: list[ContentBlock], task_context: str | None = None
    ) -> ExtractionResult:
        if not blocks:
            return ExtractionResult()
        results = [
            self.client.extract(chunk, task_context=task_context) for chunk in self._chunks(blocks)
        ]
        claims = []
        seen_claims: set[str] = set()
        for result in results:
            for claim in result.claims:
                key = re.sub(r"\W+", "", claim.text).casefold()
                if key not in seen_claims:
                    seen_claims.add(key)
                    claims.append(claim)
        return ExtractionResult(
            summary="\n\n".join(result.summary for result in results if result.summary),
            key_points=self._unique(item for result in results for item in result.key_points),
            claims=claims,
            entities=self._unique(item for result in results for item in result.entities),
            topics=self._unique(item for result in results for item in result.topics),
            tags=self._unique(item for result in results for item in result.tags),
            relevance=self._average(result.relevance for result in results),
            actionability=self._average(result.actionability for result in results),
            lineage=results[0].lineage,
        )

    def _chunks(self, blocks: list[ContentBlock]) -> list[list[ContentBlock]]:
        chunks: list[list[ContentBlock]] = []
        current: list[ContentBlock] = []
        size = 0
        for block in blocks:
            block_size = len(block.text)
            if current and size + block_size > self.max_chunk_chars:
                chunks.append(current)
                current = []
                size = 0
            current.append(block)
            size += block_size
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _unique(items: object) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in items:  # type: ignore[union-attr]
            key = item.casefold()
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    @staticmethod
    def _average(values: object) -> float | None:
        present = [value for value in values if value is not None]  # type: ignore[union-attr]
        if not present:
            return None
        return round(sum(present) / len(present), 6)
