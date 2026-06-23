import hashlib
from datetime import datetime, timezone

import pytest

from agent_data.domain.models import (
    ContentBlock,
    Evidence,
    EvidenceLocation,
    GateContext,
    QualityIssue,
    VerifiedClaim,
)
from agent_data.quality.gates import QualityGateRunner


def hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def valid_context() -> GateContext:
    content = "x" * 220
    evidence = Evidence(
        id="e1",
        block_id="b1",
        quote="x" * 20,
        location=EvidenceLocation(page=1, page_index=0, bbox=[1, 2, 3, 4]),
        content_hash="sha256:raw",
    )
    return GateContext(
        schema_valid=True,
        source_locator="https://example.com",
        collected_at=datetime.now(timezone.utc),
        raw_content_ref="raw/document.html",
        raw_hash="sha256:raw",
        clean_content=content,
        clean_hash=hash_text(content),
        content_blocks=[
            ContentBlock(block_id="b1", type="text", text=content, order=0, page=1, page_index=0)
        ],
        claims=[
            VerifiedClaim(
                text="A fact",
                claim_type="fact",
                confidence=0.9,
                verification_status="verified",
                evidence=evidence,
            )
        ],
        access_rights="public",
    )


def test_all_hard_gates_pass_for_valid_context() -> None:
    report = QualityGateRunner().run(valid_context())
    assert report.status == "passed"
    assert len(report.checks) == 10
    assert all(check.passed for check in report.checks)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ({"schema_valid": False}, "SCHEMA_INVALID"),
        ({"source_locator": ""}, "SOURCE_UNTRACEABLE"),
        ({"raw_content_ref": ""}, "RAW_CONTENT_MISSING"),
        ({"clean_content": "short"}, "CONTENT_UNUSABLE"),
        ({"clean_hash": "sha256:wrong"}, "HASH_MISMATCH"),
        (
            {
                "claims": [
                    VerifiedClaim(
                        text="A fact",
                        claim_type="fact",
                        confidence=0.9,
                        verification_status="rejected",
                    )
                ]
            },
            "CLAIM_UNGROUNDED",
        ),
        ({"content_blocks": []}, "EVIDENCE_UNLOCATABLE"),
        (
            {
                "issues": [
                    QualityIssue(
                        code="BROKEN",
                        severity="critical",
                        confidence=1,
                        message="broken",
                    )
                ]
            },
            "CRITICAL_QUALITY_ISSUE",
        ),
        ({"access_rights": "restricted"}, "RIGHTS_RESTRICTED"),
    ],
)
def test_each_hard_gate_has_stable_failure_code(mutation: dict, code: str) -> None:
    context = valid_context().model_copy(update=mutation)
    report = QualityGateRunner().run(context)
    assert report.status == "failed"
    assert code in report.failed_codes


def test_evidence_fidelity_gate_rejects_empty_quote() -> None:
    context = valid_context()
    evidence = context.claims[0].evidence.model_copy(update={"quote": ""})  # type: ignore[union-attr]
    claim = context.claims[0].model_copy(update={"evidence": evidence})
    report = QualityGateRunner().run(context.model_copy(update={"claims": [claim]}))
    assert "EVIDENCE_MISMATCH" in report.failed_codes


def test_missing_content_blocks_fails_location_gate_even_without_claims() -> None:
    context = valid_context().model_copy(update={"content_blocks": [], "claims": []})
    report = QualityGateRunner().run(context)
    assert "EVIDENCE_UNLOCATABLE" in report.failed_codes


def test_pdf_evidence_without_bbox_fails_location_gate() -> None:
    context = valid_context()
    evidence = context.claims[0].evidence.model_copy(  # type: ignore[union-attr]
        update={"location": EvidenceLocation(page=1, page_index=0)}
    )
    claim = context.claims[0].model_copy(update={"evidence": evidence})
    report = QualityGateRunner().run(context.model_copy(update={"claims": [claim]}))
    assert "EVIDENCE_UNLOCATABLE" in report.failed_codes
