"""Backend instantiation — creates all UniversalNeo4jBackend[T] instances."""

from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics
    from core.ports import QueryExecutor

logger = get_logger("skuel.bootstrap")


def create_all_backends(
    driver: Any,
    query_executor: "QueryExecutor",
    prometheus_metrics: "PrometheusMetrics | None" = None,
) -> dict[str, Any]:
    """Create all domain backends (100% dynamic pattern — direct instantiation).

    Returns dict with named backends for all entity types.

    ``query_executor`` is the single raw-Cypher port (created once in compose);
    standalone backends that take an executor rather than a driver (e.g.
    ``ConnectionFetchBackend``) are built from it here.
    """
    from adapters.persistence.neo4j.backends.activity_backends import (
        ChoicesBackend,
        EventsBackend,
        GoalsBackend,
        HabitsBackend,
        PrinciplesBackend,
        TasksBackend,
    )
    from adapters.persistence.neo4j.backends.curriculum_backends import (
        KuBackend,
        PsBackend,
    )
    from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
    from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
    from core.models.askesis.askesis import Askesis
    from core.models.event.event import Event
    from core.models.finance.finance_pure import ExpensePure
    from core.models.finance.invoice import InvoicePure
    from core.models.goal.goal import Goal
    from core.models.habit.completion import HabitCompletion
    from core.models.habit.habit import Habit
    from core.models.principle.reflection import PrincipleReflection
    from core.models.progress import UserProgress
    from core.models.task.task import Task
    from core.models.transcription.transcription import Transcription

    # ACTIVITY DOMAINS - Domain-specific labels with base_label=NeoLabel.ENTITY
    # for multi-label CREATE: (n:Entity:Task)
    tasks_backend = TasksBackend(
        driver,
        NeoLabel.TASK,
        Task,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    events_backend = EventsBackend(
        driver,
        NeoLabel.EVENT,
        Event,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    habits_backend = HabitsBackend(
        driver,
        NeoLabel.HABIT,
        Habit,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    habit_completions_backend = UniversalNeo4jBackend[HabitCompletion](
        driver,
        NeoLabel.HABIT_COMPLETION,
        HabitCompletion,
        prometheus_metrics=prometheus_metrics,
    )
    goals_backend = GoalsBackend(
        driver,
        NeoLabel.GOAL,
        Goal,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    finance_backend = UniversalNeo4jBackend[ExpensePure](
        driver, NeoLabel.EXPENSE, ExpensePure, prometheus_metrics=prometheus_metrics
    )
    invoice_backend = UniversalNeo4jBackend[InvoicePure](
        driver, NeoLabel.INVOICE, InvoicePure, prometheus_metrics=prometheus_metrics
    )
    transcription_backend = UniversalNeo4jBackend[Transcription](
        driver, NeoLabel.TRANSCRIPTION, Transcription, prometheus_metrics=prometheus_metrics
    )

    # IDENTITY/FOUNDATION - Use dedicated UserBackend (no DTO conversion lifecycle)
    from adapters.persistence.neo4j.user_backend import UserBackend
    from core.models.pathways.path_step import PathStep

    users_backend = UserBackend(driver)
    ps_backend = PsBackend(
        driver,
        NeoLabel.PATH_STEP,
        PathStep,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    from core.models.ku.ku import Ku as AtomicKu

    ku_backend = KuBackend(
        driver,
        NeoLabel.KU,
        AtomicKu,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )

    from core.models.principle.principle import Principle

    principles_backend = PrinciplesBackend(
        driver,
        NeoLabel.PRINCIPLE,
        Principle,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    reflection_backend = UniversalNeo4jBackend[PrincipleReflection](
        driver,
        NeoLabel.PRINCIPLE_REFLECTION,
        PrincipleReflection,
        prometheus_metrics=prometheus_metrics,
    )
    from core.models.choice.choice import Choice

    choices_backend = ChoicesBackend(
        driver,
        NeoLabel.CHOICE,
        Choice,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    progress_backend = UniversalNeo4jBackend[UserProgress](
        driver, NeoLabel.USER_PROGRESS, UserProgress, prometheus_metrics=prometheus_metrics
    )

    # ADR-054 Commit 7 — UserEntryBackend replaces SubmissionsBackend
    user_entry_backend = UserEntryBackend(driver, prometheus_metrics=prometheus_metrics)
    from adapters.persistence.neo4j.backends.misc_backends import ActivityReportBackend
    from core.models.report.activity_report import ActivityReport

    activity_report_backend = ActivityReportBackend(
        driver,
        NeoLabel.ACTIVITY_REPORT,
        ActivityReport,
        base_label=NeoLabel.ENTITY,
        prometheus_metrics=prometheus_metrics,
    )
    askesis_backend = UniversalNeo4jBackend[Askesis](
        driver, NeoLabel.ASKESIS, Askesis, prometheus_metrics=prometheus_metrics
    )

    # ACTIVITY TEMPLATE BACKENDS (Phase 2 of PS+Activity Templates build)
    # Used by PsEngagementService (Phase 4) to load/manage PS-attached templates.
    from adapters.persistence.neo4j.backends.templates_backends import (
        ChoiceTemplateBackend,
        EventTemplateBackend,
        GoalTemplateBackend,
        HabitTemplateBackend,
        PrincipleTemplateBackend,
        TaskTemplateBackend,
    )
    from core.models.templates.choice_template import ChoiceTemplate
    from core.models.templates.event_template import EventTemplate
    from core.models.templates.goal_template import GoalTemplate
    from core.models.templates.habit_template import HabitTemplate
    from core.models.templates.principle_template import PrincipleTemplate
    from core.models.templates.task_template import TaskTemplate

    task_template_backend = TaskTemplateBackend(
        driver,
        NeoLabel.TASK_TEMPLATE,
        TaskTemplate,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    goal_template_backend = GoalTemplateBackend(
        driver,
        NeoLabel.GOAL_TEMPLATE,
        GoalTemplate,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    habit_template_backend = HabitTemplateBackend(
        driver,
        NeoLabel.HABIT_TEMPLATE,
        HabitTemplate,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    event_template_backend = EventTemplateBackend(
        driver,
        NeoLabel.EVENT_TEMPLATE,
        EventTemplate,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    choice_template_backend = ChoiceTemplateBackend(
        driver,
        NeoLabel.CHOICE_TEMPLATE,
        ChoiceTemplate,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )
    principle_template_backend = PrincipleTemplateBackend(
        driver,
        NeoLabel.PRINCIPLE_TEMPLATE,
        PrincipleTemplate,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )

    # Cross-domain connection fetcher (Activity Domain list/detail pages).
    # Standalone backend over the shared executor — keeps raw Cypher below the
    # boundary (ADR-044); the configs stay in core/utils/connection_configs.py.
    from adapters.persistence.neo4j.connection_fetch_backend import ConnectionFetchBackend

    connection_fetch_backend = ConnectionFetchBackend(query_executor)

    logger.info("✅ Domain backends created (100% dynamic pattern - direct instantiation)")

    return {
        "connection_fetch_backend": connection_fetch_backend,
        "tasks_backend": tasks_backend,
        "events_backend": events_backend,
        "habits_backend": habits_backend,
        "habit_completions_backend": habit_completions_backend,
        "goals_backend": goals_backend,
        "finance_backend": finance_backend,
        "invoice_backend": invoice_backend,
        "transcription_backend": transcription_backend,
        "users_backend": users_backend,
        "ps_backend": ps_backend,
        "ku_backend": ku_backend,
        "principles_backend": principles_backend,
        "reflection_backend": reflection_backend,
        "choices_backend": choices_backend,
        "progress_backend": progress_backend,
        "user_entry_backend": user_entry_backend,
        "activity_report_backend": activity_report_backend,
        "askesis_backend": askesis_backend,
        # Activity template backends (Phase 4 — PsEngagementService)
        "task_template_backend": task_template_backend,
        "goal_template_backend": goal_template_backend,
        "habit_template_backend": habit_template_backend,
        "event_template_backend": event_template_backend,
        "choice_template_backend": choice_template_backend,
        "principle_template_backend": principle_template_backend,
    }
