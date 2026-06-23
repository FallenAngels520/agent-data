import json
from pathlib import Path

import httpx
import pytest

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import ContentBlock
from agent_data.extraction.llm_client import OpenAICompatibleClient

FIXTURE = Path(__file__).parents[1] / "fixtures" / "llm_extraction.json"


def block() -> ContentBlock:
    return ContentBlock(block_id="block_1", type="text", text="Revenue increased 10%.", order=0)


def test_parses_openai_compatible_structured_response_and_records_lineage() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["request"] = json.loads(request.read())
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OpenAICompatibleClient(
            api_key="secret",
            model="test-model",
            base_url="https://llm.example/v1",
            http_client=http_client,
        )
        result = client.extract([block()], task_context="Analyze growth")

    assert seen["authorization"] == "Bearer secret"
    request_payload = seen["request"]
    assert isinstance(request_payload, dict)
    system_prompt = request_payload["messages"][0]["content"]
    for required_field in (
        "summary",
        "key_points",
        "claims",
        "text",
        "claim_type",
        "confidence",
        "quote",
        "candidate_block_id",
        "relevance",
        "actionability",
    ):
        assert required_field in system_prompt
    assert "byte-for-byte identical" in system_prompt
    assert result.summary == "A summary"
    assert result.claims[0].candidate_block_id == "block_1"
    assert result.lineage.model == "test-model"
    assert result.lineage.prompt_version == "extract-v1"


@pytest.mark.parametrize(
    "payload", [{}, {"choices": []}, {"choices": [{"message": {"content": "x"}}]}]
)
def test_rejects_invalid_llm_contract(payload: dict) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as http_client:
        client = OpenAICompatibleClient(
            api_key="secret", model="m", base_url="https://llm.example/v1", http_client=http_client
        )
        with pytest.raises(PipelineError) as exc:
            client.extract([block()])
    assert exc.value.code == ErrorCode.LLM_CONTRACT_MISMATCH


def test_maps_retryable_llm_http_failure() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(429, text="slow down"))
    with httpx.Client(transport=transport) as http_client:
        client = OpenAICompatibleClient(
            api_key="secret", model="m", base_url="https://llm.example/v1", http_client=http_client
        )
        with pytest.raises(PipelineError) as exc:
            client.extract([block()])
    assert exc.value.code == ErrorCode.LLM_FAILED
    assert exc.value.retryable is True


def test_task_context_requires_task_scores_in_llm_response() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    content = json.loads(payload["choices"][0]["message"]["content"])
    content.pop("relevance")
    content.pop("actionability")
    payload["choices"][0]["message"]["content"] = json.dumps(content)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as http_client:
        client = OpenAICompatibleClient(
            api_key="secret",
            model="m",
            base_url="https://llm.example/v1",
            http_client=http_client,
        )
        with pytest.raises(PipelineError) as exc:
            client.extract([block()], task_context="Analyze growth")
    assert exc.value.code == ErrorCode.LLM_CONTRACT_MISMATCH
