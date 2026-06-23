from __future__ import annotations

from agent_data.domain.models import (
    GateReport,
    QualityDimension,
    QualityResult,
    TaskScores,
)


class QualityScorer:
    INTRINSIC_WEIGHTS = {
        "source_trust": 0.20,
        "freshness": 0.15,
        "completeness": 0.20,
        "evidence_quality": 0.30,
        "structure_quality": 0.15,
    }

    def score(
        self,
        dimensions: dict[str, QualityDimension],
        gates: GateReport,
        task_scores: TaskScores,
    ) -> QualityResult:
        missing = set(self.INTRINSIC_WEIGHTS) - set(dimensions)
        if missing:
            raise ValueError(f"Missing quality dimensions: {sorted(missing)}")
        intrinsic = round(
            sum(dimensions[name].score * weight for name, weight in self.INTRINSIC_WEIGHTS.items()),
            6,
        )
        if gates.status == "failed" or intrinsic < 0.55:
            level = "Rejected"
        elif intrinsic >= 0.85:
            level = "A"
        elif intrinsic >= 0.70:
            level = "B"
        else:
            level = "C"
        return QualityResult(
            gate_status=gates.status,
            quality_level=level,
            intrinsic_score=intrinsic,
            task_score=task_scores.task_score,
            dimensions=dimensions,
            checks=gates.checks,
        )
