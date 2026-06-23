from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent_data.domain.models import EvidenceLocation, QualityDimension, TaskScores


def test_quality_dimension_rejects_score_outside_unit_interval() -> None:
    with pytest.raises(ValidationError):
        QualityDimension(score=1.1, confidence=0.9, method="rules_v1")


def test_pdf_location_requires_consistent_human_and_zero_based_pages() -> None:
    location = EvidenceLocation(page=2, page_index=1, bbox=[1, 2, 3, 4])
    assert location.page == location.page_index + 1

    with pytest.raises(ValidationError):
        EvidenceLocation(page=2, page_index=0, bbox=[1, 2, 3, 4])


def test_task_scores_are_null_without_task_context() -> None:
    scores = TaskScores.for_context(None, relevance=None, actionability=None)
    assert scores.relevance is None
    assert scores.actionability is None
    assert scores.task_score is None


def test_models_accept_timezone_aware_timestamp() -> None:
    assert datetime.now(timezone.utc).tzinfo is not None
