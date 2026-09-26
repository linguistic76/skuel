"""The derived "reviewed" badges (Submit & Share arc R2) — one renderer for the three surfaces."""

from __future__ import annotations

from fasthtml.common import Div, to_xml

from core.models.enums.pipeline import ReportSource
from ui.gradebook.review_badges import (
    REVIEWED_LABEL,
    REVISED_AFTER_FEEDBACK_LABEL,
    review_badges,
    reviewed_label,
)


def test_reviewed_label_names_the_source_from_the_enum() -> None:
    assert reviewed_label(ReportSource.HUMAN.value) == "Reviewed · Teacher"
    assert reviewed_label(ReportSource.LLM.value) == "Reviewed · AI"
    # a source this build does not know, and none at all, read as plain "Reviewed"
    assert reviewed_label("peer") == REVIEWED_LABEL
    assert reviewed_label(None) == REVIEWED_LABEL


def test_badges_follow_the_standing() -> None:
    assert review_badges(None) == []
    assert review_badges({"reviewed_by": None, "revised_after_feedback": False}) == []
    both = to_xml(Div(*review_badges({"reviewed_by": "human", "revised_after_feedback": True})))
    assert REVISED_AFTER_FEEDBACK_LABEL in both and "Reviewed · Teacher" in both
    revised_only = to_xml(
        Div(*review_badges({"reviewed_by": None, "revised_after_feedback": True}))
    )
    assert REVISED_AFTER_FEEDBACK_LABEL in revised_only and REVIEWED_LABEL not in revised_only
