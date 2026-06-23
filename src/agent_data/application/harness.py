from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, TypeVar

from agent_data.domain.errors import ErrorCode, PipelineError

T = TypeVar("T")


@dataclass(frozen=True)
class HarnessEvent:
    stage: str
    status: Literal["started", "retrying", "completed", "failed"]
    attempt: int
    timestamp: str
    error_code: str | None = None


class Harness:
    def __init__(self) -> None:
        self.events: list[HarnessEvent] = []

    def execute(self, stage: str, operation: Callable[[], T], *, retries: int = 0) -> T:
        self._event(stage, "started", 1)
        for attempt in range(1, retries + 2):
            try:
                result = operation()
                self._event(stage, "completed", attempt)
                return result
            except PipelineError as exc:
                if exc.retryable and attempt <= retries:
                    self._event(stage, "retrying", attempt, exc.code.value)
                    continue
                self._event(stage, "failed", attempt, exc.code.value)
                raise
        raise RuntimeError("unreachable")

    def _event(
        self,
        stage: str,
        status: Literal["started", "retrying", "completed", "failed"],
        attempt: int,
        error_code: str | None = None,
    ) -> None:
        self.events.append(
            HarnessEvent(
                stage=stage,
                status=status,
                attempt=attempt,
                timestamp=datetime.now(timezone.utc).isoformat(),
                error_code=error_code,
            )
        )


def exit_code_for_error(code: ErrorCode) -> int:
    if code in {
        ErrorCode.INVALID_INPUT,
        ErrorCode.PRIVATE_NETWORK_BLOCKED,
        ErrorCode.CONTENT_TOO_LARGE,
    }:
        return 3
    if code in {
        ErrorCode.SOURCE_FETCH_FAILED,
        ErrorCode.PARSER_NOT_CONFIGURED,
        ErrorCode.PARSER_UNSUPPORTED,
        ErrorCode.PARSER_FAILED,
        ErrorCode.PARSER_CONTRACT_MISMATCH,
        ErrorCode.CONTENT_UNUSABLE,
    }:
        return 4
    if code in {ErrorCode.LLM_FAILED, ErrorCode.LLM_CONTRACT_MISMATCH}:
        return 5
    return 6
