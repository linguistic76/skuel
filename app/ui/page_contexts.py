"""Per-domain page context types for route→UI contracts.

Presentation-layer TypedDicts that define the contract between routes and
UI view components. These are UI concerns, NOT service-layer contracts.

Each Activity Domain gets a standalone TypedDict with properly typed entities.
Required fields use ``total=True`` (default); optional fields use ``NotRequired``.

Usage::

    from ui.page_contexts import TasksPageContext

    ctx: TasksPageContext = {
        "entities": tasks,
        "filters": filters,
    }
    view_content = TasksViewComponents.render_list_view(ctx)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

if TYPE_CHECKING:
    from core.models.choice.choice import Choice
    from core.models.curriculum import Curriculum
    from core.models.event.event import Event
    from core.models.exercises.exercise import Exercise
    from core.models.goal.goal import Goal
    from core.models.habit.habit import Habit
    from core.models.ku.ku import Ku
    from core.models.principle.principle import Principle
    from core.models.submissions.exercise_submission import ExerciseSubmission
    from core.models.task.task import Task


# ============================================================================
# Activity Domain Contexts
# ============================================================================


class TasksPageContext(TypedDict):
    """Tasks list view context."""

    entities: list[Task]
    filters: dict[str, Any]
    projects: NotRequired[list[str]]
    assignees: NotRequired[list[str]]
    view: NotRequired[str]


class GoalsPageContext(TypedDict):
    """Goals list view context."""

    entities: list[Goal]
    stats: dict[str, int | float]
    filters: dict[str, Any]
    categories: NotRequired[list[str]]
    view: NotRequired[str]


class HabitsPageContext(TypedDict):
    """Habits list view context."""

    entities: list[Habit]
    stats: dict[str, int | float]
    filters: dict[str, Any]
    categories: NotRequired[list[str]]
    view: NotRequired[str]


class EventsPageContext(TypedDict):
    """Events list view context."""

    entities: list[Event]
    stats: dict[str, int | float]
    filters: dict[str, Any]
    view: NotRequired[str]


class ChoicesPageContext(TypedDict):
    """Choices list view context."""

    entities: list[Choice]
    stats: dict[str, int | float]
    filters: dict[str, Any]
    view: NotRequired[str]


class PrinciplesPageContext(TypedDict):
    """Principles list view context."""

    entities: list[Principle]
    stats: dict[str, int | float]
    filters: dict[str, Any]
    categories: NotRequired[list[str]]
    view: NotRequired[str]


# ============================================================================
# Curriculum Contexts
# ============================================================================


class CurriculumHubContext(TypedDict, total=False):
    """Curriculum landing page context."""

    lesson_count: int
    ls_count: int
    lp_count: int
    exercise_count: int


class CurriculumListContext(TypedDict, total=False):
    """Curriculum sub-page list context."""

    entities: list[Curriculum]
    active_section: str


# ============================================================================
# Study / Submissions Context
# ============================================================================


class SubmissionsPageContext(TypedDict, total=False):
    """Study submissions page context."""

    submissions: list[ExerciseSubmission]
    exercises: list[Exercise]


# ============================================================================
# KU Context
# ============================================================================


class KuIndexContext(TypedDict, total=False):
    """Knowledge Unit index page context."""

    kus: list[Ku]
    pinned_uids: list[str]
    latest: list[Ku]
    bookmarked: list[Ku]
