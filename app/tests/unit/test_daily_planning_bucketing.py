"""
Unit Tests — Daily Planning: PS Engagement Bucketing (ADR-059)
==============================================================

Tests for ``_build_engaged_groups`` and ``_compute_available_to_start`` in
DailyPlanningMixin. These pure module-level helpers fold PS engagement state
into the assembled ``DailyWorkPlan``:

- ``_build_engaged_groups`` intersects each engagement's
  ``spawned_instance_uids`` with the plan's per-domain UID lists to produce
  one ``EngagedPsGroup`` per active engagement.
- ``_compute_available_to_start`` reports PS UIDs the user has touched
  (``RichUserContext.active_path_steps_rich``) but is not currently
  engaged with.

The bucketing logic was lifted from the orphaned
``AskesisService.get_daily_work_plan`` (which had zero callsites) into
``DailyPlanningMixin`` where it actually runs.

Covers:
1. Engaged PS with spawned UIDs → group with intersection-filtered pending lists
2. No engagements → empty groups tuple
3. Engagement with empty spawned tuple → group still surfaces (engagement visible)
4. available_to_start excludes currently engaged PSes
5. available_to_start dedupes and preserves touched ordering
6. Flat plan UID lists are unchanged (bucketing is additive)
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from core.models.context_types import DailyWorkPlan
from core.services.ps_engagement.engagement import Engagement
from core.services.user.intelligence.daily_planning import (
    _build_engaged_groups,
    _compute_available_to_start,
)

# =============================================================================
# HELPERS
# =============================================================================


def _engagement(
    ps_uid: str,
    spawned: tuple[str, ...] = (),
    state: str = "engaged",
) -> Engagement:
    return Engagement(
        student_uid="user_1",
        ps_uid=ps_uid,
        state=state,  # type: ignore[arg-type]
        since=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
        spawned_instance_uids=spawned,
    )


def _ctx_with_touched(ps_uids: tuple[str, ...]) -> MagicMock:
    """Mock RichUserContext exposing the active_path_steps_rich items used by
    _compute_available_to_start. Only the shape matters here, not the full
    UserContext surface."""
    ctx = MagicMock()
    ctx.active_path_steps_rich = [{"step": {"uid": uid}, "graph_context": {}} for uid in ps_uids]
    return ctx


# =============================================================================
# _build_engaged_groups
# =============================================================================


def test_engaged_ps_groups_intersects_spawned_with_plan() -> None:
    """An engaged PS with spawned UIDs surfaces only the UIDs still in today's plan."""
    plan = DailyWorkPlan(
        tasks=("task_a", "task_b", "task_orphan"),
        habits=("habit_a",),
        events=(),
    )
    eng = _engagement("ps:algebra", spawned=("task_a", "habit_a", "task_completed_yesterday"))

    groups = _build_engaged_groups(plan, [eng])

    assert len(groups) == 1
    group = groups[0]
    assert group.ps_uid == "ps:algebra"
    assert group.engagement is eng
    # Intersection only — task_orphan stays in flat plan; absent here.
    assert group.pending_task_uids == ("task_a",)
    assert group.pending_habit_uids == ("habit_a",)
    # Bucketing is additive — the flat plan is untouched by these helpers.
    assert plan.tasks == ("task_a", "task_b", "task_orphan")


def test_engaged_ps_groups_empty_when_no_engagements() -> None:
    """No active engagements → empty groups tuple, no allocation."""
    plan = DailyWorkPlan(tasks=("task_a",))
    assert _build_engaged_groups(plan, []) == ()


def test_engaged_ps_groups_surfaces_engagement_with_no_spawned_uids() -> None:
    """An engagement with empty spawned tuple still surfaces — consumers may
    want to render "you're engaged with X" even when nothing spawned today."""
    plan = DailyWorkPlan(tasks=("task_a",))
    eng = _engagement("ps:meditation", spawned=())

    groups = _build_engaged_groups(plan, [eng])

    assert len(groups) == 1
    assert groups[0].ps_uid == "ps:meditation"
    assert groups[0].engagement is eng
    assert groups[0].pending_task_uids == ()


# =============================================================================
# _compute_available_to_start
# =============================================================================


def test_available_to_start_excludes_currently_engaged() -> None:
    """Active engagements filter their PS UIDs out of available_to_start."""
    ctx = _ctx_with_touched(("ps:current", "ps:abandoned", "ps:never_started"))
    active = _engagement("ps:current", spawned=())

    available = _compute_available_to_start(ctx, [active])

    # ps:current is engaged → excluded.
    # ps:abandoned, ps:never_started are touched but not engaged → included.
    assert available == ("ps:abandoned", "ps:never_started")


def test_available_to_start_dedupes_and_preserves_touched_order() -> None:
    """Duplicate touched entries collapse to first occurrence; order preserved."""
    ctx = _ctx_with_touched(("ps:a", "ps:b", "ps:a", "ps:c"))

    available = _compute_available_to_start(ctx, [])

    assert available == ("ps:a", "ps:b", "ps:c")


def test_available_to_start_empty_when_no_touched_paths() -> None:
    """No active_path_steps_rich entries → empty tuple."""
    ctx = _ctx_with_touched(())
    assert _compute_available_to_start(ctx, []) == ()
