from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import (
    ContentBlock,
    ExtractionLineage,
    ExtractionResult,
)
from agent_data.extraction.prompts import PROMPT_VERSION, SYSTEM_PROMPT


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 120,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    def extract(
        self, blocks: list[ContentBlock], task_context: str | None = None
    ) -> ExtractionResult:
        block_payload = [
            {"block_id": block.block_id, "type": block.type, "text": block.text} for block in blocks
        ]
        user_payload: dict[str, Any] = {"blocks": block_payload}
        if task_context:
            user_payload["task_context"] = task_context
        request_payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response: httpx.Response | None = None
        try:
            if self.http_client is not None:
                response = self.http_client.post(
                    f"{self.base_url}/chat/completions",
                    json=request_payload,
                    headers=headers,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        json=request_payload,
                        headers=headers,
                    )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            status = response.status_code if response is not None else 0
            raise PipelineError(
                ErrorCode.LLM_FAILED,
                f"LLM request failed: {exc}",
                stage="extract",
                retryable=status == 429 or status >= 500 or isinstance(exc, httpx.TimeoutException),
            ) from exc
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content) if isinstance(content, str) else content
            result = ExtractionResult.model_validate(parsed)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise PipelineError(
                ErrorCode.LLM_CONTRACT_MISMATCH,
                f"Unexpected LLM response: {exc}",
                stage="extract",
                remediation="Check model JSON-mode support and extraction prompt",
            ) from exc
        if task_context and (result.relevance is None or result.actionability is None):
            raise PipelineError(
                ErrorCode.LLM_CONTRACT_MISMATCH,
                "Task-aware extraction requires relevance and actionability scores",
                stage="extract",
                remediation="Use a model that follows the task-aware extraction contract",
            )
        result.lineage = ExtractionLineage(
            provider=self.base_url,
            model=self.model,
            prompt_version=PROMPT_VERSION,
        )
        return result
