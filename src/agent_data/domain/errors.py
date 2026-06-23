from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    PRIVATE_NETWORK_BLOCKED = "PRIVATE_NETWORK_BLOCKED"
    CONTENT_TOO_LARGE = "CONTENT_TOO_LARGE"
    SOURCE_FETCH_FAILED = "SOURCE_FETCH_FAILED"
    PARSER_NOT_CONFIGURED = "PARSER_NOT_CONFIGURED"
    PARSER_UNSUPPORTED = "PARSER_UNSUPPORTED"
    PARSER_FAILED = "PARSER_FAILED"
    PARSER_CONTRACT_MISMATCH = "PARSER_CONTRACT_MISMATCH"
    CONTENT_UNUSABLE = "CONTENT_UNUSABLE"
    LLM_FAILED = "LLM_FAILED"
    LLM_CONTRACT_MISMATCH = "LLM_CONTRACT_MISMATCH"
    EXPORT_FAILED = "EXPORT_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class PipelineError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        stage: str,
        retryable: bool = False,
        remediation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.retryable = retryable
        self.remediation = remediation
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "stage": self.stage,
            "retryable": self.retryable,
            "remediation": self.remediation,
            "details": self.details,
        }
