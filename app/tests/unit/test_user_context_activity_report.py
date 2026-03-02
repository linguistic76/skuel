"""
Unit Tests — UserContextPopulator.populate_activity_report
===========================================================

Covers the branch conditions in populate_activity_report:
1. Empty records list → all fields remain None
2. Single valid record → all fields populated correctly
3. Record with uid=None → skipped (NULL filter guard), fields remain None
4. Record with user_annotation → annotation field populated
5. Record without user_annotation key → annotation field stays None
"""

from datetime import datetime

from core.services.user.user_context_populator import UserContextPopulator


# =============================================================================
# HELPERS
# =============================================================================


def make_context() -> object:
    """Minimal stand-in with the 5 activity report fields."""

    class _Context:
        pass

    ctx = _Context()
    ctx.latest_activity_report_uid = None
    ctx.latest_activity_report_period = None
    ctx.latest_activity_report_generated_at = None
    ctx.latest_activity_report_content = None
    ctx.latest_activity_report_user_annotation = None
    return ctx


# =============================================================================
# TESTS
# =============================================================================


def test_populate_activity_report_empty() -> None:
    """No records → all 4 fields remain None."""
    populator = UserContextPopulator()
    ctx = make_context()

    populator.populate_activity_report(ctx, [])  # type: ignore[arg-type]

    assert ctx.latest_activity_report_uid is None
    assert ctx.latest_activity_report_period is None
    assert ctx.latest_activity_report_generated_at is None
    assert ctx.latest_activity_report_content is None


def test_populate_activity_report_single() -> None:
    """One valid record → all 4 fields populated correctly."""
    populator = UserContextPopulator()
    ctx = make_context()
    period_end = datetime(2026, 3, 1, 12, 0, 0)

    records = [
        {
            "uid": "ku_report_abc123",
            "period": "7d",
            "period_end": period_end,
            "content": "You have been over-committing on tasks this week.",
        }
    ]

    populator.populate_activity_report(ctx, records)  # type: ignore[arg-type]

    assert ctx.latest_activity_report_uid == "ku_report_abc123"
    assert ctx.latest_activity_report_period == "7d"
    assert ctx.latest_activity_report_generated_at == period_end
    assert ctx.latest_activity_report_content == "You have been over-committing on tasks this week."


def test_populate_activity_report_uid_none_skips() -> None:
    """Record with uid=None is skipped; fields remain None."""
    populator = UserContextPopulator()
    ctx = make_context()

    records = [{"uid": None, "period": "14d", "period_end": None, "content": "Some content"}]

    populator.populate_activity_report(ctx, records)  # type: ignore[arg-type]

    assert ctx.latest_activity_report_uid is None
    assert ctx.latest_activity_report_period is None
    assert ctx.latest_activity_report_generated_at is None
    assert ctx.latest_activity_report_content is None


def test_populate_activity_report_with_annotation() -> None:
    """Record includes user_annotation → annotation field populated."""
    populator = UserContextPopulator()
    ctx = make_context()
    period_end = datetime(2026, 3, 1, 12, 0, 0)

    records = [
        {
            "uid": "ku_report_abc123",
            "period": "7d",
            "period_end": period_end,
            "content": "You have been over-committing on tasks this week.",
            "user_annotation": "I think I'm over-committing because of deadline pressure.",
        }
    ]

    populator.populate_activity_report(ctx, records)  # type: ignore[arg-type]

    assert ctx.latest_activity_report_uid == "ku_report_abc123"
    assert ctx.latest_activity_report_user_annotation == (
        "I think I'm over-committing because of deadline pressure."
    )


def test_populate_activity_report_annotation_none_key_missing() -> None:
    """Record has no user_annotation key → annotation field stays None."""
    populator = UserContextPopulator()
    ctx = make_context()
    period_end = datetime(2026, 3, 1, 12, 0, 0)

    records = [
        {
            "uid": "ku_report_abc123",
            "period": "7d",
            "period_end": period_end,
            "content": "Some content.",
            # user_annotation key intentionally absent
        }
    ]

    populator.populate_activity_report(ctx, records)  # type: ignore[arg-type]

    assert ctx.latest_activity_report_uid == "ku_report_abc123"
    assert ctx.latest_activity_report_user_annotation is None
