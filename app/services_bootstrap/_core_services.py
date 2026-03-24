"""Core service helpers — Finance, Transcription, Orchestration, Advanced."""

import os
from typing import Any

from core.utils.logging import get_logger

logger = get_logger("skuel.bootstrap")


def _create_core_services(
    finance_backend: Any,
    invoice_backend: Any,
    transcription_backend: Any,
    user_service: Any,
    deepgram_api_key: str,  # REQUIRED for audio transcription (fail-fast)
    event_bus: Any = None,
) -> dict[str, Any]:
    """Create non-Activity, non-Learning core services (Finance, Transcription, User).

    Activity Domain services are created by _create_activity_services().
    Learning services are created by _create_learning_services().

    Args:
        finance_backend: UniversalNeo4jBackend[ExpensePure]
        invoice_backend: UniversalNeo4jBackend[InvoicePure]
        transcription_backend: UniversalNeo4jBackend[Transcription]
        user_service: UserService for context operations (REQUIRED)
        deepgram_api_key: Deepgram API key for audio transcription (REQUIRED)
        event_bus: Event bus for publishing domain events (optional)
    """
    from adapters.external.deepgram import DeepgramAdapter

    # Create DeepgramAdapter (REQUIRED - fail-fast if key missing)
    # Options loaded from config/deepgram.toml — see docs/configuration/DEEPGRAM_CONFIG.md
    from core.config.deepgram_config import load_deepgram_config
    from core.services.finance_service import FinanceService
    from core.services.transcription import TranscriptionService

    deepgram_config = load_deepgram_config()
    deepgram_adapter = DeepgramAdapter(deepgram_api_key, config=deepgram_config)

    return {
        "finance": FinanceService(
            backend=finance_backend,
            event_bus=event_bus,  # Event-driven architecture
            invoice_backend=invoice_backend,  # Invoice management
        ),
        "transcription": TranscriptionService(
            backend=transcription_backend,
            deepgram_adapter=deepgram_adapter,
            event_bus=event_bus,
        ),
        "deepgram_adapter": deepgram_adapter,  # Exposed for BatchTranscriptionService
        "user": user_service,
    }


def _create_orchestration_services(
    goals_backend: Any,
    tasks_backend: Any,
    habits_backend: Any,
    events_backend: Any,
) -> dict[str, Any]:
    """Create cross-domain orchestration services.

    These are specialized services that coordinate between Activity Domains:
    - GoalTaskGenerator: Creates tasks from goals
    - HabitEventScheduler: Schedules events from habits

    Note: Choices and Principles are now created in _create_activity_services().

    Args:
        goals_backend: UniversalNeo4jBackend[Goal] (label=NeoLabel.GOAL)
        tasks_backend: UniversalNeo4jBackend[Task] (label=NeoLabel.TASK)
        habits_backend: UniversalNeo4jBackend[Habit] (label=NeoLabel.HABIT)
        events_backend: UniversalNeo4jBackend[Event] (label=NeoLabel.EVENT)
    """
    from core.services.goal_task_generator import GoalTaskGenerator
    from core.services.habit_event_scheduler import HabitEventScheduler

    return {
        "goal_task_generator": GoalTaskGenerator(
            goals_backend=goals_backend, tasks_backend=tasks_backend
        ),
        "habit_event_scheduler": HabitEventScheduler(
            habits_backend=habits_backend, events_backend=events_backend
        ),
    }


def _create_advanced_services(_driver: Any, query_executor: Any = None) -> dict[str, Any]:
    """Create advanced services."""
    from pathlib import Path

    from core.services.calendar_optimization_service import CalendarOptimizationService
    from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService
    from core.services.jupyter_neo4j_sync import JupyterNeo4jSync
    from core.services.performance_optimization_service import PerformanceOptimizationService

    vault_path = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/home/mike/0bsidian/skuel"))

    return {
        "calendar_optimization": CalendarOptimizationService(),
        "jupyter_sync": JupyterNeo4jSync(executor=query_executor, vault_path=vault_path),
        "performance_optimization": PerformanceOptimizationService(),
        "cross_domain_analytics": CrossDomainAnalyticsService(executor=query_executor),
    }
