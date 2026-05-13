"""
Unit Tests — Synergy Intelligence: Engagement Completion Synergy
================================================================

Tests for ``SynergyIntelligenceMixin._detect_engagement_synergies``, the 6th
synergy type added when PS-engagement awareness was wired into intelligence.

Each active PS engagement is scored by completion ratio over its
*terminal-eligible* spawned items (Tasks/Goals/Choices, which have completed/
resolved sets). Habits/Events/Principles spawned by the engagement are
perpetual commitments — engagements that spawned only those get a flat 0.35
"ongoing" synergy.

Covers:
1. No active engagements (None) → empty list, no crash
2. No active engagements (empty dict) → empty list
3. Abandoned engagement → skipped (filtered out)
4. Completed engagement → score 1.0, "loop closed" rationale
5. Engaged with all-completable spawns, all completed → high score, ratio 100%
6. Engaged with all-completable spawns, none completed → low score, "Stalled" reco
7. Engaged with only ongoing spawns (no terminal-eligible) → flat 0.35
8. Engaged with empty spawned tuple → skipped
9. Engaged with partial completion → mid score, "{n} pending" reco
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from core.services.ps_engagement.engagement import Engagement
from core.services.user.intelligence.synergy_intelligence import SynergyIntelligenceMixin

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


class _Mixin(SynergyIntelligenceMixin):
    """Concrete instantiation for direct method calls on the mixin."""


def _make_mixin(
    *,
    engagements: dict[str, Engagement] | None,
    completed_task_uids: set[str] | None = None,
    completed_goal_uids: set[str] | None = None,
    resolved_choice_uids: set[str] | None = None,
    active_task_uids: list[str] | None = None,
    active_goal_uids: list[str] | None = None,
    pending_choice_uids: list[str] | None = None,
) -> _Mixin:
    ctx = MagicMock()
    ctx.active_ps_engagements = engagements
    ctx.completed_task_uids = completed_task_uids or set()
    ctx.completed_goal_uids = completed_goal_uids or set()
    ctx.resolved_choice_uids = resolved_choice_uids or set()
    ctx.active_task_uids = active_task_uids or []
    ctx.active_goal_uids = active_goal_uids or []
    ctx.pending_choice_uids = pending_choice_uids or []
    mixin = _Mixin()
    mixin.context = ctx
    return mixin


# =============================================================================
# TESTS
# =============================================================================


def test_no_engagements_field_none_returns_empty() -> None:
    """active_ps_engagements=None (standard build path) → no synergies."""
    mixin = _make_mixin(engagements=None)
    assert mixin._detect_engagement_synergies() == []


def test_no_engagements_empty_dict_returns_empty() -> None:
    """active_ps_engagements={} (rich build, no active PSes) → no synergies."""
    mixin = _make_mixin(engagements={})
    assert mixin._detect_engagement_synergies() == []


def test_abandoned_engagement_is_skipped() -> None:
    """Abandoned engagements emit no synergy — their spawned items are gone."""
    eng = _engagement("ps:dropped", spawned=("task_1", "task_2"), state="abandoned")
    mixin = _make_mixin(engagements={"ps:dropped": eng})
    assert mixin._detect_engagement_synergies() == []


def test_completed_engagement_scores_max() -> None:
    """A completed engagement closes the loop — synergy_score is 1.0."""
    eng = _engagement(
        "ps:algebra",
        spawned=("task_1", "task_2", "habit_1"),
        state="completed",
    )
    mixin = _make_mixin(engagements={"ps:algebra": eng})

    synergies = mixin._detect_engagement_synergies()

    assert len(synergies) == 1
    s = synergies[0]
    assert s.source_uid == "ps:algebra"
    assert s.source_domain == "pathstep"
    assert s.target_domain == "multi"
    assert s.synergy_type == "spawns"
    assert s.synergy_score == 1.0
    assert "closed" in s.rationale.lower()
    assert s.recommendations == ("Loop closed — knowledge consolidated",)


def test_engagement_with_empty_spawned_tuple_skipped() -> None:
    """An engagement that spawned nothing is not scored — no signal to surface."""
    eng = _engagement("ps:noop", spawned=())
    mixin = _make_mixin(engagements={"ps:noop": eng})
    assert mixin._detect_engagement_synergies() == []


def test_ongoing_only_engagement_gets_flat_score() -> None:
    """Engagement spawning only habits/events/principles (no terminal sets) → 0.35."""
    eng = _engagement(
        "ps:meditation",
        spawned=("habit_1", "habit_2", "principle_1"),
    )
    # No terminal-set membership — none of these UIDs are in
    # completed_task_uids / active_task_uids / completed_goal_uids / etc.
    mixin = _make_mixin(engagements={"ps:meditation": eng})

    synergies = mixin._detect_engagement_synergies()

    assert len(synergies) == 1
    s = synergies[0]
    assert s.synergy_score == 0.35
    assert "ongoing commitments" in s.rationale
    assert s.recommendations == (
        "Maintain habits/events spawned by this engagement",
    )


def test_engaged_all_completable_all_completed_scores_high() -> None:
    """All terminal-eligible spawns are completed → ratio 1.0 → 0.9 (engaged cap)."""
    eng = _engagement("ps:python", spawned=("task_1", "task_2", "goal_1"))
    mixin = _make_mixin(
        engagements={"ps:python": eng},
        completed_task_uids={"task_1", "task_2"},
        completed_goal_uids={"goal_1"},
    )

    synergies = mixin._detect_engagement_synergies()

    assert len(synergies) == 1
    s = synergies[0]
    # 0.3 + (1.0 * 0.6) = 0.9 (float arithmetic — use approx)
    assert s.synergy_score == pytest.approx(0.9)
    assert "3/3" in s.rationale
    assert "100%" in s.rationale
    assert "Closing the loop" in s.recommendations[0]


def test_engaged_stalled_emits_stalled_recommendation() -> None:
    """Low completion ratio + 3+ pending items → 'Stalled' recommendation."""
    eng = _engagement(
        "ps:procrastinated",
        spawned=("task_1", "task_2", "task_3", "task_4"),
    )
    mixin = _make_mixin(
        engagements={"ps:procrastinated": eng},
        # None completed; all four still active = pending
        active_task_uids=["task_1", "task_2", "task_3", "task_4"],
    )

    synergies = mixin._detect_engagement_synergies()

    assert len(synergies) == 1
    s = synergies[0]
    # ratio 0/4 = 0.0 → score 0.3 + (0 * 0.6) = 0.3
    assert s.synergy_score == pytest.approx(0.3)
    assert "0/4" in s.rationale
    assert any("Stalled" in r for r in s.recommendations)


def test_engaged_partial_completion_emits_pending_count() -> None:
    """Mid-ratio engagement (not stalled, not closing) → '{n} items still pending' reco."""
    eng = _engagement("ps:half", spawned=("task_1", "task_2", "task_3", "task_4"))
    mixin = _make_mixin(
        engagements={"ps:half": eng},
        completed_task_uids={"task_1", "task_2"},
        active_task_uids=["task_3", "task_4"],
    )

    synergies = mixin._detect_engagement_synergies()

    assert len(synergies) == 1
    s = synergies[0]
    # ratio 2/4 = 0.5 → 0.3 + (0.5 * 0.6) = 0.6
    assert s.synergy_score == pytest.approx(0.6)
    assert "2/4" in s.rationale
    assert "50%" in s.rationale
    # Not stalled (ratio >= 0.3), not closing (ratio < 0.7) → pending-count reco
    assert any("2 items still pending" in r for r in s.recommendations)


def test_target_uids_truncated_to_six() -> None:
    """Large spawn tuples are truncated for target_uids display surface."""
    spawned = tuple(f"task_{i}" for i in range(10))
    eng = _engagement("ps:big", spawned=spawned, state="completed")
    mixin = _make_mixin(engagements={"ps:big": eng})

    synergies = mixin._detect_engagement_synergies()

    assert len(synergies[0].target_uids) == 6
    assert synergies[0].target_uids == spawned[:6]
