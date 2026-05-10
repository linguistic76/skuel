"""Template + engagement service builder (Phases 4-5 of PS+Activity Templates).

Holds the wiring for the 6 Activity Template CRUD services and
:class:`PsEngagementService`. Kept separate from
``_activity_services.py`` because templates are PS-owned curriculum (no
per-user state), not activity instances — different ownership model,
different lifecycle, different consumers.
"""

from typing import Any

from core.utils.logging import get_logger

logger = get_logger("skuel.bootstrap")


def _create_template_services(
    *,
    executor: Any,
    ps_service: Any,
    # Template backends (one per Activity Template entity type)
    task_template_backend: Any,
    goal_template_backend: Any,
    habit_template_backend: Any,
    event_template_backend: Any,
    choice_template_backend: Any,
    principle_template_backend: Any,
    # Activity instance backends (spawn destinations)
    tasks_backend: Any,
    goals_backend: Any,
    habits_backend: Any,
    events_backend: Any,
    choices_backend: Any,
    principles_backend: Any,
) -> dict[str, Any]:
    """Construct the template + engagement layer.

    Builds (Phase 5):
    - 6 ``*TemplateService`` CRUD facades — one per Activity Template kind.
      Each wraps its UniversalNeo4jBackend and exposes attach/detach/list-for-PS
      helpers backed by the shared executor.

    Builds (Phase 4):
    - ``ps_engagement``: PsEngagementService — 4-transition lifecycle facade.
    """
    from core.services.ps_engagement import PsEngagementService
    from core.services.templates import (
        ChoiceTemplateService,
        EventTemplateService,
        GoalTemplateService,
        HabitTemplateService,
        PrincipleTemplateService,
        TaskTemplateService,
    )

    task_templates = TaskTemplateService(backend=task_template_backend, executor=executor)
    goal_templates = GoalTemplateService(backend=goal_template_backend, executor=executor)
    habit_templates = HabitTemplateService(backend=habit_template_backend, executor=executor)
    event_templates = EventTemplateService(backend=event_template_backend, executor=executor)
    choice_templates = ChoiceTemplateService(backend=choice_template_backend, executor=executor)
    principle_templates = PrincipleTemplateService(
        backend=principle_template_backend, executor=executor
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
