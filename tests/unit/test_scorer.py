from agent_data.domain.models import GateCheck, GateReport, QualityDimension, TaskScores
from agent_data.quality.scorer import QualityScorer


def dimension(score: float) -> QualityDimension:
    return QualityDimension(score=score, confidence=1, method="test")


def passed() -> GateReport:
    return GateReport(
        status="passed",
        checks=[GateCheck(name="schema", passed=True, code="SCHEMA_INVALID", message="ok")],
    )


def test_intrinsic_score_uses_documented_weights() -> None:
    dimensions = {
        "source_trust": dimension(1),
        "freshness": dimension(0.8),
        "completeness": dimension(0.7),
        "evidence_quality": dimension(0.9),
        "structure_quality": dimension(0.6),
    }
    result = QualityScorer().score(dimensions, passed(), TaskScores())
    assert result.intrinsic_score == 0.82
    assert result.quality_level == "B"


def test_quality_levels_and_gate_rejection_precedence() -> None:
    scorer = QualityScorer()
    for value, level in [(0.9, "A"), (0.75, "B"), (0.6, "C"), (0.4, "Rejected")]:
        dimensions = {name: dimension(value) for name in scorer.INTRINSIC_WEIGHTS}
        assert scorer.score(dimensions, passed(), TaskScores()).quality_level == level

    failed = GateReport(
        status="failed",
        checks=[GateCheck(name="schema", passed=False, code="SCHEMA_INVALID", message="bad")],
    )
    dimensions = {name: dimension(1) for name in scorer.INTRINSIC_WEIGHTS}
    assert scorer.score(dimensions, failed, TaskScores()).quality_level == "Rejected"


def test_task_score_remains_null_without_context() -> None:
    dimensions = {name: dimension(1) for name in QualityScorer.INTRINSIC_WEIGHTS}
    result = QualityScorer().score(dimensions, passed(), TaskScores())
    assert result.task_score is None
