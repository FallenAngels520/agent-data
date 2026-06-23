from agent_data.domain.models import AgentReadyPackage
from agent_data.domain.schema import agent_ready_json_schema, validate_agent_ready_package


def test_schema_has_required_top_level_contract() -> None:
    schema = agent_ready_json_schema()
    assert schema["title"] == "AgentReadyPackage"
    for field in (
        "id",
        "schema_version",
        "status",
        "source",
        "content",
        "knowledge",
        "lineage",
        "quality",
    ):
        assert field in schema["required"]


def test_validate_rejects_incomplete_package() -> None:
    try:
        validate_agent_ready_package({"id": "x"})
    except ValueError as exc:
        assert "schema_version" in str(exc)
    else:
        raise AssertionError("expected schema validation failure")


def test_package_model_forbids_unknown_fields() -> None:
    assert AgentReadyPackage.model_config["extra"] == "forbid"
