import os
from pathlib import Path

import pytest

from agent_data.parsers.mineru import MinerUParser
from agent_data.sources.resolver import SourceResolver

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_INTEGRATION") != "1",
    reason="set RUN_LIVE_INTEGRATION=1 to run live services",
)


def test_live_mineru_returns_markdown_and_locatable_blocks() -> None:
    pdf_path = Path(os.environ["TEST_PDF_PATH"])
    parser = MinerUParser(os.getenv("MINERU_BASE_URL", "http://192.168.0.213:8000"))
    parsed = parser.parse(SourceResolver().resolve(str(pdf_path)))
    assert parsed.markdown.strip()
    assert parsed.content_blocks
    assert all(block.page is not None and block.bbox is not None for block in parsed.content_blocks)
