import pytest

from agent_data.application.harness import Harness, exit_code_for_error
from agent_data.domain.errors import ErrorCode, PipelineError


def test_harness_retries_only_retryable_failures() -> None:
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PipelineError(ErrorCode.LLM_FAILED, "temporary", stage="extract", retryable=True)
        return "ok"

    harness = Harness()
    assert harness.execute("extract", operation, retries=2) == "ok"
    assert attempts == 3
    assert [event.status for event in harness.events] == [
        "started",
        "retrying",
        "retrying",
        "completed",
    ]


def test_harness_does_not_retry_permanent_failure() -> None:
    harness = Harness()
    with pytest.raises(PipelineError):
        harness.execute(
            "parse",
            lambda: (_ for _ in ()).throw(
                PipelineError(ErrorCode.PARSER_CONTRACT_MISMATCH, "bad", stage="parse")
            ),
            retries=2,
        )
    assert [event.status for event in harness.events] == ["started", "failed"]


@pytest.mark.parametrize(
    ("code", "exit_code"),
    [
        (ErrorCode.INVALID_INPUT, 3),
        (ErrorCode.PARSER_FAILED, 4),
        (ErrorCode.PARSER_CONTRACT_MISMATCH, 4),
        (ErrorCode.LLM_FAILED, 5),
        (ErrorCode.EXPORT_FAILED, 6),
        (ErrorCode.INTERNAL_ERROR, 6),
    ],
)
def test_error_codes_map_to_cli_exit_codes(code: ErrorCode, exit_code: int) -> None:
    assert exit_code_for_error(code) == exit_code
