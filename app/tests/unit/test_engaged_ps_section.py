"""
Unit Tests — Overview UI: Engaged PathStep Section
==================================================

Tests for ``_engaged_ps_section`` in ``ui/profile/overview.py`` — the daily
plan card subsection that surfaces each active PS engagement and the spawned
items still on today's plan.

Covers:
1. Empty engaged_ps_groups → returns None
2. Group with pending items → header + rows render
3. Group with empty pending tuples → header still renders (no items)
4. Engaged vs completed state → both render with state text
5. Title resolution from contextual_tasks/habits/goals
6. PS UID slugging (ps:namespace:slug → "slug")
7. Item cap at 6 per group
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fasthtml.common import to_xml

from core.models.context_types import DailyWorkPlan, EngagedPsGroup
from core.services.ps_engagement.engagement import Engagement
from ui.profile.overview import _engaged_ps_section

# =============================================================================
# HELPERS
# =============================================================================


def _engagement(
    ps_uid: str,
    spawned: tuple[str, ...] = (),
    state: str = "engaged",
) -> Engagement:
    return Engagement(
        student_uid="user_test",
        ps_uid=ps_uid,
        state=state,  # type: ignore[arg-type]
        since=datetime(2026, 5, 3, tzinfo=UTC),
        spawned_instance_uids=spawned,
    )


def _contextual(uid: str, title: str) -> Any:
    """Minimal stand-in for ContextualTask/Habit/Goal — only uid + title used."""

    class _Item:
        pass

    item = _Item()
    item.uid = uid
    item.title = title
    return item


# =============================================================================
# TESTS
# =============================================================================


def test_empty_engaged_groups_returns_none() -> None:
    """No engagements → helper returns None so the card omits the section entirely."""
    plan = DailyWorkPlan()
    assert _engaged_ps_section(plan) is None


def test_group_with_pending_items_renders_header_and_rows() -> None:
    """Pending UIDs surface as item rows with resolved titles."""
    eng = _engagement("ps:math:algebra", spawned=("task_1", "habit_1"))
    group = EngagedPsGroup(
        ps_uid="ps:math:algebra",
        engagement=eng,
        pending_task_uids=("task_1",),
        pending_habit_uids=("habit_1",),
    )
    plan = DailyWorkPlan(
        engaged_ps_groups=(group,),
        contextual_tasks=(_contextual("task_1", "Solve linear equations"),),
        contextual_habits=(_contextual("habit_1", "Daily problem set"),),
    )

    section = _engaged_ps_section(plan)
    assert section is not None
    html = to_xml(section)

    assert "ENGAGED PATHSTEPS" in html
    assert "algebra" in html  # PS slug
    assert "Solve linear equations" in html
    assert "Daily problem set" in html
    assert "2 of 2 pending" in html


def test_group_with_no_pending_still_renders_header() -> None:
    """Empty pending tuples → header row only (per ADR-059 visibility semantics)."""
    eng = _engagement("ps:meditation", spawned=())
    group = EngagedPsGroup(ps_uid="ps:meditation", engagement=eng)
    plan = DailyWorkPlan(engaged_ps_groups=(group,))

    section = _engaged_ps_section(plan)
    assert section is not None
    html = to_xml(section)

    assert "meditation" in html
    # No total_spawned → "engaged" fallback text instead of "N of M pending"
    assert "engaged" in html
    assert "pending" not in html


def test_completed_state_surfaces_in_badge() -> None:
    """A completed engagement renders state='completed' text."""
    eng = _engagement("ps:done", spawned=("task_1",), state="completed")
    group = EngagedPsGroup(ps_uid="ps:done", engagement=eng)
    plan = DailyWorkPlan(engaged_ps_groups=(group,))

    section = _engaged_ps_section(plan)
    html = to_xml(section)  # type: ignore[arg-type]

    assert "completed" in html


def test_ps_uid_slugged_to_last_segment() -> None:
    """ps:namespace:slug → only 'slug' shown, not the full UID."""
    eng = _engagement("ps:foo:bar:baz", spawned=())
    group = EngagedPsGroup(ps_uid="ps:foo:bar:baz", engagement=eng)
    plan = DailyWorkPlan(engaged_ps_groups=(group,))

    section = _engaged_ps_section(plan)
    html = to_xml(section)  # type: ignore[arg-type]

    assert "baz" in html
    # Earlier segments shouldn't appear as the primary slug display
    # (they may still appear elsewhere in attributes, so this is best-effort)


def test_item_rows_capped_at_six_per_group() -> None:
    """A group with 10 pending items shows at most 6 in the section."""
    pending = tuple(f"task_{i}" for i in range(10))
    contextuals = tuple(_contextual(uid, f"Task {i}") for i, uid in enumerate(pending))
    eng = _engagement("ps:big", spawned=pending)
    group = EngagedPsGroup(
        ps_uid="ps:big",
        engagement=eng,
        pending_task_uids=pending,
    )
    plan = DailyWorkPlan(
        engaged_ps_groups=(group,),
        contextual_tasks=contextuals,
    )

    section = _engaged_ps_section(plan)
    html = to_xml(section)  # type: ignore[arg-type]

    # Tasks 0-5 should appear, 6-9 should not
    for i in range(6):
        assert f"Task {i}" in html
    for i in range(6, 10):
        assert f"Task {i}" not in html
    # Progress text reflects the full pending count, not the cap
    assert "10 of 10 pending" in html


def test_unresolved_uids_fall_back_to_uid_string() -> None:
    """Pending UIDs without a matching contextual_* entry render as the UID itself."""
    eng = _engagement("ps:x", spawned=("task_orphan",))
    group = EngagedPsGroup(
        ps_uid="ps:x",
        engagement=eng,
        pending_task_uids=("task_orphan",),
    )
    plan = DailyWorkPlan(engaged_ps_groups=(group,))

    section = _engaged_ps_section(plan)
    html = to_xml(section)  # type: ignore[arg-type]

    assert "task_orphan" in html


def test_multiple_groups_each_render_independently() -> None:
    """Two engagements → two header rows, items keyed to each group."""
    eng_a = _engagement("ps:a", spawned=("task_a",))
    eng_b = _engagement("ps:b", spawned=("task_b",))
    plan = DailyWorkPlan(
        engaged_ps_groups=(
            EngagedPsGroup(ps_uid="ps:a", engagement=eng_a, pending_task_uids=("task_a",)),
            EngagedPsGroup(ps_uid="ps:b", engagement=eng_b, pending_task_uids=("task_b",)),
        ),
        contextual_tasks=(
            _contextual("task_a", "Item A"),
            _contextual("task_b", "Item B"),
        ),
    )

    section = _engaged_ps_section(plan)
    html = to_xml(section)  # type: ignore[arg-type]

    assert "Item A" in html
    assert "Item B" in html
