"""Template + engagement service builder (Phases 4-5 of PS+Activity Templates).

Holds the wiring for the 6 Activity Template CRUD services and
:class:`PsEngagementService`. Kept separate from
``_activity_services.py`` because templates are PS-owned curriculum (no
per-user state), not activity instances — different ownership model,
different lifecycle, different consumers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.choice.choice import Choice
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.event_template import EventTemplate
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.task_template import TaskTemplate
from core.ports import CrudOperations
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

logger = get_logger("skuel.bootstrap")


def _create_template_services(
    *,
    executor: Neo4jQueryExecutor,
    ps_service: Any,
    # Template backends (one per Activity Template entity type)
    task_template_backend: CrudOperations[TaskTemplate],
    goal_template_backend: CrudOperations[GoalTemplate],
    habit_template_backend: CrudOperations[HabitTemplate],
    event_template_backend: CrudOperations[EventTemplate],
    choice_template_backend: CrudOperations[ChoiceTemplate],
    principle_template_backend: CrudOperations[PrincipleTemplate],
    # Activity instance backends (spawn destinations)
    tasks_backend: CrudOperations[Task],
    goals_backend: CrudOperations[Goal],
    habits_backend: CrudOperations[Habit],
    events_backend: CrudOperations[Event],
    choices_backend: CrudOperations[Choice],
    principles_backend: CrudOperations[Principle],
) -> dict[str, Any]:
    """Construct the template + engagement layer.

    Builds (Phase 5):
    - 6 ``*TemplateService`` CRUD facades — one per Activity Template kind.
      Each wraps its UniversalNeo4jBackend and exposes attach/detach/list-for-PS
      helpers backed by the shared executor.

    Builds (Phase 4):
    - ``ps_engagement``: PsEngagementService — 4-transition lifecycle facade.
    """
    from adapters.persistence.neo4j.template_attachment_backend import TemplateAttachmentBackend
    from core.services.ps_engagement import PsEngagementService
    from core.services.templates import (
        ChoiceTemplateService,
        EventTemplateService,
        GoalTemplateService,
        HabitTemplateService,
        PrincipleTemplateService,
        TaskTemplateService,
    )

    # One shared attachment backend — stateless, the edge type is passed per call.
    attachment = TemplateAttachmentBackend(executor)

    task_templates = TaskTemplateService(backend=task_template_backend, attachment=attachment)
    goal_templates = GoalTemplateService(backend=goal_template_backend, attachment=attachment)
    habit_templates = HabitTemplateService(backend=habit_template_backend, attachment=attachment)
    event_templates = EventTemplateService(backend=event_template_backend, attachment=attachment)
    choice_templates = ChoiceTemplateService(backend=choice_template_backend, attachment=attachment)
    principle_templates = PrincipleTemplateService(
        backend=principle_template_backend, attachment=attachment
    )

    ps_engagement = PsEngagementService(
        executor=executor,
        ps_service=ps_service,
        task_template_backend=task_template_backend,
        goal_template_backend=goal_template_backend,
        habit_template_backend=habit_template_backend,
        event_template_backend=event_template_backend,
        choice_template_backend=choice_template_backend,
        principle_template_backend=principle_template_backend,
        tasks_backend=tasks_backend,
        goals_backend=goals_backend,
        habits_backend=habits_backend,
        events_backend=events_backend,
        choices_backend=choices_backend,
        principles_backend=principles_backend,
    )
    logger.info(
        "✅ Template services created: 6 CRUD facades (Phase 5) + PsEngagementService (Phase 4)"
    )

    return {
        "ps_engagement": ps_engagement,
        "task_templates": task_templates,
        "goal_templates": goal_templates,
        "habit_templates": habit_templates,
        "event_templates": event_templates,
        "choice_templates": choice_templates,
        "principle_templates": principle_templates,
    }
