"""
Activity Template backends — Phase 2 (model + persistence layer).

One :class:`UniversalNeo4jBackend` subclass per Activity Template entity. The
classes are intentionally thin: Phase 2 only needs CRUD + multi-label storage.
PS-link traversal queries (``HAS_*_TEMPLATE`` edge management, cross-template
reference validation, spawn) live on the engagement service in Phase 4 — keeping
them off the backends here keeps the surface area small and reviewable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend

if TYPE_CHECKING:
    # Imports referenced by the string type parameters in the class definitions
    # below (e.g. ``UniversalNeo4jBackend["TaskTemplate"]``). MyPy resolves the
    # strings; ruff can't see the link, hence the F401 silences.
    from core.models.templates.choice_template import ChoiceTemplate  # noqa: F401
    from core.models.templates.event_template import EventTemplate  # noqa: F401
    from core.models.templates.goal_template import GoalTemplate  # noqa: F401
    from core.models.templates.habit_template import HabitTemplate  # noqa: F401
    from core.models.templates.principle_template import PrincipleTemplate  # noqa: F401
    from core.models.templates.task_template import TaskTemplate  # noqa: F401


class TaskTemplateBackend(UniversalNeo4jBackend["TaskTemplate"]):
    """Domain backend for TaskTemplate (EntityType.TASK_TEMPLATE)."""


class GoalTemplateBackend(UniversalNeo4jBackend["GoalTemplate"]):
    """Domain backend for GoalTemplate (EntityType.GOAL_TEMPLATE)."""


class HabitTemplateBackend(UniversalNeo4jBackend["HabitTemplate"]):
    """Domain backend for HabitTemplate (EntityType.HABIT_TEMPLATE)."""


class EventTemplateBackend(UniversalNeo4jBackend["EventTemplate"]):
    """Domain backend for EventTemplate (EntityType.EVENT_TEMPLATE)."""


class ChoiceTemplateBackend(UniversalNeo4jBackend["ChoiceTemplate"]):
    """Domain backend for ChoiceTemplate (EntityType.CHOICE_TEMPLATE)."""


class PrincipleTemplateBackend(UniversalNeo4jBackend["PrincipleTemplate"]):
    """Domain backend for PrincipleTemplate (EntityType.PRINCIPLE_TEMPLATE)."""
