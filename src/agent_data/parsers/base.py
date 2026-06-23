from __future__ import annotations

from typing import Protocol

from agent_data.domain.models import ParsedDocument, ResolvedSource


class DocumentParser(Protocol):
    name: str

    def supports(self, source: ResolvedSource) -> bool: ...

    def parse(self, source: ResolvedSource) -> ParsedDocument: ...
