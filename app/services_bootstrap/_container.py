"""Services container — type-safe dataclass holding all wired services."""

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.config.intelligence_tier import IntelligenceTier
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics
    from core.orchestrator.activity_review_orchestrator import ActivityReviewOrchestrator
    from core.orchestrator.admin_orchestrator import AdminOrchestrator
    from core.orchestrator.calendar_optimization_orchestrator import (
        CalendarOptimizationOrchestrator,
    )
    from core.orchestrator.explore_orchestrator import ExploreOrchestrator
    from core.orchestrator.lateral_relationships_orchestrator import (
        LateralRelationshipsOrchestrator,
    )
    from core.orchestrator.library_orchestrator import LibraryOrchestrator
    from core.orchestrator.pathways_orchestrator import PathwaysOrchestrator
    from core.orchestrator.profile_orchestrator import ProfileOrchestrator
    from core.orchestrator.teacher_orchestrator import TeacherOrchestrator
    from core.orchestrator.user_entry_orchestrator import UserEntryOrchestrator
    from core.ports.relationship_backend_protocols import UserRelationshipOperations
    from core.ports.service_protocols import LateralRelationshipOperations
    from core.services.adaptive_lp.adaptive_lp_cross_domain_service import (
        AdaptiveLpCrossDomainService,
    )
    from core.services.admin_stats_service import AdminStatsService
    from core.services.analytics_service import AnalyticsService
    from core.services.askesis_ai_service import AskesisAIService
    from core.services.background.embedding_worker import EmbeddingBackgroundWorker
    from core.services.background.progress_report_worker import ProgressReportWorker

    # Facade services — concrete class IS the contract (no parallel protocol needed)
    from core.services.choices_service import ChoicesService
    from core.services.chunks.batch_chunking_service import BatchChunkingService
    from core.services.content_enrichment_service import ContentEnrichmentService
    from core.services.context_aware_ai_service import ContextAwareAIService
    from core.services.embeddings_service import EmbeddingsService
    from core.services.entry_grounding_service import EntryGroundingService
    from core.services.events_service import EventsService
    from core.services.finance_service import FinanceService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.insight.insight_store import InsightStore
    from core.services.interaction.interaction_service import InteractionService
    from core.services.journal import JournalService
    from core.services.jupyter_neo4j_sync import JupyterNeo4jSync
    from core.services.knowledge import ActivityKnowledgeIntelligenceService
    from core.services.knowledge_domain_service import KnowledgeDomainService
    from core.services.ku_service import KuService
    from core.services.lp_service import LpService
    from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
    from core.services.notifications.notification_service import NotificationService
    from core.services.performance_optimization_service import PerformanceOptimizationService
    from core.services.prereq_suggestion_service import PrereqSuggestionService
    from core.services.principles_service import PrinciplesService
    from core.services.ps_engagement import PsEngagementService
    from core.services.ps_service import PsService
    from core.services.report.activity_report_service import ActivityReportService
    from core.services.report.progress_report_generator import ProgressReportGenerator
    from core.services.report.progress_schedule_service import ProgressScheduleService
    from core.services.report.report_mastery_service import ReportMasteryService
    from core.services.report.review_queue_service import ReviewQueueService
    from core.services.resource_service import ResourceService
    from core.services.tasks_service import TasksService
    from core.services.templates import (
        ChoiceTemplateService,
        EventTemplateService,
        GoalTemplateService,
        HabitTemplateService,
        PrincipleTemplateService,
        TaskTemplateService,
    )
    from core.services.transcription.batch_transcription_service import BatchTranscriptionService
    from core.services.transcription.transcription_service import TranscriptionService
    from core.services.user.intelligence.factory import (
        UserContextIntelligenceFactory,
    )
    from core.services.user_entry.assessment_service import AssessmentService
    from core.services.user_entry.user_entry_processing_service import (
        UserEntryProcessingService,
    )
    from core.services.user_entry.user_entry_service import UserEntryService
    from core.services.user_progress_service import UserProgressService
    from core.services.user_service import UserService
    from core.services.vault.vault_reconciler import VaultReconciler
    from ui.today.orchestrator import TodayOrchestrator

from core.ports import (
    AskesisCoreOperations,
    AskesisOperations,
    AsyncCloseable,
    CalendarServiceOperations,
    Closeable,
    ConnectionFetchOperations,
    ConversationOperations,
    CrossDomainAnalyticsOperations,
    EntryReportOperations,
    EventBusOperations,
    ExerciseOperations,
    FormSubmissionOperations,
    FormTemplateOperations,
    GoalTaskGeneratorOperations,
    GraphAuthOperations,
    GroupOperations,
    HabitEventSchedulerOperations,
    IngestionOperations,
    IntelligenceOperations,
    LifePathOperations,
    QueryExecutor,
    RevisedExerciseOperations,
    SearchOperations,
    SharingOperations,
    SystemServiceOperations,
    TeacherReviewOperations,
    UserContextOperations,
    VisualizationOperations,
    ZPDOperations,
)
from core.utils.logging import get_logger

logger = get_logger("skuel.bootstrap")


@dataclass
class Services:
    """
    Type-safe service container with protocol-based dependencies.

    This replaces the complex DIContainer with a plain dataclass.
    Services are created once during bootstrap and stored here.
    All route-required services are included with proper protocol types.
    """

    # ========================================================================
    # ACTIVITY DOMAINS (6) - All use facade pattern with embedded intelligence
    # Created by _create_activity_services(), access intelligence via .intelligence
    # Concrete types: facade service IS the contract — no parallel protocol needed.
    # ========================================================================
    tasks: "TasksService | None" = None
    goals: "GoalsService | None" = None
    habits: "HabitsService | None" = None
    events: "EventsService | None" = None
    choices: "ChoicesService | None" = None
    principles: "PrinciplesService | None" = None

    # ========================================================================
    # FINANCE (1) - NOT an Activity Domain (standalone facade)
    # ========================================================================
    finance: "FinanceService | None" = None

    # ========================================================================
    # CURRICULUM DOMAINS (3) - PS, KU, LP
    # ========================================================================
    ku: "KuService | None" = None  # KuService (atomic knowledge units)
    knowledge_domains: "KnowledgeDomainService | None" = (
        None  # KnowledgeDomainService — world-layer domain taxonomy (groups Kus)
    )
    resource: "ResourceService | None" = (
        None  # ResourceService (curated content — books, talks, films)
    )
    activity_knowledge_intelligence: "ActivityKnowledgeIntelligenceService | None" = (
        None  # Knowledge intelligence for all 6 activity domains (March 2026)
    )
    # adaptive_sel removed — absorbed into PsService.adaptive (February 2026)
    cross_domain: "AdaptiveLpCrossDomainService | None" = None

    # Content services
    content_enrichment: "ContentEnrichmentService | None" = None
    transcription: "TranscriptionService | None" = None

    # Report services (LLM-based processing)
    report_mastery: "ReportMasteryService | None" = (
        None  # ReportMasteryService - Explicit mastery propagation
    )
    entry_report: EntryReportOperations | None = (
        None  # EntryReportService - LLM report on submission content
    )
    exercises: ExerciseOperations | None = (
        None  # ExerciseService - Reusable LLM instruction templates
    )
    revised_exercises: RevisedExerciseOperations | None = (
        None  # RevisedExerciseService - Four-phase learning loop revision cycle
    )

    # General-purpose forms (March 2026)
    form_templates: "FormTemplateOperations | None" = None
    form_submissions: "FormSubmissionOperations | None" = None

    # Batch transcription service (Tier 1: audio → txt).
    # Tier 2 (BatchProcessingService) retired with ADR-054 Commit 6a — the
    # LLM-driven txt→md path lives inside UserEntryProcessingService now.
    batch_transcription: "BatchTranscriptionService | None" = None

    # Sharing (cross-domain)
    sharing: SharingOperations | None = (
        None  # UnifiedSharingService - Cross-domain sharing and visibility control
    )

    # UserEntry (ADR-054) — unified user-authored content facade.
    # Replaces the legacy submission + journal services.
    user_entry: "UserEntryService | None" = None
    user_entry_processor: "UserEntryProcessingService | None" = None
    user_entry_assessment: "AssessmentService | None" = None

    # ========================================================================
    # GROUP & TEACHING (ADR-040) - Teacher exercise workflow
    # ========================================================================
    groups: GroupOperations | None = None  # GroupService - CRUD + membership for groups
    teacher_review: TeacherReviewOperations | None = (
        None  # TeacherReviewService - review queue + feedback
    )
    notifications: "NotificationService | None" = None  # NotificationService - in-app notifications

    # System services
    # Note: sync field REMOVED (January 2026) - use unified_ingestion instead
    # Note: events moved to Activity Domains section above
    calendar: CalendarServiceOperations | None = (
        None  # CalendarService - unified calendar aggregation
    )
    system: SystemServiceOperations | None = (
        None  # SystemService - health checks and system monitoring
    )
    admin_stats: "AdminStatsService | None" = (
        None  # AdminStatsService - cross-domain admin dashboard statistics
    )
    visualization: VisualizationOperations | None = (
        None  # VisualizationService - Chart.js/Vis.js/Gantt adapters
    )

    # User management (fundamental)
    user: "UserService | None" = None  # Facade — concrete type per CLAUDE.md
    user_relationships: "UserRelationshipOperations | None" = None
    graph_auth: GraphAuthOperations | None = None  # GraphAuthService - graph-native authentication
    context: UserContextOperations | None = (
        None  # UserContextService - context-aware intelligence (NEW: 2025-11-18)
    )
    context_intelligence: "UserContextIntelligenceFactory | None" = None

    # Consolidated Learning Services (V4)
    user_progress: "UserProgressService | None" = None
    # Note: unified_progress DELETED (January 2026) - use user_progress or UserContextBuilder
    lp: "LpService | None" = None  # LpService - All path management
    ps: "PsService | None" = None  # PsService - Dedicated path step management
    # PS+Activity Templates lifecycle facade (Phase 4 — May 2026)
    # Owns 4 transitions: publish/engage/complete/abandon over PS templates.
    ps_engagement: "PsEngagementService | None" = None

    # PS+Activity Templates CRUD services (Phase 5 — May 2026).
    # PS-owned curriculum (no per-user state). Routes wire SHARED scope +
    # TEACHER role gate. Each service exposes attach/detach/list_for_pathstep.
    task_templates: "TaskTemplateService | None" = None
    goal_templates: "GoalTemplateService | None" = None
    habit_templates: "HabitTemplateService | None" = None
    event_templates: "EventTemplateService | None" = None
    choice_templates: "ChoiceTemplateService | None" = None
    principle_templates: "PrincipleTemplateService | None" = None
    learning_intelligence: IntelligenceOperations | None = (
        None  # LpIntelligenceService - analysis and recommendations
    )
    # ZPD service — Zone of Proximal Development (March 2026)
    # Created when INTELLIGENCE_TIER=FULL. None when CORE or curriculum graph < 3 KUs.
    # See: core/services/zpd/zpd_service.py, docs/roadmap/zpd-service-architecture.md
    zpd_service: ZPDOperations | None = None

    askesis: AskesisOperations | None = (
        None  # AskesisService - Unified retrieval chatbot (requires OPENAI_API_KEY)
    )
    askesis_core: AskesisCoreOperations | None = (
        None  # AskesisCoreService - CRUD operations for Askesis AI assistant instances
    )

    # Infrastructure adapters
    graph_adapter: "Neo4jAdapter | None" = None
    event_bus: EventBusOperations | None = None
    prometheus_metrics: "PrometheusMetrics | None" = None

    # Event-driven intelligence
    insight_store: "InsightStore | None" = None

    # Note: choices moved to Activity Domains section above

    # Unified Ingestion Service (ADR-014: Merged MD + YAML ingestion)
    unified_ingestion: IngestionOperations | None = (
        None  # UnifiedIngestionService - handles both MD and YAML for all entity types
    )
    # Batch chunk regeneration (Phase 2, May 2026) — admin tool for rechunking
    # existing :Content when CHUNKING_ALGORITHM_VERSION changes. event_bus is
    # wired only in FULL tier; CORE tier gets a regen-only instance.
    batch_chunking_service: "BatchChunkingService | None" = None

    # The Destination - LifePath (Domain #14)
    # "Everything flows toward the life path"
    # Vision capture + alignment measurement + recommendations
    lifepath: LifePathOperations | None = (
        None  # LifePathService - Vision→Action bridge (January 2026)
    )

    # Analytics services (meta-service, not a domain)
    analytics: "AnalyticsService | None" = None
    cross_domain_analytics: CrossDomainAnalyticsOperations | None = (
        None  # CrossDomainAnalyticsService - Event-driven analytics
    )

    # Search infrastructure (One Path Forward, January 2026)
    search_router: SearchOperations | None = None  # SearchRouter - THE path for all search

    # Orchestration services
    # Note: principles moved to Activity Domains section above
    goal_task_generator: GoalTaskGeneratorOperations | None = (
        None  # GoalTaskGenerator - Auto-generate tasks from goals
    )
    habit_event_scheduler: HabitEventSchedulerOperations | None = (
        None  # HabitEventScheduler - Auto-schedule events from habits
    )
    # Orchestrators (Application Layer)
    admin_orchestrator: "AdminOrchestrator | None" = None
    # Prerequisite-edge suggestion queue (Discovery Analytics PR 4) — admin surface
    prereq_suggestions: "PrereqSuggestionService | None" = None
    # Entry→Ku grounding (Entry-Enrichment PR 3) — post-sync pass + removal route
    entry_grounding: "EntryGroundingService | None" = None
    profile_orchestrator: "ProfileOrchestrator | None" = None
    user_entry_orchestrator: "UserEntryOrchestrator | None" = None
    explore_orchestrator: "ExploreOrchestrator | None" = None
    library_orchestrator: "LibraryOrchestrator | None" = None
    teacher_orchestrator: "TeacherOrchestrator | None" = None
    activity_review_orchestrator: "ActivityReviewOrchestrator | None" = None
    pathways_orchestrator: "PathwaysOrchestrator | None" = None
    lateral_orchestrator: "LateralRelationshipsOrchestrator | None" = None
    calendar_optimization_orchestrator: "CalendarOptimizationOrchestrator | None" = None
    today_orchestrator: "TodayOrchestrator | None" = None

    # Advanced services
    jupyter_sync: "JupyterNeo4jSync | None" = None
    performance_optimization: "PerformanceOptimizationService | None" = None

    # Cross-cutting AI services (require LLM/embeddings - ADR-030: Two-Tier Intelligence Design)
    askesis_ai: "AskesisAIService | None" = None
    context_aware_ai: "ContextAwareAIService | None" = None

    # Infrastructure - Neo4j driver and query executor
    neo4j_driver: "AsyncDriver | None" = None
    query_executor: "QueryExecutor | None" = None
    # Cross-domain connection fetcher for Activity Domain list/detail pages.
    # Below-the-boundary backend behind ConnectionFetchOperations (ADR-044).
    connection_fetch_backend: "ConnectionFetchOperations | None" = None

    # Embedding + vector search services (ADR-068)
    embeddings_service: "EmbeddingsService | None" = None
    vector_search_service: "Neo4jVectorSearchService | None" = None

    # Background workers (January 2026)
    embedding_worker: "EmbeddingBackgroundWorker | None" = None
    progress_report_worker: "ProgressReportWorker | None" = None

    # Progress report generation (February 2026)
    progress_report_generator: "ProgressReportGenerator | None" = None
    progress_schedule: "ProgressScheduleService | None" = None

    # Activity report + review queue (March 2026 refactor: ActivityReviewService split)
    activity_report: "ActivityReportService | None" = None
    review_queue: "ReviewQueueService | None" = None

    # ========================================================================
    # LATERAL RELATIONSHIP SERVICES (January 2026) - Core Graph Architecture
    # ========================================================================
    lateral: "LateralRelationshipOperations | None" = None

    # Interaction audit (User Interaction Contract — EntityType.INTERACTION)
    interaction_service: "InteractionService | None" = None

    # Vault bridge (ADR-070) — bidirectional Obsidian ↔ SKUEL sync
    vault_reconciler: "VaultReconciler | None" = None

    # Journal domain — DNWF three-stage workflow (FULL tier only)
    journal: "JournalService | None" = None

    # Conversation store — owner-private discussion sessions (ADR-078).
    # Tier-independent (pure persistence); the understanding-agnostic boundary.
    conversation: "ConversationOperations | None" = None

    # Intelligence tier (ADR-043: CORE = analytics only, FULL = analytics + AI)
    intelligence_tier: "IntelligenceTier | None" = None

    # Services are ready when constructed - no lifecycle needed

    async def cleanup(self) -> None:
        """Clean up all async resources (idempotent — safe to call multiple times)"""
        logger.info("Cleaning up service container...")

        # Close database connection with detailed logging
        if self.graph_adapter:
            adapter = self.graph_adapter
            self.graph_adapter = None  # Clear first to prevent double-close
            try:
                logger.info("Closing graph adapter...")
                if isinstance(adapter, AsyncCloseable):
                    await adapter.close()
                logger.info("Graph adapter closed")
            except (
                Exception
            ) as e:  # safety-net: service bootstrap must report initialization failures
                logger.warning(f"Error closing graph adapter: {e}")

        # Close event bus with detailed logging
        if self.event_bus:
            bus = self.event_bus
            self.event_bus = None  # Clear first to prevent double-close
            try:
                logger.info("Closing event bus...")
                if isinstance(bus, AsyncCloseable):
                    await bus.close()
                logger.info("Event bus closed")
            except (
                Exception
            ) as e:  # safety-net: service bootstrap must report initialization failures
                logger.warning(f"Error closing event bus: {e}")

        # Auto-close all remaining closeable fields (no hardcoded list)
        already_handled = {"graph_adapter", "event_bus"}
        for f in fields(self):
            if f.name in already_handled:
                continue
            service = getattr(self, f.name)
            if service is None:
                continue
            try:
                if isinstance(service, AsyncCloseable):
                    logger.info(f"Closing {f.name}...")
                    await service.close()
                    logger.info(f"{f.name} closed")
                elif isinstance(service, Closeable):
                    logger.info(f"Closing {f.name}...")
                    service.close()
                    logger.info(f"{f.name} closed")
            except (
                Exception
            ) as e:  # safety-net: service bootstrap must report initialization failures
                logger.warning(f"Error closing {f.name}: {e}")

        logger.info("✅ Service container cleanup complete")
