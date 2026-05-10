"""Template + engagement service builder (Phase 4 of PS+Activity Templates).

Holds the wiring for ``PsEngagementService`` and any future template-side
services. Kept separate from ``_activity_services.py`` because templates are
PS-owned curriculum (no per-user state), not activity instances — different
ownership model, different lifecycle, different consumers.
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

    Currently builds one service:
    - ``ps_engagement``: PsEngagementService — 4-transition lifecycle facade.

    Future expansion: per-template authoring CRUD services would slot in here
    when Phase 5 adds the route layer.
    """
    from core.services.ps_engagement import PsEngagementService

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
    logger.info("✅ Template services created (PsEngagementService — Phase 4)")

    return {"ps_engagement": ps_engagement}
