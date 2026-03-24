"""Activity Domain service creation — all 6 Activity Domain facades."""

from typing import Any

from core.utils.logging import get_logger

logger = get_logger("skuel.bootstrap")


def _create_activity_services(
    # Backends for all 6 Activity Domains
    tasks_backend: Any,
    events_backend: Any,
    habits_backend: Any,
    habit_completions_backend: Any,
    goals_backend: Any,
    choices_backend: Any,
    principles_backend: Any,
    reflection_backend: Any = None,
    # Shared dependencies
    graph_intelligence: Any = None,
    event_bus: Any = None,
    # Tasks-specific optional dependencies
    ku_inference_service: Any = None,
    analytics_engine: Any = None,
    ku_generation_service: Any = None,
    # Event-driven insights
    insight_store: Any = None,
    # Knowledge intelligence (shared singleton for all 6 domains)
    activity_knowledge_intelligence: Any = None,
) -> dict[str, Any]:
    """Create all 6 Activity Domain services.

    Activity Domains share:
        - backend: UniversalNeo4jBackend[T] for CRUD
        - graph_intelligence: Pure Cypher graph queries (REQUIRED)
        - event_bus: Domain event publishing (optional)

    Domain-specific dependencies:
        - Tasks: ku_inference_service, analytics_engine, ku_generation_service
        - Habits: completions_backend (for achievements)
        - Principles: goals_backend, habits_backend (cross-domain alignment), reflection_backend

    All facades embed intelligence (access via facade.intelligence).
    """
    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.principles_service import PrinciplesService
    from core.services.tasks_service import TasksService

    return {
        "tasks": TasksService(
            backend=tasks_backend,
            ku_inference_service=ku_inference_service,
            analytics_engine=analytics_engine,
            ku_generation_service=ku_generation_service,
            graph_intelligence_service=graph_intelligence,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
        "events": EventsService(
            backend=events_backend,
            graph_intelligence_service=graph_intelligence,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
        "habits": HabitsService(
            backend=habits_backend,
            graph_intelligence_service=graph_intelligence,
            completions_backend=habit_completions_backend,  # REQUIRED - fail-fast
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
        "goals": GoalsService(
            backend=goals_backend,
            graph_intelligence_service=graph_intelligence,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
        "choices": ChoicesService(
            backend=choices_backend,
            graph_intelligence_service=graph_intelligence,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
        "principles": PrinciplesService(
            backend=principles_backend,
            graph_intelligence_service=graph_intelligence,
            goals_backend=goals_backend,
            habits_backend=habits_backend,
            reflection_backend=reflection_backend,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
    }
