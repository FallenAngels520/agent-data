from pathlib import Path

import httpx
import pytest

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.sources.resolver import SourceResolver


def test_resolves_local_pdf_and_hash_is_stable(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\ncontent")
    resolver = SourceResolver()

    first = resolver.resolve(str(pdf))
    second = resolver.resolve(str(pdf))

    assert first.kind == "pdf"
    assert first.raw_hash == second.raw_hash
    assert first.raw_hash.startswith("sha256:")
    assert first.filename == "sample.pdf"


def test_missing_local_file_is_invalid_input(tmp_path: Path) -> None:
    resolver = SourceResolver()
    with pytest.raises(PipelineError) as exc:
        resolver.resolve(str(tmp_path / "missing.pdf"))
    assert exc.value.code == ErrorCode.INVALID_INPUT


@pytest.mark.parametrize("value", ["ftp://example.com/a", "file:///tmp/a.pdf"])
def test_rejects_unsupported_url_schemes(value: str) -> None:
    with pytest.raises(PipelineError) as exc:
        SourceResolver().resolve(value)
    assert exc.value.code == ErrorCode.INVALID_INPUT


@pytest.mark.parametrize("url", ["http://127.0.0.1/a", "http://localhost/a", "http://10.0.0.1/a"])
def test_rejects_private_or_loopback_urls(url: str) -> None:
    with pytest.raises(PipelineError) as exc:
        SourceResolver().resolve(url)
    assert exc.value.code == ErrorCode.PRIVATE_NETWORK_BLOCKED


def test_can_explicitly_allow_private_url() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"<html><article>Hello</article></html>")
    )
    with httpx.Client(transport=transport) as client:
        source = SourceResolver(client=client, allow_private_networks=True).resolve(
            "http://127.0.0.1/page"
        )
    assert source.kind == "url"
    assert source.canonical_url == "http://127.0.0.1/page"


def test_enforces_maximum_download_size() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 11))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(PipelineError) as exc:
            SourceResolver(client=client, max_download_bytes=10).resolve("https://example.com")
    assert exc.value.code == ErrorCode.CONTENT_TOO_LARGE


def test_rejects_redirect_from_public_url_to_private_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "93.184.216.34":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        return httpx.Response(200, content=b"private")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PipelineError) as exc:
            SourceResolver(client=client).resolve("https://93.184.216.34/article")
    assert exc.value.code == ErrorCode.PRIVATE_NETWORK_BLOCKED
