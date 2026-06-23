import pytest

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import ParsedDocument, ResolvedSource
from agent_data.parsers.registry import ParserRegistry


class FakeParser:
    name = "fake"

    def supports(self, source: ResolvedSource) -> bool:
        return source.kind == "pdf"

    def parse(self, source: ResolvedSource) -> ParsedDocument:
        return ParsedDocument(markdown="ok", parser_name=self.name, parser_version="1")


def source(kind: str = "pdf") -> ResolvedSource:
    return ResolvedSource(
        kind=kind,
        original="sample.pdf",
        filename="sample.pdf",
        media_type="application/pdf",
        raw_bytes=b"%PDF",
        raw_hash="sha256:test",
    )


def test_registry_selects_configured_supporting_parser() -> None:
    parser = FakeParser()
    registry = ParserRegistry({"fake": parser}, {"pdf": "fake"})
    assert registry.for_source(source()) is parser


def test_registry_rejects_unknown_configured_provider() -> None:
    registry = ParserRegistry({}, {"pdf": "missing"})
    with pytest.raises(PipelineError) as exc:
        registry.for_source(source())
    assert exc.value.code == ErrorCode.PARSER_NOT_CONFIGURED


def test_registry_rejects_parser_that_does_not_support_source() -> None:
    registry = ParserRegistry({"fake": FakeParser()}, {"url": "fake"})
    with pytest.raises(PipelineError) as exc:
        registry.for_source(source("url"))
    assert exc.value.code == ErrorCode.PARSER_UNSUPPORTED
