from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import ResolvedSource
from agent_data.parsers.trafilatura_parser import TrafilaturaParser


def source(html: str = "<article>content</article>") -> ResolvedSource:
    return ResolvedSource(
        kind="url",
        original="https://example.com/article",
        canonical_url="https://example.com/article",
        filename="article",
        media_type="text/html",
        raw_bytes=html.encode(),
        raw_hash="sha256:fixture",
    )


def test_normalizes_markdown_and_metadata_into_ordered_blocks() -> None:
    def extractor(html: str, url: str) -> dict:
        return {
            "markdown": "# Title\n\nFirst paragraph.\n\n## Subhead\n\nSecond paragraph.",
            "title": "Title",
            "author": "Author",
            "date": "2026-06-01",
        }

    parsed = TrafilaturaParser(extractor=extractor).parse(source())
    assert parsed.metadata == {
        "title": "Title",
        "author": "Author",
        "published_at": "2026-06-01",
    }
    assert [block.type for block in parsed.content_blocks] == [
        "title",
        "text",
        "title",
        "text",
    ]
    assert [block.order for block in parsed.content_blocks] == [0, 1, 2, 3]
    assert parsed.content_blocks[1].start_offset is not None
    assert parsed.content_blocks[1].end_offset is not None


def test_rejects_empty_or_soft_404_content() -> None:
    for markdown in ("", "404 Not Found"):
        parser = TrafilaturaParser(extractor=lambda html, url, value=markdown: {"markdown": value})
        try:
            parser.parse(source())
        except PipelineError as exc:
            assert exc.code == ErrorCode.CONTENT_UNUSABLE
        else:
            raise AssertionError("expected unusable content")


def test_rejects_non_url_source() -> None:
    pdf_source = source()
    pdf_source = pdf_source.model_copy(update={"kind": "pdf"})
    parser = TrafilaturaParser(extractor=lambda html, url: {"markdown": "x"})
    try:
        parser.parse(pdf_source)
    except PipelineError as exc:
        assert exc.code == ErrorCode.PARSER_UNSUPPORTED
    else:
        raise AssertionError("expected unsupported source")
