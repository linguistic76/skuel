"""Core service helpers — Finance, Transcription, Orchestration, Advanced."""

from typing import TYPE_CHECKING, TypedDict

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.external.deepgram import DeepgramAdapter
    from core.models.finance.invoice import InvoicePure
    from core.models.transcription.transcription import Transcription
    from core.ports import BackendOperations, EventBusOperations
    from core.ports.cross_domain_protocols import CrossDomainBackendOperations
    from core.ports.domain_protocols import (
        BaseRelationshipOperations,
        GoalsOperations,
        HabitsOperations,
    )
    from core.services.calendar_optimization_service import CalendarOptimizationService
    from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService
    from core.services.events_service import EventsService
    from core.services.finance_service import FinanceService
    from core.services.goal_task_generator import GoalTaskGenerator
    from core.services.habit_event_scheduler import HabitEventScheduler
    from core.services.relationships import UnifiedRelationshipService
    from core.services.tasks_service import TasksService
    from core.services.transcription import TranscriptionService

logger = get_logger("skuel.bootstrap")


class CoreServices(TypedDict):
    """Finance, and the transcription pair — ``None`` where no Deepgram key is given."""

    finance: FinanceService
    transcription: TranscriptionService | None
    deepgram_adapter: DeepgramAdapter | None


class OrchestrationServices(TypedDict):
    """The two services that create one Activity Domain's entities from another's."""

    goal_task_generator: GoalTaskGenerator
    habit_event_scheduler: HabitEventScheduler


class AdvancedServices(TypedDict):
    """Calendar optimization and cross-domain analytics."""

    calendar_optimization: CalendarOptimizationService
    cross_domain_analytics: CrossDomainAnalyticsService


def _create_core_services(
    invoice_backend: BackendOperations[InvoicePure],
    transcription_backend: BackendOperations[Transcription],
    deepgram_api_key: str | None,  # None in CORE tier; str in FULL tier (Digital layer)
    event_bus: EventBusOperations,
) -> CoreServices:
    """Create non-Activity, non-Learning core services (Finance, Transcription).

    Activity Domain services are created by _create_activity_services().
    Learning services are created by _create_learning_services().

    Args:
        invoice_backend: UniversalNeo4jBackend[InvoicePure]
        transcription_backend: UniversalNeo4jBackend[Transcription]
        deepgram_api_key: Deepgram API key. None in CORE tier (transcription is Digital);
            str in FULL tier (validated by caller before this call).
        event_bus: Event bus for publishing domain events
    """
    from adapters.outbound.invoice_renderer import render_invoice_pdf
    from core.services.finance_service import FinanceService

    result: CoreServices = {
        "finance": FinanceService(
            invoice_backend=invoice_backend,
            invoice_renderer=render_invoice_pdf,
            event_bus=event_bus,
        ),
        "transcription": None,
        "deepgram_adapter": None,
    }

    if deepgram_api_key:
        from adapters.external.deepgram import DeepgramAdapter
        from core.config.deepgram_config import load_deepgram_config
        from core.services.transcription import TranscriptionService

        deepgram_config = load_deepgram_config()
        deepgram_adapter = DeepgramAdapter(deepgram_api_key, config=deepgram_config)
        result["deepgram_adapter"] = deepgram_adapter
        result["transcription"] = TranscriptionService(
            backend=transcription_backend,
            deepgram_adapter=deepgram_adapter,
            event_bus=event_bus,
        )

    return result


def _create_orchestration_services(
    goals_backend: GoalsOperations,
    tasks_service: TasksService,
    goals_relationships: UnifiedRelationshipService,
    habits_backend: HabitsOperations,
    events_service: EventsService,
    habits_relationships: BaseRelationshipOperations,
) -> OrchestrationServices:
    """Create cross-domain orchestration services.

    These are specialized services that coordinate between Activity Domains:
    - GoalTaskGenerator: Creates tasks from goals
    - HabitEventScheduler: Schedules events from habits

    Args:
        goals_backend: UniversalNeo4jBackend[Goal] (label=NeoLabel.GOAL)
        tasks_service: TasksService — the generator persists through its entity
            door (the one create path for Tasks), never a backend handle
        goals_relationships: GoalsService.relationships — the generator reads the
            knowledge a goal requires and the habits that support it, which its
            knowledge and habit tasks are generated from
        habits_backend: UniversalNeo4jBackend[Habit] (label=NeoLabel.HABIT)
        events_service: EventsService — the scheduler persists through its entity
            door (the one create path for Events), never a backend handle
        habits_relationships: HabitsService.relationships — the scheduler reads the
            goals a habit supports, which its scheduled events contribute to
    """
    from core.services.goal_task_generator import GoalTaskGenerator
    from core.services.habit_event_scheduler import HabitEventScheduler

    return {
        "goal_task_generator": GoalTaskGenerator(
            goals_backend=goals_backend,
            tasks_service=tasks_service,
            relationship_service=goals_relationships,
        ),
        "habit_event_scheduler": HabitEventScheduler(
            habits_backend=habits_backend,
            events_service=events_service,
            relationship_service=habits_relationships,
        ),
    }


def _create_advanced_services(
    cross_domain_backend: CrossDomainBackendOperations,
) -> AdvancedServices:
    """Create the calendar optimization and cross-domain analytics services."""
    from core.services.calendar_optimization_service import CalendarOptimizationService
    from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService

    return {
        "calendar_optimization": CalendarOptimizationService(),
        "cross_domain_analytics": CrossDomainAnalyticsService(backend=cross_domain_backend),
    }
