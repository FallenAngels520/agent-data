from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import ContentBlock, ParsedDocument, ResolvedSource


class Crawl4AIParser:
    name = "crawl4ai"

    def __init__(
        self,
        base_url: str,
        *,
        api_token: str | None = None,
        client: httpx.Client | None = None,
        timeout_seconds: float = 300,
        poll_interval_seconds: float = 1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def supports(self, source: ResolvedSource) -> bool:
        return source.kind == "url"

    def parse(self, source: ResolvedSource) -> ParsedDocument:
        if not self.supports(source):
            raise PipelineError(
                ErrorCode.PARSER_UNSUPPORTED,
                "Crawl4AI parser only supports URL sources",
                stage="parse",
            )
        url = source.canonical_url or source.original
        task_id = self._submit(url)
        payload = self._wait(task_id)
        return self._convert(payload, source)

    def _submit(self, url: str) -> str:
        response = self._request("POST", "/crawl", json={"urls": url, "priority": 10})
        payload = self._json(response, "crawl submission")
        task_id = payload.get("task_id") if isinstance(payload, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise self._contract_error("crawl submission did not return task_id")
        return task_id

    def _wait(self, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            response = self._request("GET", f"/task/{task_id}")
            payload = self._json(response, "task status")
            if not isinstance(payload, dict):
                raise self._contract_error("task status must be an object")
            status = payload.get("status")
            if status == "completed":
                return payload
            if status in {"failed", "error", "cancelled"}:
                message = str(payload.get("error") or payload.get("message") or status)
                raise PipelineError(
                    ErrorCode.PARSER_FAILED,
                    f"Crawl4AI task failed: {message}",
                    stage="parse",
                    retryable=False,
                )
            if time.monotonic() >= deadline:
                raise PipelineError(
                    ErrorCode.PARSER_FAILED,
                    f"Crawl4AI task timed out: {task_id}",
                    stage="parse",
                    retryable=True,
                )
            time.sleep(max(self.poll_interval_seconds, 0))

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if self.api_token:
            headers = {**headers, "Authorization": f"Bearer {self.api_token}"}
        try:
            if self.client is not None:
                response = self.client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=headers,
                    **kwargs,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.request(
                        method,
                        f"{self.base_url}{path}",
                        headers=headers,
                        **kwargs,
                    )
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise PipelineError(
                ErrorCode.PARSER_FAILED,
                f"Crawl4AI request failed: {exc}",
                stage="parse",
                retryable=True,
            ) from exc

    def _convert(self, payload: dict[str, Any], source: ResolvedSource) -> ParsedDocument:
        result = payload.get("result")
        if not isinstance(result, dict):
            raise self._contract_error("completed task did not include result object")
        markdown = self._markdown(result).strip()
        if self._is_unusable(markdown):
            raise PipelineError(
                ErrorCode.CONTENT_UNUSABLE,
                "Crawl4AI did not return usable markdown",
                stage="parse",
                remediation=(
                    "Check whether the page requires login or a crawl configuration override"
                ),
            )
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        return ParsedDocument(
            markdown=markdown,
            content_blocks=self._blocks(markdown, source.raw_hash),
            metadata={
                "title": metadata.get("title"),
                "author": metadata.get("author"),
                "published_at": metadata.get("date") or metadata.get("published_at"),
            },
            parser_name=self.name,
            parser_version=str(payload.get("version", "docker-api")),
        )

    @staticmethod
    def _markdown(result: dict[str, Any]) -> str:
        value = result.get("markdown")
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("fit_markdown", "raw_markdown", "markdown"):
                item = value.get(key)
                if isinstance(item, str):
                    return item
        return ""

    @staticmethod
    def _blocks(markdown: str, source_hash: str) -> list[ContentBlock]:
        blocks: list[ContentBlock] = []
        offset = 0
        for order, paragraph in enumerate(markdown.split("\n\n")):
            text = paragraph.strip()
            if not text:
                offset += len(paragraph) + 2
                continue
            start = markdown.find(text, offset)
            end = start + len(text)
            block_type = "title" if text.startswith("#") else "text"
            display_text = text.lstrip("#").strip() if block_type == "title" else text
            material = f"{source_hash}|{order}|{start}|{end}|{display_text}"
            blocks.append(
                ContentBlock(
                    block_id=f"block_{hashlib.sha256(material.encode()).hexdigest()[:16]}",
                    type=block_type,
                    text=display_text,
                    order=order,
                    start_offset=start,
                    end_offset=end,
                    source_location={"format": "crawl4ai_markdown"},
                )
            )
            offset = end
        return blocks

    @staticmethod
    def _is_unusable(markdown: str) -> bool:
        return not markdown.strip()

    @staticmethod
    def _json(response: httpx.Response, context: str) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise Crawl4AIParser._contract_error(f"{context} was not valid JSON") from exc

    @staticmethod
    def _contract_error(message: str) -> PipelineError:
        return PipelineError(
            ErrorCode.PARSER_CONTRACT_MISMATCH,
            f"Unexpected Crawl4AI response: {message}",
            stage="parse",
            remediation="Verify the deployed Crawl4AI Docker API version and adapter contract",
        )
