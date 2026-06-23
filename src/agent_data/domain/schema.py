from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from agent_data.domain.models import AgentReadyPackage


def agent_ready_json_schema() -> dict[str, Any]:
    return AgentReadyPackage.model_json_schema()


def validate_agent_ready_package(value: dict[str, Any]) -> AgentReadyPackage:
    try:
        return AgentReadyPackage.model_validate(value)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
