from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import ContentBlock, ParsedDocument, ResolvedSource

Extractor = Callable[[str, str], dict[str, Any]]


class TrafilaturaParser:
    name = "trafilatura"

    def __init__(self, *, extractor: Extractor | None = None) -> None:
        self.extractor = extractor or self._extract

    def supports(self, source: ResolvedSource) -> bool:
        return source.kind == "url"

    def parse(self, source: ResolvedSource) -> ParsedDocument:
        if not self.supports(source):
            raise PipelineError(
                ErrorCode.PARSER_UNSUPPORTED,
                "Trafilatura parser only supports URL sources",
                stage="parse",
            )
        html = source.raw_bytes.decode("utf-8", errors="replace")
        try:
            result = self.extractor(html, source.canonical_url or source.original)
        except PipelineError:
            raise
        except Exception as exc:
            raise PipelineError(
                ErrorCode.PARSER_FAILED,
                f"Trafilatura extraction failed: {exc}",
                stage="parse",
            ) from exc
        markdown = str(result.get("markdown") or "").strip()
        if self._is_unusable(markdown):
            raise PipelineError(
                ErrorCode.CONTENT_UNUSABLE,
                "Web page did not contain usable article content",
                stage="parse",
                remediation="Check whether the page requires login or JavaScript rendering",
            )
        blocks = self._blocks(markdown, source.raw_hash)
        metadata = {
            "title": result.get("title"),
            "author": result.get("author"),
            "published_at": result.get("date"),
        }
        return ParsedDocument(
            markdown=markdown,
            content_blocks=blocks,
            metadata=metadata,
            parser_name=self.name,
            parser_version=self._version(),
        )

    @staticmethod
    def _blocks(markdown: str, source_hash: str) -> list[ContentBlock]:
        blocks: list[ContentBlock] = []
        for order, match in enumerate(
            re.finditer(r"(?ms)(?:^|\n\s*\n)(.+?)(?=\n\s*\n|\Z)", markdown)
        ):
            text = match.group(1).strip()
            if not text:
                continue
            start = markdown.find(text, match.start())
            end = start + len(text)
            block_type = "title" if re.match(r"^#{1,6}\s+", text) else "text"
            display_text = re.sub(r"^#{1,6}\s+", "", text) if block_type == "title" else text
            material = f"{source_hash}|{order}|{start}|{end}|{display_text}"
            blocks.append(
                ContentBlock(
                    block_id=f"block_{hashlib.sha256(material.encode()).hexdigest()[:16]}",
                    type=block_type,
                    text=display_text,
                    order=order,
                    start_offset=start,
                    end_offset=end,
                    source_location={"format": "markdown"},
                )
            )
        return blocks

    @staticmethod
    def _is_unusable(markdown: str) -> bool:
        normalized = re.sub(r"\s+", " ", markdown).strip().lower()
        if not normalized:
            return True
        return bool(
            re.fullmatch(r"(?:404|403)(?: error)?(?: not found| forbidden)?[.!]?", normalized)
        )

    @staticmethod
    def _extract(html: str, url: str) -> dict[str, Any]:
        try:
            import trafilatura
        except ImportError as exc:
            raise RuntimeError("trafilatura is not installed") from exc
        markdown = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            include_tables=True,
        )
        metadata_raw = trafilatura.extract(html, url=url, output_format="json", with_metadata=True)
        metadata = json.loads(metadata_raw) if metadata_raw else {}
        return {
            "markdown": markdown,
            "title": metadata.get("title"),
            "author": metadata.get("author"),
            "date": metadata.get("date"),
        }

    @staticmethod
    def _version() -> str:
        try:
            from importlib.metadata import version

            return version("trafilatura")
        except Exception:
            return "unknown"
