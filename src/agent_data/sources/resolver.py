from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import socket
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import ResolvedSource


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


class SourceResolver:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        allow_private_networks: bool = False,
        max_download_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        self.client = client
        self.allow_private_networks = allow_private_networks
        self.max_download_bytes = max_download_bytes

    def resolve(self, value: str) -> ResolvedSource:
        lowered = value.lower()
        if lowered.startswith(("http://", "https://")):
            return self._resolve_url(value)
        if "://" in value:
            parsed = urlsplit(value)
            raise PipelineError(
                ErrorCode.INVALID_INPUT,
                f"Unsupported URL scheme: {parsed.scheme}",
                stage="source",
            )
        return self._resolve_pdf(Path(value))

    def _resolve_pdf(self, path: Path) -> ResolvedSource:
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise PipelineError(
                ErrorCode.INVALID_INPUT,
                f"PDF file does not exist or is not a PDF: {path}",
                stage="source",
            )
        raw = path.read_bytes()
        return ResolvedSource(
            kind="pdf",
            original=str(path),
            filename=path.name,
            media_type="application/pdf",
            raw_bytes=raw,
            raw_hash=sha256_bytes(raw),
        )

    def _resolve_url(self, value: str) -> ResolvedSource:
        canonical = self._canonical_url(value)
        host = urlsplit(canonical).hostname or ""
        if not self.allow_private_networks and self._is_private_host(host):
            raise PipelineError(
                ErrorCode.PRIVATE_NETWORK_BLOCKED,
                f"Private or loopback URL is blocked: {host}",
                stage="source",
            )
        try:
            if self.client is not None:
                response = self.client.get(canonical, follow_redirects=True)
            else:
                with httpx.Client(timeout=30, follow_redirects=True) as client:
                    response = client.get(canonical)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PipelineError(
                ErrorCode.SOURCE_FETCH_FAILED,
                f"Failed to fetch URL: {exc}",
                stage="source",
                retryable=True,
            ) from exc
        if not self.allow_private_networks:
            visited = [item.request.url for item in response.history] + [response.url]
            blocked = next(
                (url.host for url in visited if url.host and self._is_private_host(url.host)),
                None,
            )
            if blocked:
                raise PipelineError(
                    ErrorCode.PRIVATE_NETWORK_BLOCKED,
                    f"Redirect reached a private or loopback host: {blocked}",
                    stage="source",
                )
        raw = response.content
        if len(raw) > self.max_download_bytes:
            raise PipelineError(
                ErrorCode.CONTENT_TOO_LARGE,
                f"Downloaded content exceeds {self.max_download_bytes} bytes",
                stage="source",
            )
        media_type = response.headers.get("content-type", "text/html").split(";", 1)[0]
        filename = Path(urlsplit(str(response.url)).path).name or "index.html"
        return ResolvedSource(
            kind="url",
            original=value,
            canonical_url=str(response.url),
            filename=filename,
            media_type=media_type or mimetypes.guess_type(filename)[0] or "text/html",
            raw_bytes=raw,
            raw_hash=sha256_bytes(raw),
            response_metadata={"status_code": response.status_code},
        )

    @staticmethod
    def _canonical_url(value: str) -> str:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        if not host:
            raise PipelineError(ErrorCode.INVALID_INPUT, "URL must contain a host", stage="source")
        port = parsed.port
        netloc = host
        if port and not (
            (parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)
        ):
            netloc = f"{host}:{port}"
        path = parsed.path or "/"
        return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))

    @staticmethod
    def _is_private_host(host: str) -> bool:
        if host.lower() == "localhost":
            return True
        try:
            return not ipaddress.ip_address(host).is_global
        except ValueError:
            pass
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
        except socket.gaierror:
            return False
        return any(not ipaddress.ip_address(address).is_global for address in addresses)
