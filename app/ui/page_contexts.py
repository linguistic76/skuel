"""Per-domain page context types for route→UI contracts.

Presentation-layer TypedDicts that define the contract between routes and
UI view components. These are UI concerns, NOT service-layer contracts.

The existing ``ListContext`` in ``core/ports/query_types.py`` stays unchanged —
page contexts narrow that contract at the presentation layer.
"""

from typing import Any, TypedDict

# ============================================================================
# Activity Domain Contexts
# ============================================================================


class ActivityPageContext(TypedDict, total=False):
    """Base for all 6 Activity Domain list views."""

    entities: list[Any]
    stats: dict[str, int]
    filters: dict[str, Any]
    view: str  # "list" | "create" | "calendar" | "analytics"


class TasksPageContext(ActivityPageContext, total=False):
    """Tasks list view context with project/assignee extensions."""

    projects: list[str]
    assignees: list[str]


class GoalsPageContext(ActivityPageContext, total=False):
    """Goals list view context."""

    categories: list[str]


class HabitsPageContext(ActivityPageContext, total=False):
    """Habits list view context."""

    categories: list[str]


class EventsPageContext(ActivityPageContext, total=False):
    """Events list view context."""


class ChoicesPageContext(ActivityPageContext, total=False):
    """Choices list view context."""


class PrinciplesPageContext(ActivityPageContext, total=False):
    """Principles list view context."""

    categories: list[str]


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

    entities: list[Any]
    active_section: str


# ============================================================================
# Study / Submissions Context
# ============================================================================


class SubmissionsPageContext(TypedDict, total=False):
    """Study submissions page context."""

    submissions: list[Any]
    exercises: list[Any]


# ============================================================================
# KU Context
# ============================================================================


class KuIndexContext(TypedDict, total=False):
    """Knowledge Unit index page context."""

    kus: list[Any]
    pinned_uids: list[str]
    latest: list[Any]
    bookmarked: list[Any]
