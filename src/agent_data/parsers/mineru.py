from __future__ import annotations

import hashlib
import json
import re
from html import unescape
from typing import Any

import httpx

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import ContentBlock, ParsedDocument, ResolvedSource


class MinerUParser:
    name = "mineru"

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 600,
        start_page: int = 0,
        end_page: int = 99999,
        language: str = "ch",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.start_page = start_page
        self.end_page = end_page
        self.language = language

    def supports(self, source: ResolvedSource) -> bool:
        return source.kind == "pdf"

    def parse(self, source: ResolvedSource) -> ParsedDocument:
        if not self.supports(source):
            raise PipelineError(
                ErrorCode.PARSER_UNSUPPORTED,
                "MinerU only supports PDF sources",
                stage="parse",
            )
        data = {
            "return_md": "true",
            "return_content_list": "true",
            "return_middle_json": "true",
            "table_enable": "true",
            "formula_enable": "true",
            "backend": "pipeline",
            "parse_method": "ocr",
            "lang_list": self.language,
            "start_page_id": str(self.start_page),
            "end_page_id": str(self.end_page),
        }
        files = {"files": (source.filename, source.raw_bytes, "application/pdf")}
        try:
            if self.client is not None:
                response = self.client.post(f"{self.base_url}/file_parse", data=data, files=files)
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(f"{self.base_url}/file_parse", data=data, files=files)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise PipelineError(
                ErrorCode.PARSER_FAILED,
                f"MinerU request failed: {exc}",
                stage="parse",
                retryable=isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))
                or getattr(response, "status_code", 0) >= 500,
            ) from exc
        return self._convert(payload, source)

    def _convert(self, payload: Any, source: ResolvedSource) -> ParsedDocument:
        try:
            results = payload["results"]
            if not isinstance(results, dict) or not results:
                raise TypeError("results must be a non-empty object")
            result = next(iter(results.values()))
            markdown = result["md_content"]
            if not isinstance(markdown, str):
                raise TypeError("md_content must be a string")
        except (KeyError, TypeError, StopIteration) as exc:
            raise self._contract_error(str(exc)) from exc

        raw_blocks = result.get("content_list")
        if raw_blocks is None:
            return ParsedDocument(
                markdown=markdown,
                parser_name=self.name,
                parser_version=str(payload.get("version", "unknown")),
                metadata={"backend": payload.get("backend")},
                warnings=["EVIDENCE_UNLOCATABLE"],
            )
        if isinstance(raw_blocks, str):
            try:
                raw_blocks = json.loads(raw_blocks)
            except json.JSONDecodeError as exc:
                raise self._contract_error("content_list is not valid JSON") from exc
        if not isinstance(raw_blocks, list):
            raise self._contract_error("content_list must be a list")

        locators = self._middle_locators(result.get("middle_json"))
        blocks: list[ContentBlock] = []
        for order, item in enumerate(raw_blocks):
            if not isinstance(item, dict):
                raise self._contract_error("content_list item must be an object")
            text = self._block_text(item)
            if not text.strip():
                continue
            page_index = item.get("page_idx")
            if not isinstance(page_index, int) or page_index < 0:
                raise self._contract_error("content block requires non-negative page_idx")
            block_type = self._block_type(item)
            bbox = item.get("bbox") or self._middle_bbox(
                locators,
                page_index=page_index,
                block_type=block_type,
                text=text,
            )
            block_id = self._block_id(source.raw_hash, order, page_index, bbox, text)
            blocks.append(
                ContentBlock(
                    block_id=block_id,
                    type=block_type,
                    text=text,
                    order=order,
                    page=page_index + 1,
                    page_index=page_index,
                    bbox=bbox,
                    source_location={"mineru_type": item.get("type")},
                )
            )
        warnings = []
        if any(block.bbox is None for block in blocks):
            warnings.append("BBOX_UNAVAILABLE")
        return ParsedDocument(
            markdown=markdown,
            content_blocks=blocks,
            parser_name=self.name,
            parser_version=str(payload.get("version", "unknown")),
            metadata={"backend": payload.get("backend")},
            warnings=warnings,
        )

    @classmethod
    def _middle_locators(cls, raw_middle: Any) -> list[dict[str, Any]]:
        if isinstance(raw_middle, str):
            try:
                raw_middle = json.loads(raw_middle)
            except json.JSONDecodeError:
                return []
        if not isinstance(raw_middle, dict) or not isinstance(raw_middle.get("pdf_info"), list):
            return []
        locators: list[dict[str, Any]] = []
        for page_index, page in enumerate(raw_middle["pdf_info"]):
            if not isinstance(page, dict):
                continue
            for block in page.get("para_blocks") or []:
                if not isinstance(block, dict) or not isinstance(block.get("bbox"), list):
                    continue
                locators.append(
                    {
                        "page_index": page_index,
                        "type": cls._middle_type(str(block.get("type") or "text")),
                        "text": cls._recursive_text(block),
                        "bbox": block["bbox"],
                        "used": False,
                    }
                )
        return locators

    @classmethod
    def _middle_bbox(
        cls,
        locators: list[dict[str, Any]],
        *,
        page_index: int,
        block_type: str,
        text: str,
    ) -> list[float] | None:
        candidates = [
            locator
            for locator in locators
            if not locator["used"]
            and locator["page_index"] == page_index
            and locator["type"] == block_type
        ]
        normalized = cls._normalize_text(text)
        matching = [
            locator
            for locator in candidates
            if locator["text"]
            and (
                normalized in cls._normalize_text(locator["text"])
                or cls._normalize_text(locator["text"]) in normalized
            )
        ]
        selected = matching[0] if matching else (candidates[0] if candidates else None)
        if selected is None:
            return None
        selected["used"] = True
        return selected["bbox"]

    @staticmethod
    def _middle_type(value: str) -> str:
        if value in {"title", "doc_title"}:
            return "title"
        if value in {"interline_equation", "equation"}:
            return "equation"
        return value

    @classmethod
    def _recursive_text(cls, value: Any) -> str:
        if isinstance(value, dict):
            direct = value.get("content")
            pieces = [direct] if isinstance(direct, str) else []
            for key, child in value.items():
                if key not in {"content", "bbox"}:
                    text = cls._recursive_text(child)
                    if text:
                        pieces.append(text)
            return " ".join(pieces)
        if isinstance(value, list):
            return " ".join(filter(None, (cls._recursive_text(item) for item in value)))
        return ""

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    @staticmethod
    def _block_type(item: dict[str, Any]) -> str:
        if item.get("type") == "text" and int(item.get("text_level") or 0) > 0:
            return "title"
        return str(item.get("type") or "text")

    @staticmethod
    def _block_text(item: dict[str, Any]) -> str:
        for key in ("text", "code_body", "content"):
            value = item.get(key)
            if isinstance(value, str):
                return value.strip()
        values = item.get("list_items")
        if isinstance(values, list):
            return "\n".join(str(value) for value in values).strip()
        table = item.get("table_body")
        if isinstance(table, str):
            return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", table))).strip()
        return ""

    @staticmethod
    def _block_id(
        source_hash: str,
        order: int,
        page_index: int,
        bbox: Any,
        text: str,
    ) -> str:
        material = json.dumps(
            [source_hash, order, page_index, bbox, text], ensure_ascii=False, separators=(",", ":")
        )
        return f"block_{hashlib.sha256(material.encode()).hexdigest()[:16]}"

    @staticmethod
    def _contract_error(message: str) -> PipelineError:
        return PipelineError(
            ErrorCode.PARSER_CONTRACT_MISMATCH,
            f"Unexpected MinerU response: {message}",
            stage="parse",
            remediation="Verify the deployed MinerU version and adapter contract",
        )
