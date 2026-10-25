"""Backend instantiation — the one constructor of every backend the application runs."""

from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics

logger = get_logger("skuel.bootstrap")


def create_all_backends(
    driver: Any,
    query_executor: Neo4jQueryExecutor,
    prometheus_metrics: PrometheusMetrics | None = None,
) -> dict[str, Any]:
    """Create every backend the application runs — the one place each is built.

    Returns a dict of named backends: the domain backends for the entity types,
    then the purpose-built backends each service family reads through. Every
    consumer in the composition root takes its backend from this dict, and so
    do every test and every script (``tests/unit/test_production_backend_census.py``),
    so the class, label, base label and entity class a backend runs with are
    stated once.

    ``query_executor`` is the single raw-Cypher port (created once in compose);
    backends that take an executor rather than a driver (e.g.
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

    # Cross-activity reads over any :Entity node — ActivityKnowledgeIntelligenceService,
    # the one knowledge-intelligence service the six Activity facades share.
    from core.models.entity import Entity

    activity_entity_backend = UniversalNeo4jBackend[Entity](
        driver,
        NeoLabel.ENTITY,
        Entity,
        prometheus_metrics=prometheus_metrics,
        base_label=NeoLabel.ENTITY,
    )

    # The Activity pages' link reader (list cards, detail pages, the day view).
    # Standalone backend over the shared executor — keeps raw Cypher below the
    # boundary (ADR-044); what a page shows is the registry's page views (ADR-090 §2).
    from adapters.persistence.neo4j.connection_fetch_backend import ConnectionFetchBackend

    connection_fetch_backend = ConnectionFetchBackend(query_executor)

    # PURPOSE-BUILT BACKENDS - each serves one service family, over the driver or
    # the shared executor. Built in every tier: a backend holds only its handle and
    # runs nothing until called, so the tier gates the services, not these.
    from adapters.persistence.neo4j.backends.collab_backends import (
        GroupBackend,
        LateralRelationshipBackend,
        NotificationBackend,
        ReviewQueueBackend,
    )
    from adapters.persistence.neo4j.backends.conversation_backend import ConversationBackend
    from adapters.persistence.neo4j.backends.curriculum_backends import (
        EmbeddingCoverageBackend,
        KnowledgeHealthBackend,
        LpBackend,
    )
    from adapters.persistence.neo4j.backends.exercise_backends import (
        EntryReportBackend,
        ExerciseBackend,
        RevisedExerciseBackend,
    )
    from adapters.persistence.neo4j.backends.forms_backends import (
        FormSubmissionBackend,
        FormTemplateBackend,
    )
    from adapters.persistence.neo4j.backends.misc_backends import (
        ActivityReportGeneratorBackend,
        InteractionBackend,
        ResourceBackend,
    )
    from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
    from adapters.persistence.neo4j.batch_chunking_backend import BatchChunkingBackend
    from adapters.persistence.neo4j.bulk_upsert_backend import BulkUpsertBackend
    from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
    from adapters.persistence.neo4j.device_backend import DeviceBackend
    from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
    from adapters.persistence.neo4j.entry_grounding_backend import EntryGroundingBackend
    from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
    from adapters.persistence.neo4j.ingestion_write_backend import IngestionWriteBackend
    from adapters.persistence.neo4j.insight_backend import InsightBackend
    from adapters.persistence.neo4j.lifepath_backend import LifePathBackend
    from adapters.persistence.neo4j.prereq_candidate_backend import PrereqCandidateBackend
    from adapters.persistence.neo4j.ps_engagement_backend import PsEngagementBackend
    from adapters.persistence.neo4j.ps_intelligence_backend import PsIntelligenceBackend
    from adapters.persistence.neo4j.search_event_backend import SearchEventBackend
    from adapters.persistence.neo4j.session_backend import SessionBackend
    from adapters.persistence.neo4j.template_attachment_backend import TemplateAttachmentBackend
    from adapters.persistence.neo4j.uid_census_backend import UidCensusBackend
    from adapters.persistence.neo4j.user_progress_backend import UserProgressBackend
    from adapters.persistence.neo4j.user_relationship_backend import UserRelationshipBackend
    from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend
    from adapters.persistence.neo4j.zpd_backend import ZPDBackend
    from adapters.persistence.neo4j.zpd_snapshot_backend import ZPDSnapshotBackend
    from core.models.exercises.exercise import Exercise
    from core.models.exercises.revised_exercise import RevisedExercise
    from core.models.forms.form_submission import FormSubmission
    from core.models.forms.form_template import FormTemplate
    from core.models.group.group import Group
    from core.models.interaction.interaction import Interaction
    from core.models.pathways.learning_path import LearningPath
    from core.models.report.entry_report import EntryReport
    from core.models.resource.resource import Resource

    purpose_built = {
        # Identity, sessions, devices, social graph
        "session_backend": SessionBackend(driver),
        "device_backend": DeviceBackend(driver),
        "user_relationship_backend": UserRelationshipBackend(executor=query_executor),
        "conversation_backend": ConversationBackend(driver),
        # Cross-domain reads, analytics, insights, telemetry
        "cross_domain_backend": CrossDomainBackend(query_executor),
        "knowledge_health_backend": KnowledgeHealthBackend(query_executor),
        "embedding_coverage_backend": EmbeddingCoverageBackend(query_executor),
        "insight_backend": InsightBackend(query_executor),
        "search_event_backend": SearchEventBackend(query_executor),
        "uid_census_backend": UidCensusBackend(query_executor),
        # Ingestion and chunking
        "ingestion_backend": IngestionBackend(executor=query_executor),
        "ingestion_write_backend": IngestionWriteBackend(driver),
        "bulk_upsert_backend": BulkUpsertBackend(driver),
        "batch_chunking_backend": BatchChunkingBackend(driver),
        # Curriculum, progress, engagement
        "lp_backend": LpBackend(
            driver, NeoLabel.LEARNING_PATH, LearningPath, base_label=NeoLabel.ENTITY
        ),
        "user_progress_backend": UserProgressBackend(query_executor),
        "ps_intelligence_backend": PsIntelligenceBackend(query_executor),
        "template_attachment_backend": TemplateAttachmentBackend(query_executor),
        "ps_engagement_backend": PsEngagementBackend(query_executor),
        "prereq_candidate_backend": PrereqCandidateBackend(query_executor),
        "lateral_relationship_backend": LateralRelationshipBackend(executor=query_executor),
        # Embeddings, vector search, grounding, ZPD
        "embeddings_backend": EmbeddingsBackend(executor=query_executor),
        "vector_search_backend": VectorSearchBackend(executor=query_executor),
        "entry_grounding_backend": EntryGroundingBackend(query_executor),
        "zpd_backend": ZPDBackend(driver),
        "zpd_snapshot_backend": ZPDSnapshotBackend(driver),
        # Learning loop: exercises, reports, revisions, interactions
        "exercise_backend": ExerciseBackend(
            driver=driver,
            label=NeoLabel.EXERCISE,
            entity_class=Exercise,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        ),
        "entry_report_backend": EntryReportBackend(
            driver=driver,
            label=NeoLabel.ENTRY_REPORT,
            entity_class=EntryReport,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        ),
        "revised_exercise_backend": RevisedExerciseBackend(
            driver=driver,
            label=NeoLabel.REVISED_EXERCISE,
            entity_class=RevisedExercise,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        ),
        "interaction_backend": InteractionBackend(
            driver=driver,
            label=NeoLabel.INTERACTION,
            entity_class=Interaction,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        ),
        "review_queue_backend": ReviewQueueBackend(executor=query_executor),
        "activity_report_generator_backend": ActivityReportGeneratorBackend(
            executor=query_executor
        ),
        # Resources, forms, groups, sharing, notifications, life path
        "resource_backend": ResourceBackend(
            driver=driver,
            label=NeoLabel.RESOURCE,
            entity_class=Resource,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        ),
        "form_template_backend": FormTemplateBackend(
            driver=driver,
            label=NeoLabel.FORM_TEMPLATE,
            entity_class=FormTemplate,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        ),
        "form_submission_backend": FormSubmissionBackend(
            driver=driver,
            label=NeoLabel.FORM_SUBMISSION,
            entity_class=FormSubmission,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        ),
        "group_backend": GroupBackend(
            driver=driver,
            label=NeoLabel.GROUP,
            entity_class=Group,
            prometheus_metrics=prometheus_metrics,
        ),
        "sharing_backend": SharingBackend(
            driver, NeoLabel.ENTITY, Entity, prometheus_metrics=prometheus_metrics
        ),
        "notification_backend": NotificationBackend(executor=query_executor),
        "lifepath_backend": LifePathBackend(query_executor),
    }

    logger.info("✅ Backends created (100% dynamic pattern - direct instantiation)")

    return {
        **purpose_built,
        "connection_fetch_backend": connection_fetch_backend,
        "activity_entity_backend": activity_entity_backend,
        "tasks_backend": tasks_backend,
        "events_backend": events_backend,
        "habits_backend": habits_backend,
        "habit_completions_backend": habit_completions_backend,
        "goals_backend": goals_backend,
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
