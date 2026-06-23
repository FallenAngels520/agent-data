from __future__ import annotations

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import ResolvedSource
from agent_data.parsers.base import DocumentParser


class ParserRegistry:
    def __init__(self, parsers: dict[str, DocumentParser], configured: dict[str, str]) -> None:
        self.parsers = parsers
        self.configured = configured

    def for_source(self, source: ResolvedSource) -> DocumentParser:
        parser_name = self.configured.get(source.kind)
        parser = self.parsers.get(parser_name or "")
        if parser is None:
            raise PipelineError(
                ErrorCode.PARSER_NOT_CONFIGURED,
                f"No registered parser named {parser_name!r} for {source.kind}",
                stage="parse",
            )
        if not parser.supports(source):
            raise PipelineError(
                ErrorCode.PARSER_UNSUPPORTED,
                f"Parser {parser_name!r} does not support {source.kind}",
                stage="parse",
            )
        return parser
