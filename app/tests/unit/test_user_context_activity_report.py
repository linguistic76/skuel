"""
Unit Tests — UserContextPopulator.populate_activity_report
                + UserContextPopulator.populate_cross_domain_insights
===========================================================

populate_activity_report (5 tests):
1. None → all fields remain None
2. Single valid dict → all fields populated correctly
3. Dict with uid=None → skipped (NULL filter guard), fields remain None
4. Dict with user_annotation → annotation field populated
5. Dict without user_annotation key → annotation field stays None

populate_cross_domain_insights (2 tests):
6. None → {"active_count": 0, "top_insights": []}
7. Unsorted insights → top_insights sorted by confidence descending
"""

from datetime import datetime

from core.services.user.unified_user_context import UserContext
from core.services.user.user_context_populator import UserContextPopulator

# =============================================================================
# HELPERS
# =============================================================================


def make_context() -> object:
    """Minimal stand-in with the activity report and insights fields."""

    class _Context:
        pass

    ctx = _Context()
    ctx.latest_activity_report_uid = None
    ctx.latest_activity_report_period = None
    ctx.latest_activity_report_generated_at = None
    ctx.latest_activity_report_content = None
    ctx.latest_activity_report_user_annotation = None
    ctx.cross_domain_insights = None
    return ctx


# =============================================================================
# populate_activity_report TESTS
# =============================================================================


def test_populate_activity_report_empty() -> None:
    """None → all 4 fields remain None."""
    populator = UserContextPopulator()
    ctx = make_context()

    populator.populate_activity_report(ctx, None)

    assert ctx.latest_activity_report_uid is None
    assert ctx.latest_activity_report_period is None
    assert ctx.latest_activity_report_generated_at is None
    assert ctx.latest_activity_report_content is None


def test_populate_activity_report_single() -> None:
    """One valid dict → all 4 fields populated correctly."""
    populator = UserContextPopulator()
    ctx = make_context()
    period_end = datetime(2026, 3, 1, 12, 0, 0)

    record = {
        "uid": "ku_report_abc123",
        "period": "7d",
        "period_end": period_end,
        "content": "You have been over-committing on tasks this week.",
    }

    populator.populate_activity_report(ctx, record)

    assert ctx.latest_activity_report_uid == "ku_report_abc123"
    assert ctx.latest_activity_report_period == "7d"
    assert ctx.latest_activity_report_generated_at == period_end
    assert ctx.latest_activity_report_content == "You have been over-committing on tasks this week."


def test_populate_activity_report_uid_none_skips() -> None:
    """Dict with uid=None is skipped; fields remain None."""
    populator = UserContextPopulator()
    ctx = make_context()

    record = {"uid": None, "period": "14d", "period_end": None, "content": "Some content"}

    populator.populate_activity_report(ctx, record)

    assert ctx.latest_activity_report_uid is None
    assert ctx.latest_activity_report_period is None
    assert ctx.latest_activity_report_generated_at is None
    assert ctx.latest_activity_report_content is None


def test_populate_activity_report_with_annotation() -> None:
    """Dict includes user_annotation → annotation field populated."""
    populator = UserContextPopulator()
    ctx = make_context()
    period_end = datetime(2026, 3, 1, 12, 0, 0)

    record = {
        "uid": "ku_report_abc123",
        "period": "7d",
        "period_end": period_end,
        "content": "You have been over-committing on tasks this week.",
        "user_annotation": "I think I'm over-committing because of deadline pressure.",
    }

    populator.populate_activity_report(ctx, record)

    assert ctx.latest_activity_report_uid == "ku_report_abc123"
    assert ctx.latest_activity_report_user_annotation == (
        "I think I'm over-committing because of deadline pressure."
    )


def test_populate_activity_report_annotation_none_key_missing() -> None:
    """Dict has no user_annotation key → annotation field stays None."""
    populator = UserContextPopulator()
    ctx = make_context()
    period_end = datetime(2026, 3, 1, 12, 0, 0)

    record = {
        "uid": "ku_report_abc123",
        "period": "7d",
        "period_end": period_end,
        "content": "Some content.",
        # user_annotation key intentionally absent
    }

    populator.populate_activity_report(ctx, record)

    assert ctx.latest_activity_report_uid == "ku_report_abc123"
    assert ctx.latest_activity_report_user_annotation is None


# =============================================================================
# populate_from_consolidated_data — activity_report wiring
# =============================================================================


def test_populate_from_consolidated_data_wires_activity_report() -> None:
    """activity_report key in consolidated data reaches UserContext fields."""
    populator = UserContextPopulator()
    ctx = UserContext(user_uid="user_test")

    data = {
        "tasks": {},
        "habits": {},
        "goals": {},
        "knowledge": {},
        "events": {},
        "mocs": {},
        "activity_report": {
            "uid": "ku_report_wired_test",
            "period": "7d",
            "period_end": None,
            "content": "Wired through consolidated path.",
        },
    }

    populator.populate_from_consolidated_data(ctx, data)

    assert ctx.latest_activity_report_uid == "ku_report_wired_test"
    assert ctx.latest_activity_report_period == "7d"
    assert ctx.latest_activity_report_content == "Wired through consolidated path."


def test_populate_from_consolidated_data_no_activity_report() -> None:
    """Missing activity_report key leaves UserContext fields as None."""
    populator = UserContextPopulator()
    ctx = UserContext(user_uid="user_test")

    data = {"tasks": {}, "habits": {}, "goals": {}, "knowledge": {}, "events": {}, "mocs": {}}

    populator.populate_from_consolidated_data(ctx, data)

    assert ctx.latest_activity_report_uid is None
    assert ctx.latest_activity_report_content is None


# =============================================================================
# populate_cross_domain_insights TESTS
# =============================================================================


def test_populate_cross_domain_insights_none() -> None:
    """None → cross_domain_insights = {"active_count": 0, "top_insights": []}."""
    populator = UserContextPopulator()
    ctx = make_context()

    populator.populate_cross_domain_insights(ctx, None)

    assert ctx.cross_domain_insights == {"active_count": 0, "top_insights": []}


def test_populate_cross_domain_insights_sorted() -> None:
    """3 insights unsorted by confidence → top_insights sorted descending."""
    populator = UserContextPopulator()
    ctx = make_context()

    insights = [
        {
            "uid": "ins_a",
            "type": "habit_gap",
            "title": "Low streak",
            "impact": "medium",
            "confidence": 0.6,
        },
        {
            "uid": "ins_b",
            "type": "goal_risk",
            "title": "Goal at risk",
            "impact": "high",
            "confidence": 0.9,
        },
        {
            "uid": "ins_c",
            "type": "knowledge_gap",
            "title": "Gap found",
            "impact": "low",
            "confidence": 0.3,
        },
    ]

    populator.populate_cross_domain_insights(ctx, insights)

    assert ctx.cross_domain_insights["active_count"] == 3
    top = ctx.cross_domain_insights["top_insights"]
    assert len(top) == 3
    assert top[0]["uid"] == "ins_b"  # confidence 0.9
    assert top[1]["uid"] == "ins_a"  # confidence 0.6
    assert top[2]["uid"] == "ins_c"  # confidence 0.3
