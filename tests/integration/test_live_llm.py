import os

import pytest

from agent_data.domain.models import ContentBlock
from agent_data.extraction.llm_client import OpenAICompatibleClient

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_INTEGRATION") != "1",
    reason="set RUN_LIVE_INTEGRATION=1 to run live services",
)


def test_live_llm_returns_groundable_claim_contract() -> None:
    block = ContentBlock(
        block_id="block_live",
        type="text",
        text="Revenue increased 10% in 2025.",
        order=0,
    )
    client = OpenAICompatibleClient(
        api_key=os.environ["LLM_API_KEY"],
        model=os.environ["LLM_MODEL"],
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    )
    result = client.extract([block], task_context="Analyze revenue growth")
    assert result.claims
    assert all(claim.quote and claim.candidate_block_id for claim in result.claims)
    assert result.relevance is not None
    assert result.actionability is not None
