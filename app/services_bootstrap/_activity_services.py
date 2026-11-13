"""Activity Domain service creation — all 6 Activity Domain facades."""

from typing import TYPE_CHECKING

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.models.habit.completion import HabitCompletion
    from core.ports.base_protocols import BackendOperations
    from core.ports.domain_protocols import (
        ChoicesOperations,
        EventsOperations,
        GoalsOperations,
        HabitsOperations,
        PrinciplesOperations,
        TasksOperations,
    )
    from core.ports.infrastructure_protocols import EventBusOperations
    from core.ports.intelligence_protocols import KnowledgeIntelligenceOperations
    from core.services.activity_services import ActivityServices
    from core.services.cross_domain import CrossDomainQueryService
    from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
    from core.services.insight.insight_store import InsightStore

logger = get_logger("skuel.bootstrap")


def _create_activity_services(
    *,
    tasks_backend: TasksOperations,
    events_backend: EventsOperations,
    habits_backend: HabitsOperations,
    habit_completions_backend: BackendOperations[HabitCompletion],
    goals_backend: GoalsOperations,
    choices_backend: ChoicesOperations,
    principles_backend: PrinciplesOperations,
    graph_intelligence: GraphIntelligenceService,
    cross_domain_query: CrossDomainQueryService,
    event_bus: EventBusOperations,
    insight_store: InsightStore,
    activity_knowledge_intelligence: KnowledgeIntelligenceOperations,
) -> ActivityServices:
    """Create the six Activity Domain facades.

    Every facade takes its own backend and the shared dependencies: the graph
    intelligence service, the cross-domain query service, the event bus, the
    insight store and the knowledge intelligence singleton. Habits also takes the
    completions backend.

    Each facade holds its intelligence service as ``facade.intelligence``.
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
            cross_domain_query=cross_domain_query,
            graph_intel=graph_intelligence,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
        "events": EventsService(
            backend=events_backend,
            graph_intel=graph_intelligence,
            cross_domain_query=cross_domain_query,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
        "habits": HabitsService(
            backend=habits_backend,
            graph_intel=graph_intelligence,
            completions_backend=habit_completions_backend,  # REQUIRED - fail-fast
            cross_domain_query=cross_domain_query,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
        "goals": GoalsService(
            backend=goals_backend,
            graph_intel=graph_intelligence,
            cross_domain_query=cross_domain_query,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
        "choices": ChoicesService(
            backend=choices_backend,
            graph_intel=graph_intelligence,
            cross_domain_query=cross_domain_query,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
        "principles": PrinciplesService(
            backend=principles_backend,
            graph_intel=graph_intelligence,
            cross_domain_query=cross_domain_query,
            event_bus=event_bus,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        ),
    }
