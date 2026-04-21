"""
Sentinel Tests for UserContext Rich-Only Fields
================================================

Guards the six fields that are populated exclusively by ``build_rich()``
and silently absent at standard ``build()`` depth:

    - tasks_by_goal
    - habits_by_goal
    - at_risk_habits
    - blocked_task_uids
    - principle_guided_choice_counts
    - recent_principle_aligned_choices

Contract enforced here:

1. At standard depth (``is_rich_context=False``), every rich-only field
   defaults to ``None`` — not an empty container — so silent no-op reads
   cannot masquerade as legitimate zero state.
2. Accessor methods for rich-only data (``get_tasks_for_goal``,
   ``get_habits_for_goal``, ``get_blocked_tasks``,
   ``get_habits_needing_reinforcement``) raise
   ``RichContextRequiredError`` when called on a standard-depth context.
3. The ``RICH_ONLY_FIELDS`` ClassVar matches the fields we actually
   store as ``| None``. Drift between the registry and the dataclass
   is a silent-failure hazard.
4. With ``is_rich_context=True`` + populated containers, accessors
   return the expected data.
"""

from __future__ import annotations

import pytest

from core.errors import RichContextRequiredError
from core.services.user.unified_user_context import UserContext

# =============================================================================
# Registry integrity
# =============================================================================


def test_rich_only_fields_registry_matches_expected_set() -> None:
    """The RICH_ONLY_FIELDS ClassVar is the contract — pin it explicitly."""
    expected = frozenset(
        {
            "tasks_by_goal",
            "habits_by_goal",
            "at_risk_habits",
            "blocked_task_uids",
            "principle_guided_choice_counts",
            "recent_principle_aligned_choices",
        }
    )
    assert expected == UserContext.RICH_ONLY_FIELDS


# =============================================================================
# Standard depth: None defaults
# =============================================================================


@pytest.fixture
def standard_context() -> UserContext:
    """Minimal standard-depth context — what build() produces."""
    return UserContext(user_uid="user:test", username="testuser")


def test_standard_depth_is_not_rich(standard_context: UserContext) -> None:
    assert standard_context.is_rich_context is False


@pytest.mark.parametrize(
    "field_name",
    [
        "tasks_by_goal",
        "habits_by_goal",
        "at_risk_habits",
        "blocked_task_uids",
        "principle_guided_choice_counts",
        "recent_principle_aligned_choices",
    ],
)
def test_rich_only_field_defaults_to_none_at_standard_depth(
    standard_context: UserContext, field_name: str
) -> None:
    """Every rich-only field must be None — not an empty container."""
    assert getattr(standard_context, field_name) is None


# =============================================================================
# Standard depth: accessors raise
# =============================================================================


def test_get_tasks_for_goal_raises_at_standard_depth(
    standard_context: UserContext,
) -> None:
    with pytest.raises(RichContextRequiredError) as exc_info:
        standard_context.get_tasks_for_goal("goal:anything")
    assert exc_info.value.operation == "get_tasks_for_goal"


def test_get_habits_for_goal_raises_at_standard_depth(
    standard_context: UserContext,
) -> None:
    with pytest.raises(RichContextRequiredError) as exc_info:
        standard_context.get_habits_for_goal("goal:anything")
    assert exc_info.value.operation == "get_habits_for_goal"


def test_get_blocked_tasks_raises_at_standard_depth(
    standard_context: UserContext,
) -> None:
    with pytest.raises(RichContextRequiredError) as exc_info:
        standard_context.get_blocked_tasks()
    assert exc_info.value.operation == "get_blocked_tasks"


def test_get_habits_needing_reinforcement_raises_at_standard_depth(
    standard_context: UserContext,
) -> None:
    with pytest.raises(RichContextRequiredError) as exc_info:
        standard_context.get_habits_needing_reinforcement()
    assert exc_info.value.operation == "get_habits_needing_reinforcement"


def test_require_rich_context_raises_at_standard_depth(
    standard_context: UserContext,
) -> None:
    with pytest.raises(RichContextRequiredError) as exc_info:
        standard_context.require_rich_context("custom_op")
    assert exc_info.value.operation == "custom_op"


# =============================================================================
# Rich depth: accessors succeed
# =============================================================================


@pytest.fixture
def rich_context() -> UserContext:
    """Rich-depth context with rich-only fields populated."""
    return UserContext(
        user_uid="user:test",
        username="testuser",
        is_rich_context=True,
        tasks_by_goal={
            "goal:a": ["task:1", "task:2"],
            "goal:b": ["task:3"],
        },
        habits_by_goal={
            "goal:a": ["habit:x"],
            "goal:c": ["habit:y", "habit:z"],
        },
        at_risk_habits=["habit:x", "habit:y"],
        blocked_task_uids={"task:blocked_1", "task:blocked_2"},
        principle_guided_choice_counts={"principle:minimalism": 3},
        recent_principle_aligned_choices=["choice:1", "choice:2"],
    )


def test_rich_context_is_rich(rich_context: UserContext) -> None:
    assert rich_context.is_rich_context is True


def test_get_tasks_for_goal_at_rich_depth(rich_context: UserContext) -> None:
    assert rich_context.get_tasks_for_goal("goal:a") == ["task:1", "task:2"]
    assert rich_context.get_tasks_for_goal("goal:missing") == []


def test_get_habits_for_goal_at_rich_depth(rich_context: UserContext) -> None:
    assert rich_context.get_habits_for_goal("goal:c") == ["habit:y", "habit:z"]
    assert rich_context.get_habits_for_goal("goal:missing") == []


def test_get_blocked_tasks_at_rich_depth(rich_context: UserContext) -> None:
    assert rich_context.get_blocked_tasks() == {"task:blocked_1", "task:blocked_2"}


def test_get_habits_needing_reinforcement_at_rich_depth(
    rich_context: UserContext,
) -> None:
    assert rich_context.get_habits_needing_reinforcement() == ["habit:x", "habit:y"]


def test_require_rich_context_passes_at_rich_depth(
    rich_context: UserContext,
) -> None:
    rich_context.require_rich_context("custom_op")


# =============================================================================
# Error message quality
# =============================================================================


def test_rich_context_error_names_operation(standard_context: UserContext) -> None:
    """The error should identify which operation was attempted."""
    with pytest.raises(RichContextRequiredError) as exc_info:
        standard_context.get_blocked_tasks()
    assert "get_blocked_tasks" in str(exc_info.value)
    assert "build_rich" in str(exc_info.value)
