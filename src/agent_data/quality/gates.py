from __future__ import annotations

import hashlib

from agent_data.domain.models import GateCheck, GateContext, GateReport


class QualityGateRunner:
    def __init__(self, *, min_content_chars: int = 200) -> None:
        self.min_content_chars = min_content_chars

    def run(self, context: GateContext) -> GateReport:
        block_ids = {block.block_id for block in context.content_blocks}
        facts = [claim for claim in context.claims if claim.claim_type == "fact"]
        located = bool(context.content_blocks) and all(
            (
                claim.evidence is not None
                and claim.evidence.block_id in block_ids
                and (
                    (
                        claim.evidence.location.page is not None
                        and claim.evidence.location.bbox is not None
                    )
                    or (
                        claim.evidence.location.start_offset is not None
                        and claim.evidence.location.end_offset is not None
                    )
                )
            )
            for claim in facts
        )
        fidelity = all(
            claim.evidence is not None
            and bool(claim.evidence.quote.strip())
            and claim.verification_status == "verified"
            for claim in facts
        )
        clean_hash = "sha256:" + hashlib.sha256(context.clean_content.encode()).hexdigest()
        checks = [
            self._check("schema", context.schema_valid, "SCHEMA_INVALID", "Schema is valid"),
            self._check(
                "provenance",
                bool(context.source_locator and context.collected_at),
                "SOURCE_UNTRACEABLE",
                "Source and collection time are available",
            ),
            self._check(
                "raw_retention",
                bool(context.raw_content_ref and context.raw_hash),
                "RAW_CONTENT_MISSING",
                "Raw content reference and hash are available",
            ),
            self._check(
                "parse",
                len(context.clean_content.strip()) >= self.min_content_chars,
                "CONTENT_UNUSABLE",
                "Clean content meets minimum usable length",
            ),
            self._check(
                "integrity",
                context.clean_hash == clean_hash,
                "HASH_MISMATCH",
                "Clean content hash matches",
            ),
            self._check(
                "claim_grounding",
                all(
                    claim.verification_status == "verified" and claim.evidence is not None
                    for claim in facts
                ),
                "CLAIM_UNGROUNDED",
                "All fact claims are grounded",
            ),
            self._check(
                "evidence_location",
                located,
                "EVIDENCE_UNLOCATABLE",
                "All evidence locations resolve to content blocks",
            ),
            self._check(
                "evidence_fidelity",
                fidelity,
                "EVIDENCE_MISMATCH",
                "All evidence quotes are verified",
            ),
            self._check(
                "critical_issues",
                not any(issue.severity == "critical" for issue in context.issues),
                "CRITICAL_QUALITY_ISSUE",
                "No unresolved critical issue exists",
            ),
            self._check(
                "rights",
                context.access_rights != "restricted",
                "RIGHTS_RESTRICTED",
                "No explicit access restriction blocks use",
            ),
        ]
        return GateReport(
            status="passed" if all(check.passed for check in checks) else "failed",
            checks=checks,
        )

    @staticmethod
    def _check(name: str, passed: bool, code: str, success_message: str) -> GateCheck:
        return GateCheck(
            name=name,
            passed=passed,
            code=code,
            message=success_message if passed else f"Failed: {success_message}",
        )
