"""
Unit Tests — Life Path Intelligence: PS-Engagement Alignment Bonus
==================================================================

Tests for ``LifePathIntelligenceMixin._engagement_alignment_bonus``, the
multiplier that boosts activity_score and goal_score in life-path alignment
when active tasks/habits/goals come from PS engagements.

Rationale: spawned-from-engagement items are *taught* movement on the life
path — the user explicitly engaged with curriculum that prescribed them — so
they earn extra credit beyond native learning-goal linkage.

Multiplier scales linearly: 1.0 (no spawned items active) → 1.20 (all active
items spawned). Abandoned engagements have their spawned items deleted per
ADR-059, so those UIDs naturally don't appear in active_* sets.

Covers:
1. Empty reverse index → 1.0 (no PS-engagement signal)
2. Zero active activities → 1.0 (degenerate denominator guarded)
3. 100% spawned share → 1.20 (max bonus)
4. 50% spawned share → 1.10
5. Index has entries but no active activity matches → 1.0
6. Mixed task/habit/goal spawned items → bonus reflects all three pools
"""

from unittest.mock import MagicMock

import pytest

from core.services.user.intelligence.life_path_intelligence import LifePathIntelligenceMixin

# =============================================================================
# HELPERS
# =============================================================================


class _Mixin(LifePathIntelligenceMixin):
    """Concrete instantiation for direct method calls on the mixin."""


def _make_mixin(
    *,
    spawned_uid_to_ps_uid: dict[str, str] | None = None,
    active_task_uids: list[str] | None = None,
    active_habit_uids: list[str] | None = None,
    active_goal_uids: list[str] | None = None,
) -> _Mixin:
    ctx = MagicMock()
    ctx.spawned_uid_to_ps_uid = spawned_uid_to_ps_uid or {}
    ctx.active_task_uids = active_task_uids or []
    ctx.active_habit_uids = active_habit_uids or []
    ctx.active_goal_uids = active_goal_uids or []
    mixin = _Mixin()
    mixin.context = ctx
    return mixin


# =============================================================================
# TESTS
# =============================================================================


def test_empty_index_returns_unit_multiplier() -> None:
    """No spawned-from-PS entries → no bonus."""
    mixin = _make_mixin(spawned_uid_to_ps_uid={})
    assert mixin._engagement_alignment_bonus() == 1.0


def test_zero_active_activities_returns_unit_multiplier() -> None:
    """No active tasks/habits/goals → bonus is undefined, returns 1.0 not div-by-zero."""
    mixin = _make_mixin(
        spawned_uid_to_ps_uid={"task_1": "ps:foo"},
        active_task_uids=[],
        active_habit_uids=[],
        active_goal_uids=[],
    )
    assert mixin._engagement_alignment_bonus() == 1.0


def test_full_spawned_share_caps_at_max_bonus() -> None:
    """All 3 active items are spawned → 1.0 + (1.0 * 0.20) = 1.20."""
    mixin = _make_mixin(
        spawned_uid_to_ps_uid={
            "task_1": "ps:a",
            "habit_1": "ps:a",
            "goal_1": "ps:a",
        },
        active_task_uids=["task_1"],
        active_habit_uids=["habit_1"],
        active_goal_uids=["goal_1"],
    )
    assert mixin._engagement_alignment_bonus() == pytest.approx(1.20)


def test_half_spawned_share_yields_midpoint_bonus() -> None:
    """2 of 4 active items spawned → share 0.5 → 1.0 + (0.5 * 0.20) = 1.10."""
    mixin = _make_mixin(
        spawned_uid_to_ps_uid={"task_1": "ps:a", "habit_1": "ps:a"},
        active_task_uids=["task_1", "task_native"],
        active_habit_uids=["habit_1", "habit_native"],
    )
    assert mixin._engagement_alignment_bonus() == pytest.approx(1.10)


def test_index_populated_but_no_match_returns_unit() -> None:
    """Engagement spawned items that aren't currently active → no bonus.

    This is the case where a user engaged once, the spawned items were all
    completed (and so dropped from active_* sets) but the index still carries
    their UIDs. The bonus is zero because the items aren't influencing today's
    activity pool.
    """
    mixin = _make_mixin(
        spawned_uid_to_ps_uid={"task_done": "ps:past", "goal_done": "ps:past"},
        active_task_uids=["task_native_1", "task_native_2"],
        active_goal_uids=["goal_native"],
    )
    assert mixin._engagement_alignment_bonus() == 1.0


def test_mixed_domain_spawned_pool_counted_uniformly() -> None:
    """Bonus pools active tasks + habits + goals → 1 spawn out of 4 → 1.05."""
    mixin = _make_mixin(
        spawned_uid_to_ps_uid={"task_1": "ps:a"},
        active_task_uids=["task_1", "task_native"],
        active_habit_uids=["habit_native"],
        active_goal_uids=["goal_native"],
    )
    # 1/4 spawn share × 0.20 = 0.05 bonus
    assert mixin._engagement_alignment_bonus() == pytest.approx(1.05)
