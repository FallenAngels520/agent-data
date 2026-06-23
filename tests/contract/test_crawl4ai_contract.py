import json

import httpx
import pytest

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import ResolvedSource
from agent_data.parsers.crawl4ai import Crawl4AIParser


def source() -> ResolvedSource:
    return ResolvedSource(
        kind="url",
        original="https://example.com/article",
        canonical_url="https://example.com/article",
        filename="article",
        media_type="text/html",
        raw_bytes=b"<html></html>",
        raw_hash="sha256:fixture",
    )


def test_crawl4ai_submits_task_with_auth_and_normalizes_markdown_blocks() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.setdefault("requests", []).append(request)
        if request.url.path == "/crawl":
            seen["crawl_json"] = request.read().decode()
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "results": [
                        {
                            "markdown": "# Title\n\nFirst paragraph.\n\nSecond paragraph.",
                            "metadata": {
                                "title": "Title",
                                "author": "Author",
                                "date": "2026-06-01",
                            },
                        },
                    ],
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    parser = Crawl4AIParser(
        "http://crawl4ai.local",
        api_token="secret",
        client=client,
        poll_interval_seconds=0,
    )

    parsed = parser.parse(source())

    assert parsed.parser_name == "crawl4ai"
    assert parsed.metadata == {
        "title": "Title",
        "author": "Author",
        "published_at": "2026-06-01",
    }
    assert [block.type for block in parsed.content_blocks] == ["title", "text", "text"]
    assert parsed.content_blocks[1].start_offset is not None
    requests = seen["requests"]
    assert requests[0].headers["authorization"] == "Bearer secret"
    assert json.loads(seen["crawl_json"])["urls"] == ["https://example.com/article"]


def test_crawl4ai_accepts_task_id_response_for_older_async_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/crawl":
            return httpx.Response(200, json={"task_id": "task-1"})
        if request.url.path == "/task/task-1":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "result": {
                        "markdown": "# Title\n\nFirst paragraph.",
                        "metadata": {"title": "Title"},
                    },
                },
            )
        return httpx.Response(404)

    parser = Crawl4AIParser(
        "http://crawl4ai.local",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_seconds=0,
    )

    parsed = parser.parse(source())

    assert parsed.metadata["title"] == "Title"
    assert parsed.content_blocks[0].text == "Title"


def test_crawl4ai_uses_raw_markdown_when_fit_markdown_is_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "results": [
                    {
                        "markdown": {
                            "fit_markdown": "",
                            "raw_markdown": "# Title\n\nFirst paragraph.",
                        }
                    }
                ],
            },
        )

    parser = Crawl4AIParser(
        "http://crawl4ai.local",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_seconds=0,
    )

    parsed = parser.parse(source())

    assert parsed.markdown == "# Title\n\nFirst paragraph."


def test_crawl4ai_maps_failed_task_to_parser_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/crawl":
            return httpx.Response(200, json={"task_id": "task-1"})
        return httpx.Response(200, json={"status": "failed", "error": "blocked"})

    parser = Crawl4AIParser(
        "http://crawl4ai.local",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_seconds=0,
    )

    with pytest.raises(PipelineError) as exc:
        parser.parse(source())

    assert exc.value.code == ErrorCode.PARSER_FAILED
    assert exc.value.stage == "parse"


def test_crawl4ai_rejects_missing_task_id_contract() -> None:
    parser = Crawl4AIParser(
        "http://crawl4ai.local",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
        ),
        poll_interval_seconds=0,
    )

    with pytest.raises(PipelineError) as exc:
        parser.parse(source())

    assert exc.value.code == ErrorCode.PARSER_CONTRACT_MISMATCH


def test_crawl4ai_times_out_waiting_for_task_completion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/crawl":
            return httpx.Response(200, json={"task_id": "task-1"})
        return httpx.Response(200, json={"status": "processing"})

    parser = Crawl4AIParser(
        "http://crawl4ai.local",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        timeout_seconds=0,
        poll_interval_seconds=0,
    )

    with pytest.raises(PipelineError) as exc:
        parser.parse(source())

    assert exc.value.code == ErrorCode.PARSER_FAILED
    assert exc.value.retryable is True


def test_crawl4ai_rejects_empty_markdown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/crawl":
            return httpx.Response(200, json={"task_id": "task-1"})
        return httpx.Response(200, json={"status": "completed", "result": {"markdown": ""}})

    parser = Crawl4AIParser(
        "http://crawl4ai.local",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_seconds=0,
    )

    with pytest.raises(PipelineError) as exc:
        parser.parse(source())

    assert exc.value.code == ErrorCode.CONTENT_UNUSABLE
