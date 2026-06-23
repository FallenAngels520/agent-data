import json
from pathlib import Path

import httpx
import pytest

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import ResolvedSource
from agent_data.parsers.mineru import MinerUParser

FIXTURES = Path(__file__).parents[1] / "fixtures"


def source() -> ResolvedSource:
    return ResolvedSource(
        kind="pdf",
        original="sample.pdf",
        filename="sample.pdf",
        media_type="application/pdf",
        raw_bytes=b"%PDF fixture",
        raw_hash="sha256:fixture",
    )


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_mineru_sends_required_fields_and_normalizes_blocks() -> None:
    seen: dict[str, bytes | str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read()
        return httpx.Response(200, json=fixture("mineru_success.json"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        parsed = MinerUParser("http://mineru:8000", client=client).parse(source())

    body = seen["body"]
    assert isinstance(body, bytes)
    assert seen["url"] == "http://mineru:8000/file_parse"
    assert b'name="return_md"' in body and b"true" in body
    assert b'name="return_content_list"' in body
    assert b'name="return_middle_json"' in body
    assert b'name="end_page_id"' in body and b"99999" in body
    assert parsed.parser_name == "mineru"
    assert parsed.parser_version == "3.0.0"
    assert [block.type for block in parsed.content_blocks] == [
        "title",
        "text",
        "table",
        "list",
        "equation",
    ]
    assert parsed.content_blocks[2].page == 2
    assert parsed.content_blocks[2].page_index == 1
    assert parsed.content_blocks[2].bbox == [10, 200, 900, 500]
    assert "A" in parsed.content_blocks[2].text
    assert parsed.content_blocks[3].text == "One\nTwo"


def test_mineru_accepts_already_decoded_content_list() -> None:
    payload = fixture("mineru_success.json")
    payload["results"]["sample"]["content_list"] = json.loads(
        payload["results"]["sample"]["content_list"]
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as client:
        parsed = MinerUParser("http://mineru", client=client).parse(source())
    assert len(parsed.content_blocks) == 5


def test_mineru_2_1_content_list_is_enriched_with_middle_json_bbox() -> None:
    payload = fixture("mineru_success.json")
    content_list = json.loads(payload["results"]["sample"]["content_list"])
    for item in content_list:
        item.pop("bbox", None)
    payload["results"]["sample"]["content_list"] = json.dumps(content_list)
    payload["results"]["sample"]["middle_json"] = json.dumps(
        {
            "pdf_info": [
                {
                    "para_blocks": [
                        {
                            "type": "title",
                            "bbox": [10, 20, 900, 80],
                            "lines": [{"spans": [{"content": "Title"}]}],
                        },
                        {
                            "type": "text",
                            "bbox": [10, 100, 900, 160],
                            "lines": [{"spans": [{"content": "Paragraph"}]}],
                        },
                    ]
                },
                {
                    "para_blocks": [
                        {"type": "table", "bbox": [10, 200, 900, 500], "blocks": []},
                        {
                            "type": "list",
                            "bbox": [10, 500, 900, 700],
                            "lines": [{"spans": [{"content": "One Two"}]}],
                        },
                        {
                            "type": "interline_equation",
                            "bbox": [10, 710, 900, 760],
                            "lines": [{"spans": [{"content": "x=1"}]}],
                        },
                    ]
                },
            ]
        }
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as client:
        parsed = MinerUParser("http://mineru", client=client).parse(source())
    assert [block.bbox for block in parsed.content_blocks] == [
        [10, 20, 900, 80],
        [10, 100, 900, 160],
        [10, 200, 900, 500],
        [10, 500, 900, 700],
        [10, 710, 900, 760],
    ]


def test_mineru_missing_content_list_is_retained_as_warning() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=fixture("mineru_missing_content_list.json"))
    )
    with httpx.Client(transport=transport) as client:
        parsed = MinerUParser("http://mineru", client=client).parse(source())
    assert parsed.markdown == "# Title"
    assert parsed.content_blocks == []
    assert "EVIDENCE_UNLOCATABLE" in parsed.warnings


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"results": {}},
        {"results": {"sample": {"md_content": "x", "content_list": "not-json"}}},
    ],
)
def test_mineru_rejects_unknown_contract(payload: dict) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(PipelineError) as exc:
            MinerUParser("http://mineru", client=client).parse(source())
    assert exc.value.code == ErrorCode.PARSER_CONTRACT_MISMATCH


def test_mineru_maps_http_failure() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503, text="busy"))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(PipelineError) as exc:
            MinerUParser("http://mineru", client=client).parse(source())
    assert exc.value.code == ErrorCode.PARSER_FAILED
    assert exc.value.retryable is True


def test_mineru_maps_network_failure_without_losing_original_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PipelineError) as exc:
            MinerUParser("http://mineru", client=client).parse(source())
    assert exc.value.code == ErrorCode.PARSER_FAILED
    assert exc.value.retryable is True
