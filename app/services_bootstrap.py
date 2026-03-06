"""
Lightweight Service Bootstrap for SKUEL
=======================================

SKUEL's Entity Type + Cross-Cutting System Service Composition
---------------------------------------------------------------

This module is the composition root for SKUEL's complete architecture.
It wires together all domain services and cross-cutting systems using
constructor injection - no heavy DI framework required.

ENTITY TYPE SERVICES COMPOSED HERE
-----------------------------------

    1. tasks → TasksService - Work items and dependencies
    2. goals → GoalsService - Objectives and milestones
    3. habits → HabitsService - Recurring behaviors and streaks
    4. events → EventsService - Calendar items and scheduling
    5. choices → ChoicesService - Decisions and outcomes
    6. principles → PrinciplesService - Values and alignment
    7. finance → FinanceService - Expenses and budgets
    8. knowledge → ArticleService - Knowledge Units (ku:)
    9. ls → LsService - Learning Steps (ls:)
    10. lp → LpService - Learning Paths (lp:)
    11. submissions → SubmissionsCoreService - File processing + journals
    12. life_path → AnalyticsLifePathService - Life goal alignment
    13. analytics → AnalyticsService - Statistical aggregation

THE 4 CROSS-CUTTING SYSTEMS
---------------------------

**Foundation & Infrastructure:**
    1. user_context → UserContextBuilder - ~240 fields cross-domain state
    2. search → SearchOperations - Unified search across domains
    3. askesis → AskesisService - Life context synthesis
    4. messaging → Conversation - Turn-based chat interface

ARCHITECTURE PATTERNS
---------------------

Service Composition:
    - All services created in compose_services()
    - Protocol-based dependencies (TasksOperations, etc.)
    - UniversalNeo4jBackend[T] for all entity persistence
    - Result[T] pattern for error handling

Design Principles:
    - Constructor injection everywhere
    - Clear protocols/ABCs for ports
    - Single bootstrap/wiring function
    - Easy testing with protocol implementations
    - Clean async lifecycle management
    - **GRACEFUL DEGRADATION**: Core services required, AI services optional

Production Philosophy:
    - Core services (Neo4j, Deepgram) are REQUIRED - fail fast if missing
    - AI services (OpenAI) are OPTIONAL - app works with basic features only
    - Clear error messages for missing configuration
    - Services warn when AI unavailable but continue functioning

INFRASTRUCTURE SERVICES
-----------------------

**Currently Active (Required):**
    - Neo4j ✅ Graph database (runs from /infra) - REQUIRED
    - Deepgram API ✅ Audio transcription - REQUIRED

**Optional AI Services:**
    - OpenAI API 🟡 AI/LLM features and embeddings - OPTIONAL (graceful degradation)

**Future Services (Pre-wired but Disabled):**
    - Redis 🟡 Distributed caching (in-memory cache currently used)
    - Ollama 🟡 Local LLM inference (OpenAI API currently used)
    - RabbitMQ/Kafka 🟡 Message queue (in-memory event bus currently used)
    - Prometheus 🟡 Metrics (manual monitoring currently used)
    - Grafana 🟡 Dashboards (manual monitoring currently used)
    - Nginx 🟡 Reverse proxy (direct access currently used)

See: /FUTURE_SERVICES.md for detailed explanation of why these services
     are pre-wired but disabled, and when to enable them.

Configuration for future services exists in:
    - core/config/unified_config.py (CacheConfig, MessageQueueConfig)
    - docker-compose.production.yml (Service definitions)

They are intentionally disabled to reduce operational overhead during
development. Enable when production requirements demand them.

See Also:
    /core/models/shared_enums.py - Domain enum definitions
    /core/ports/domain_protocols.py - Service interfaces
    /adapters/persistence/neo4j/universal_backend.py - Generic backend
    /FUTURE_SERVICES.md - Pre-wired infrastructure services explanation
"""

__version__ = "4.0"  # Entity type + cross-cutting system architecture


import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.constants import MasteryLevel
from core.models.enums.neo_labels import NeoLabel

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.config.intelligence_tier import IntelligenceTier
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics
    from core.ports.service_protocols import LateralRelationshipOperations
    from core.services.adaptive_lp.adaptive_lp_cross_domain_service import (
        AdaptiveLpCrossDomainService,
    )
    from core.services.analytics_service import AnalyticsService
    from core.services.article_service import ArticleService
    from core.services.askesis_ai_service import AskesisAIService
    from core.services.background.embedding_worker import EmbeddingBackgroundWorker
    from core.services.background.progress_feedback_worker import ProgressFeedbackWorker
    from core.services.calendar_optimization_service import CalendarOptimizationService

    # Facade services — concrete class IS the contract (no parallel protocol needed)
    from core.services.choices_service import ChoicesService
    from core.services.content_enrichment_service import ContentEnrichmentService
    from core.services.context_aware_ai_service import ContextAwareAIService
    from core.services.cross_domain_queries import CrossDomainQueries
    from core.services.events_service import EventsService
    from core.services.feedback.activity_report_service import ActivityReportService
    from core.services.feedback.progress_feedback_generator import ProgressFeedbackGenerator
    from core.services.feedback.progress_schedule_service import ProgressScheduleService
    from core.services.feedback.review_queue_service import ReviewQueueService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.insight.insight_store import InsightStore
    from core.services.jupyter_neo4j_sync import JupyterNeo4jSync
    from core.services.ku_service import KuService
    from core.services.lp_service import LpService
    from core.services.ls_service import LsService
    from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService
    from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
    from core.services.notifications.notification_service import NotificationService
    from core.services.performance_optimization_service import PerformanceOptimizationService
    from core.services.principles_service import PrinciplesService
    from core.services.submissions.journal_output_generator import JournalOutputGenerator
    from core.services.tasks_service import TasksService
    from core.services.transcription.transcription_service import TranscriptionService
    from core.services.user.intelligence.factory import (
        UserContextIntelligenceFactory,
    )
    from core.services.user_progress_service import UserProgressService
    from core.services.user_relationship_service import UserRelationshipService

from core.ports import (
    AskesisCoreOperations,
    AskesisOperations,
    AsyncCloseable,
    CalendarServiceOperations,
    Closeable,
    CrossDomainAnalyticsOperations,
    # Infrastructure
    EventBusOperations,
    ExerciseOperations,
    # Submission + SubmissionFeedback protocols
    FeedbackOperations,
    FinancesOperations,
    GoalTaskGeneratorOperations,
    GraphAuthOperations,
    GroupOperations,
    HabitEventSchedulerOperations,
    IngestionOperations,
    IntelligenceOperations,
    # NOTE: LearningOperations DELETED January 2026 - was dead code (type hint wrong)
    # NOTE: LearningPathsOperations DELETED January 2026 - replaced by LpOperations
    # NOTE: JournalsOperations DELETED February 2026 - Journal merged into Reports
    # NOTE: ChoicesOperations, EventsOperations, GoalsOperations, HabitsOperations,
    #       ArticleOperations, LpOperations, LsOperations, PrinciplesOperations, TasksOperations
    #       moved to TYPE_CHECKING block — facade services use concrete types (March 2026)
    LifePathOperations,
    QueryExecutor,
    SearchOperations,
    SharingOperations,
    SubmissionOperations,
    SubmissionProcessingOperations,
    SubmissionSearchOperations,
    SystemServiceOperations,
    TeacherReviewOperations,
    UserContextOperations,
    UserOperations,
    VisualizationOperations,
    ZPDOperations,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.bootstrap")


# ============================================================================
# SERVICES CONTAINER (Simple Data Structure)
# ============================================================================


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
    finance: FinancesOperations | None = None

    # ========================================================================
    # CURRICULUM DOMAINS (3) - KU, LS, LP
    # ========================================================================
    article: "ArticleService | None" = None  # ArticleService (teaching compositions)
    ku: "KuService | None" = None  # KuService (atomic knowledge units)
    # adaptive_sel removed — absorbed into ArticleService.adaptive (February 2026)
    cross_domain: "AdaptiveLpCrossDomainService | None" = None

    # Content services
    content_enrichment: "ContentEnrichmentService | None" = None
    transcription: "TranscriptionService | None" = None

    # Reports feedback services (LLM-based processing)
    feedback: FeedbackOperations | None = None  # FeedbackService - LLM feedback on report content
    exercises: ExerciseOperations | None = (
        None  # ExerciseService - Reusable LLM instruction templates
    )

    # Journal processing services
    journal_generator: "JournalOutputGenerator | None" = (
        None  # JournalOutputGenerator - je_output formatting and disk storage
    )

    # Submission pipeline services
    submissions: SubmissionOperations | None = (
        None  # SubmissionsService - File upload and submission content management
    )
    submissions_core: SubmissionOperations | None = (
        None  # SubmissionsCoreService - Content management (categories, tags, bulk operations)
    )
    sharing: SharingOperations | None = (
        None  # UnifiedSharingService - Cross-domain sharing and visibility control
    )
    submissions_processor: SubmissionProcessingOperations | None = (
        None  # SubmissionsProcessingService - Orchestrates processing (LLM enrichment, transcription)
    )

    # Submission search service (unified query interface)
    submissions_search: SubmissionSearchOperations | None = (
        None  # SubmissionsSearchService - Query all submission types (journals, essays, projects, etc.)
    )

    # ========================================================================
    # GROUP & TEACHING (ADR-040) - Teacher assignment workflow
    # ========================================================================
    group_service: GroupOperations | None = None  # GroupService - CRUD + membership for groups
    teacher_review: TeacherReviewOperations | None = (
        None  # TeacherReviewService - review queue + feedback
    )
    notification_service: "NotificationService | None" = (
        None  # NotificationService - in-app notifications
    )

    # System services
    # Note: sync field REMOVED (January 2026) - use unified_ingestion instead
    # Note: events moved to Activity Domains section above
    calendar: CalendarServiceOperations | None = (
        None  # CalendarService - unified calendar aggregation
    )
    system_service: SystemServiceOperations | None = (
        None  # SystemService - health checks and system monitoring
    )
    visualization: VisualizationOperations | None = (
        None  # VisualizationService - Chart.js/Vis.js/Gantt adapters
    )

    # User management (fundamental)
    user_service: UserOperations | None = None  # UserService - user profile management
    user_relationships: "UserRelationshipService | None" = None
    graph_auth: GraphAuthOperations | None = None  # GraphAuthService - graph-native authentication
    context_service: UserContextOperations | None = (
        None  # UserContextService - context-aware intelligence (NEW: 2025-11-18)
    )
    context_intelligence: "UserContextIntelligenceFactory | None" = None

    # Consolidated Learning Services (V4)
    user_progress: "UserProgressService | None" = None
    # Note: unified_progress DELETED (January 2026) - use user_progress or UserContextBuilder
    lp: "LpService | None" = None  # LpService - All path management
    ls: "LsService | None" = (
        None  # LsService - Dedicated learning step management (NEW: October 24, 2025)
    )
    learning_intelligence: IntelligenceOperations | None = (
        None  # LpIntelligenceService - analysis and recommendations
    )
    # ZPD service — Zone of Proximal Development (March 2026)
    # Created when INTELLIGENCE_TIER=FULL. None when CORE or curriculum graph < 3 KUs.
    # See: core/services/zpd/zpd_service.py, docs/roadmap/zpd-service-deferred.md
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

    # Advanced services
    calendar_optimization: "CalendarOptimizationService | None" = None
    jupyter_sync: "JupyterNeo4jSync | None" = None
    performance_optimization: "PerformanceOptimizationService | None" = None

    # Cross-cutting AI services (require LLM/embeddings - ADR-030: Two-Tier Intelligence Design)
    askesis_ai: "AskesisAIService | None" = None
    context_aware_ai: "ContextAwareAIService | None" = None

    # Infrastructure - Neo4j driver and query executor
    neo4j_driver: "AsyncDriver | None" = None
    query_executor: "QueryExecutor | None" = None

    # GenAI services (Neo4j native embeddings and vector search - January 2026)
    embeddings_service: "Neo4jGenAIEmbeddingsService | None" = None
    vector_search_service: "Neo4jVectorSearchService | None" = None

    # Background workers (January 2026)
    embedding_worker: "EmbeddingBackgroundWorker | None" = None
    progress_feedback_worker: "ProgressFeedbackWorker | None" = None

    # Progress report generation (February 2026)
    progress_feedback_generator: "ProgressFeedbackGenerator | None" = None
    progress_schedule: "ProgressScheduleService | None" = None

    # Activity report + review queue (March 2026 refactor: ActivityReviewService split)
    activity_report: "ActivityReportService | None" = None
    review_queue: "ReviewQueueService | None" = None

    # ========================================================================
    # LATERAL RELATIONSHIP SERVICES (January 2026) - Core Graph Architecture
    # ========================================================================
    lateral: "LateralRelationshipOperations | None" = None

    # Cross-domain graph queries (multi-hop: Tasks↔KU, Habits↔Goals, Events↔KU, Finance↔Goals)
    cross_domain_queries: "CrossDomainQueries | None" = None

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
                elif isinstance(adapter, Closeable):
                    adapter.close()
                logger.info("Graph adapter closed")
            except Exception as e:
                logger.warning(f"Error closing graph adapter: {e}")

        # Close event bus with detailed logging
        if self.event_bus:
            bus = self.event_bus
            self.event_bus = None  # Clear first to prevent double-close
            try:
                logger.info("Closing event bus...")
                if isinstance(bus, AsyncCloseable):
                    await bus.close()
                elif isinstance(bus, Closeable):
                    bus.close()
                logger.info("Event bus closed")
            except Exception as e:
                logger.warning(f"Error closing event bus: {e}")

        # Close individual services if they have cleanup methods
        services_to_close = [
            ("tasks", self.tasks),
            ("events", self.events),
            ("finance", self.finance),
            ("content_enrichment", self.content_enrichment),
            ("habits", self.habits),
            ("transcription", self.transcription),
            ("performance_optimization", self.performance_optimization),
            # Note: sync was removed (January 2026) - use unified_ingestion instead
        ]

        for service_name, service in services_to_close:
            if service:
                try:
                    if isinstance(service, AsyncCloseable):
                        logger.info(f"Closing {service_name}...")
                        await service.close()
                        logger.info(f"{service_name} closed")
                    elif isinstance(service, Closeable):
                        logger.info(f"Closing {service_name}...")
                        service.close()
                        logger.info(f"{service_name} closed")
                except Exception as e:
                    logger.warning(f"Error closing {service_name}: {e}")

        logger.info("✅ Service container cleanup complete")


# ============================================================================
# HELPER FUNCTIONS - Service Creation
# ============================================================================


def _create_core_services(
    tasks_backend: Any,
    events_backend: Any,
    finance_backend: Any,
    invoice_backend: Any,
    habits_backend: Any,
    habit_completions_backend: Any,
    transcription_backend: Any,
    user_service: Any,
    deepgram_api_key: str,  # REQUIRED for audio transcription (fail-fast)
    event_bus: Any = None,
    graph_intelligence=None,
    ku_inference_service=None,
    analytics_engine=None,
    ku_generation_service=None,
) -> dict[str, Any]:
    """Create core productivity services.

    Args:
        tasks_backend: UniversalNeo4jBackend[Task] (label=NeoLabel.TASK),
        events_backend: UniversalNeo4jBackend[Event] (label=NeoLabel.EVENT),
        finance_backend: UniversalNeo4jBackend[ExpensePure],
        invoice_backend: UniversalNeo4jBackend[InvoicePure],
        habits_backend: UniversalNeo4jBackend[Habit],
        habit_completions_backend: UniversalNeo4jBackend[HabitCompletion],
        transcription_backend: UniversalNeo4jBackend[Transcription],
        user_service: UserService for context operations (REQUIRED),
        event_bus: Event bus for publishing domain events (optional),
        graph_intelligence: GraphIntelligenceService for -4 queries (optional),
        ku_inference_service: EntityInferenceService for knowledge inference (optional),
        analytics_engine: AnalyticsEngine for advanced analytics (optional),
        ku_generation_service: InsightGenerationService for knowledge generation (optional),
        deepgram_api_key: Deepgram API key for audio transcription (REQUIRED)
    """
    from adapters.external.deepgram import DeepgramAdapter
    from core.services.events_service import EventsService
    from core.services.finance_service import FinanceService
    from core.services.habits_service import HabitsService
    from core.services.tasks_service import TasksService
    from core.services.transcription import TranscriptionService

    # Create DeepgramAdapter (REQUIRED - fail-fast if key missing)
    # 120s timeout for large audio files (up to ~10MB / 10 minutes of audio)
    deepgram_adapter = DeepgramAdapter(deepgram_api_key, timeout=120.0)

    return {
        "tasks": TasksService(
            backend=tasks_backend,
            ku_inference_service=ku_inference_service,
            analytics_engine=analytics_engine,
            ku_generation_service=ku_generation_service,
            graph_intelligence_service=graph_intelligence,
            event_bus=event_bus,  # Event-driven architecture
        ),
        "events": EventsService(
            backend=events_backend,
            graph_intelligence_service=graph_intelligence,  # Required for relationship service
            event_bus=event_bus,  # Event-driven architecture
        ),
        "finance": FinanceService(
            backend=finance_backend,
            event_bus=event_bus,  # Event-driven architecture
            invoice_backend=invoice_backend,  # Invoice management
        ),
        "habits": HabitsService(
            backend=habits_backend,
            graph_intelligence_service=graph_intelligence,  # REQUIRED for relationship service
            completions_backend=habit_completions_backend,  # REQUIRED - fail-fast
            event_bus=event_bus,  # Event-driven architecture
        ),
        "transcription": TranscriptionService(
            backend=transcription_backend,
            deepgram_adapter=deepgram_adapter,
            event_bus=event_bus,
        ),
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


def _create_learning_services(
    driver: "AsyncDriver",
    neo4j_adapter: Any,
    progress_backend: Any,
    knowledge_backend: Any,
    atomic_ku_backend: Any,  # KuBackend for atomic Ku entities
    content_adapter: Any,  # ContentOperations protocol (Neo4jContentAdapter),
    chunking_service: Any,
    user_service: Any,
    graph_intelligence: Any,
    llm_service: Any,  # LLMService for RAG generation (None when CORE tier)
    _tasks_service: Any = None,  # Placeholder: TasksService for entity extraction
    _habits_service: Any = None,  # Placeholder: HabitsService for entity extraction
    _goals_service: Any = None,  # Placeholder: GoalsService for entity extraction
    _events_service: Any = None,  # Placeholder: EventsService for entity extraction
    event_bus: Any = None,
    prometheus_metrics: "PrometheusMetrics | None" = None,
    query_executor: Any = None,
) -> dict[str, Any]:
    """Create all learning-related services using 100% dynamic backends."""
    from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
    from core.models.curriculum.learning_path import LearningPath
    from core.models.curriculum.learning_step import LearningStep
    from core.services.article_service import ArticleService
    from core.services.entity_retrieval import EntityRetrieval
    from core.services.lp_service import LpService  # Intelligence created internally
    from core.services.ls_service import LsService
    from core.services.query_builder import QueryBuilder
    from core.services.schema_service import Neo4jSchemaService

    # Note: UnifiedProgressService DELETED (January 2026) - violates fail-fast
    from core.services.user_progress_service import UserProgressService

    # Create Neo4j GenAI services (January 2026 - Neo4j GenAI Plugin Integration)
    # These services use Neo4j's native GenAI plugin for embeddings and vector search
    # API keys configured at database level (AuraDB console)
    # This is THE ONLY embeddings service - OpenAIEmbeddingsService removed (January 2026)
    # Gated by intelligence tier (ADR-043): CORE skips entirely, FULL creates normally
    embeddings_service = None
    vector_search_service = None

    from core.config.intelligence_tier import IntelligenceTier

    tier = IntelligenceTier.from_env()

    if not tier.ai_enabled:
        logger.info("⏭️  GenAI services skipped (intelligence tier: CORE)")
    else:
        try:
            from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService
            from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

            # Create GenAI embeddings service (uses ai.text.embed())
            embeddings_service = Neo4jGenAIEmbeddingsService(
                executor=query_executor,
                prometheus_metrics=prometheus_metrics,  # Track OpenAI calls
            )
            logger.info(
                "✅ Neo4j GenAI embeddings service created (with Prometheus instrumentation)"
            )

            # Create vector search service (uses db.index.vector.queryNodes())
            vector_search_service = Neo4jVectorSearchService(query_executor, embeddings_service)
            logger.info("✅ Neo4j vector search service created")

        except Exception as e:
            logger.warning(f"Failed to initialize Neo4j GenAI services: {e}")
            logger.warning("   Vector search will not be available - using keyword search fallback")
            embeddings_service = None
            vector_search_service = None

    # NOTE: LpIntelligenceService now created internally by LpService (January 2026)
    # See LpService.__init__ for intelligence creation pattern (unified with other domains)

    # Create query builder
    schema_service = Neo4jSchemaService(driver)
    unified_query_builder = QueryBuilder(schema_service)

    # Create knowledge service using dynamic backends with REQUIRED query_builder
    # January 2026: ArticleIntelligenceService created internally, no longer passed in
    # January 2026 - GenAI Integration: Pass vector search and embeddings services
    ku_service = ArticleService(
        repo=knowledge_backend,
        content_repo=content_adapter,  # Neo4jContentAdapter implements ContentOperations protocol
        neo4j_adapter=neo4j_adapter,
        chunking_service=chunking_service,
        graph_intelligence_service=graph_intelligence,
        query_builder=unified_query_builder,  # QueryBuilder is now REQUIRED
        event_bus=event_bus,  # Event-driven architecture
        # executor removed: ArticleOrganizationService now uses backend directly
        user_service=user_service,  # January 2026: KU-Activity Integration
        vector_search_service=vector_search_service,  # January 2026: GenAI vector search
        embeddings_service=embeddings_service,  # January 2026: GenAI embeddings (THE ONLY service)
    )

    # Create atomic Ku service (lightweight ontology/reference nodes)
    from core.services.ku.ku_core_service import KuCoreService
    from core.services.ku.ku_search_service import KuSearchService
    from core.services.ku_service import KuService

    ku_core = KuCoreService(backend=atomic_ku_backend)
    ku_search = KuSearchService(backend=atomic_ku_backend)
    atomic_ku_service = KuService(core=ku_core, search=ku_search, backend=atomic_ku_backend)

    # Create progress services
    user_progress = UserProgressService(query_executor)
    # Note: unified_progress DELETED (January 2026) - use user_progress or UserContextBuilder

    # Create learning step service (LS operations)
    # January 2026: graph_intel now REQUIRED for unified Curriculum architecture (ADR-030)
    # Backend created here (composition root) — core services never import adapters
    ls_backend = UniversalNeo4jBackend[LearningStep](
        driver, NeoLabel.LEARNING_STEP, LearningStep, base_label=NeoLabel.ENTITY
    )
    ls_service = LsService(
        backend=ls_backend,
        executor=query_executor,
        graph_intel=graph_intelligence,
        event_bus=event_bus,
    )

    # Create path service (LP operations - delegates LS operations to LsService)
    # January 2026: Intelligence created internally (unified with other domains)
    # Backend created here (composition root) — core services never import adapters
    from adapters.persistence.neo4j.domain_backends import LpBackend

    lp_backend = LpBackend(driver, NeoLabel.LEARNING_PATH, LearningPath, base_label=NeoLabel.ENTITY)
    learning_paths = LpService(
        backend=lp_backend,
        executor=query_executor,
        ls_service=ls_service,  # Delegate LS operations to LsService
        ku_service=ku_service,
        progress_service=user_progress,
        graph_intelligence_service=graph_intelligence,  # 4 graph queries (REQUIRED)
        event_bus=event_bus,  # Event-driven architecture
        progress_backend=progress_backend,
        user_service=user_service,
    )

    # Create retrieval service (embeddings_service is OPTIONAL - graceful degradation)
    ku_retrieval = EntityRetrieval(
        knowledge_repo=knowledge_backend,
        embeddings_service=embeddings_service,  # Can be None - will use keyword search fallback
        unified_query_builder=unified_query_builder,
        user_progress_service=user_progress,
        chunking_service=chunking_service,
    )

    # Adaptive SEL removed — now ArticleService.adaptive sub-service (February 2026)

    # NOTE: Askesis creation MOVED to compose_services() (January 2026)
    # This allows intelligence_factory to be passed at construction time (not post-wired)
    # Askesis needs: learning_paths.intelligence, graph_intelligence, user_service, llm_service,
    # embeddings_service, ku_service, tasks/goals/habits/events services

    # Create cross-domain service (circular import resolved via adaptive_lp_models.py)
    from core.services.adaptive_lp.adaptive_lp_cross_domain_service import (
        AdaptiveLpCrossDomainService,
    )

    cross_domain_service = AdaptiveLpCrossDomainService(MasteryLevel.BEGINNER)

    return {
        "learning_intelligence": learning_paths.intelligence,  # Access via facade
        "article_service": ku_service,
        "atomic_ku_service": atomic_ku_service,
        "user_progress": user_progress,
        # unified_progress DELETED (January 2026)
        "learning_paths": learning_paths,
        "learning_steps": ls_service,  # NEW: Dedicated LS service
        "ku_retrieval": ku_retrieval,
        # NOTE: "askesis" MOVED to compose_services() (January 2026)
        "cross_domain": cross_domain_service,
        "embeddings_service": embeddings_service,  # For intelligence services
        "vector_search_service": vector_search_service,  # For semantic search
        # Components needed for Askesis creation in compose_services()
        "graph_intelligence": graph_intelligence,
        "llm_service": llm_service,
    }


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
        ),
        "events": EventsService(
            backend=events_backend,
            graph_intelligence_service=graph_intelligence,
            event_bus=event_bus,
        ),
        "habits": HabitsService(
            backend=habits_backend,
            graph_intelligence_service=graph_intelligence,
            completions_backend=habit_completions_backend,  # REQUIRED - fail-fast
            event_bus=event_bus,
            insight_store=insight_store,
        ),
        "goals": GoalsService(
            backend=goals_backend,
            graph_intelligence_service=graph_intelligence,
            event_bus=event_bus,
        ),
        "choices": ChoicesService(
            backend=choices_backend,
            graph_intelligence_service=graph_intelligence,
            event_bus=event_bus,
            insight_store=insight_store,
        ),
        "principles": PrinciplesService(
            backend=principles_backend,
            graph_intelligence_service=graph_intelligence,
            goals_backend=goals_backend,
            habits_backend=habits_backend,
            reflection_backend=reflection_backend,
            event_bus=event_bus,
            insight_store=insight_store,
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


# ============================================================================
# BOOTSTRAP FUNCTION (The Single Wiring Point)
# ============================================================================


async def compose_services(
    neo4j_adapter: Any,
    event_bus: EventBusOperations = None,
    config: Any = None,
    prometheus_metrics: "PrometheusMetrics | None" = None,
    metrics_cache: Any = None,
) -> Result[tuple[Services, Any, Any]]:
    """
    Bootstrap function: creates all services with their dependencies.

    This is THE SINGLE PLACE where service wiring happens.
    No magic, no reflection, just explicit constructor injection.

    Following "Result inside, exception at boundary" pattern.

    **FAIL-FAST DESIGN**: All dependencies are REQUIRED. Service composition
    will fail immediately if any required API key or service is unavailable.

    Args:
        neo4j_adapter: Database adapter (satisfies GraphPort) - REQUIRED,
        event_bus: Event bus adapter (optional, will create default if None),
        config: UnifiedConfig for accessing configuration (optional, will load if None)
        prometheus_metrics: PrometheusMetrics for instrumentation (optional — January 2026)
        metrics_cache: MetricsCache for performance tracking (optional)

    Returns:
        Result[tuple[Services, knowledge_backend]]: Success with wired services or failure
        with detailed error. Returns tuple of (Services, KnowledgeUniversalBackend) for
        GraphQL injection. SearchRouter is available via services.search_router.

    Raises:
        ValueError: If any required dependency is missing
    """
    logger.info("🔧 Composing service dependencies (FAIL-FAST mode)...")

    # Load config if not provided
    if config is None:
        from core.config import get_settings

        config = get_settings()

    # Determine intelligence tier (ADR-043)
    from core.config.intelligence_tier import IntelligenceTier

    tier = IntelligenceTier.from_env()
    if tier.ai_enabled:
        logger.info("🧠 Intelligence tier: FULL (analytics + AI services)")
    else:
        logger.info("🧠 Intelligence tier: CORE (analytics only — no API costs)")

    try:
        # ========================================================================
        # CREATE EVENT BUS (Event-Driven Architecture)
        # ========================================================================

        # Create event bus if not provided
        if not event_bus:
            from adapters.infrastructure.event_bus import InMemoryEventBus

            event_bus = InMemoryEventBus()
            logger.info("✅ InMemoryEventBus created (event-driven architecture enabled)")
        else:
            logger.info("✅ Using provided event bus")
        # ========================================================================
        # VALIDATE ALL REQUIRED DEPENDENCIES (FAIL-FAST)
        # ========================================================================

        from core.config.credential_store import get_credential

        # Validate Neo4j database connection
        try:
            driver = neo4j_adapter.get_driver()
        except (AttributeError, RuntimeError) as e:
            logger.error(f"❌ Neo4j driver unavailable: {e}")
            raise ValueError(
                "Neo4j database connection is REQUIRED. "
                "Ensure NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD are configured."
            ) from e

        if not driver:
            logger.error("❌ Neo4j driver is None")
            raise ValueError(
                "Cannot initialize services without Neo4j driver. "
                "Check your Neo4j connection configuration."
            )

        logger.info("✅ Neo4j driver validated")

        # Create QueryExecutor adapter — THE single path for raw Cypher in core services
        from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

        query_executor = Neo4jQueryExecutor(driver)
        logger.info("✅ QueryExecutor created (hexagonal architecture port)")

        # CrossDomainQueries — multi-hop graph queries spanning Tasks↔KU, Habits↔Goals, etc.
        from core.services.cross_domain_queries import CrossDomainQueries

        cross_domain_queries_svc = CrossDomainQueries(query_executor)
        logger.info("✅ CrossDomainQueries created")

        # ========================================================================
        # SYNC AUTH INDEXES AND CLEANUP (Startup Tasks)
        # ========================================================================
        from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager

        schema_manager = Neo4jSchemaManager(driver)

        # Create auth-specific indexes (rate limiting, session lookup, email uniqueness)
        auth_index_result = await schema_manager.sync_auth_indexes()
        if auth_index_result.is_ok:
            created = auth_index_result.value.get("created", [])
            logger.info(f"✅ Auth indexes synced: {', '.join(created) if created else 'all exist'}")
        else:
            logger.warning(f"⚠️ Auth index sync had issues: {auth_index_result.error}")

        # Cleanup expired sessions and reset tokens (daily maintenance at startup)
        from adapters.persistence.neo4j.session_backend import SessionBackend

        session_backend = SessionBackend(driver)
        cleanup_sessions = await session_backend.cleanup_expired_sessions()
        cleanup_tokens = await session_backend.cleanup_expired_tokens()

        if cleanup_sessions.is_ok and cleanup_tokens.is_ok:
            sessions_cleaned = cleanup_sessions.value
            tokens_cleaned = cleanup_tokens.value
            if sessions_cleaned > 0 or tokens_cleaned > 0:
                logger.info(
                    f"✅ Cleanup: {sessions_cleaned} expired sessions, {tokens_cleaned} expired tokens"
                )
            else:
                logger.debug("✅ Cleanup: no expired sessions or tokens")
        else:
            logger.warning("⚠️ Cleanup had issues - continuing startup")

        # Validate API keys (GRACEFUL DEGRADATION for optional features)
        # Required keys: DEEPGRAM (audio transcription)
        # Optional keys: OPENAI (AI features - app works without them)
        required_keys = {
            "DEEPGRAM_API_KEY": "Deepgram API (required for audio transcription)",
        }

        recommended_keys = {
            "OPENAI_API_KEY": "OpenAI API (optional - enables embeddings, semantic search, and AI features)",
        }

        # Check required keys (FAIL-FAST)
        missing_required = []
        for key_name, description in required_keys.items():
            key_value = get_credential(key_name, fallback_to_env=True)
            if not key_value:
                missing_required.append(f"  - {key_name}: {description}")
                logger.error(f"❌ Missing required API key: {key_name}")
            else:
                logger.info(f"✅ {key_name} validated")

        if missing_required:
            error_msg = (
                "SKUEL requires these API keys to be configured. Missing keys:\n"
                + "\n".join(missing_required)
                + "\n\nSet these environment variables or add them to your credential store."
            )
            logger.error("❌ Service composition failed - missing required API keys")
            raise ValueError(error_msg)

        # Check recommended keys (WARN only, don't fail)
        for key_name, description in recommended_keys.items():
            key_value = get_credential(key_name, fallback_to_env=True)
            if not key_value or key_value in ["your-openai-api-key-here", "", "sk-"]:
                logger.warning(f"⚠️ {key_name} not configured: {description}")
                logger.warning("   App will run with basic features only")
            else:
                logger.info(f"✅ {key_name} validated")

        logger.info("✅ Required API keys validated")

        # ========================================================================
        # CREATE SERVICES (All dependencies are guaranteed available)
        # ========================================================================

        # 100% Dynamic Pattern: Instantiate UniversalNeo4jBackend directly at point of use
        # "The plant (models) grows on the lattice (UniversalNeo4jBackend)"
        from adapters.persistence.neo4j.domain_backends import (
            ArticleBackend,
            ChoicesBackend,
            EventsBackend,
            GoalsBackend,
            HabitsBackend,
            KuBackend,
            PrinciplesBackend,
            SubmissionsBackend,
            TasksBackend,
        )
        from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
        from core.models.askesis.askesis import Askesis
        from core.models.event.event import Event

        # NOTE: Choice import REMOVED (February 2026) - Choice uses Entity model
        # Choice entities are Entity nodes with entity_type="choice"
        # NOTE: Event import REMOVED (February 2026) - Event uses Entity model
        # Event entities are Entity nodes with entity_type="event"
        from core.models.finance.finance_pure import ExpensePure
        from core.models.finance.invoice import InvoicePure
        from core.models.goal.goal import Goal

        # NOTE: Goal import REMOVED (February 2026) - Goal uses Entity model
        # Goal entities are Entity nodes with entity_type="goal"
        from core.models.habit.completion import HabitCompletion
        from core.models.habit.habit import Habit

        # NOTE: MapOfContent import removed (January 2026) - MOC is Entity-based (emergent)
        # MOC is any Entity with ORGANIZES relationships, not a separate entity type
        from core.models.principle.reflection import PrincipleReflection
        from core.models.progress import UserProgress
        from core.models.task.task import Task
        from core.models.transcription.transcription import Transcription

        # Create backends directly (no wrapper) - makes lattice pattern visible
        # ACTIVITY DOMAINS - Use UniversalNeo4jBackend (requires DomainModelProtocol)
        # Domain-specific labels (NeoLabel.TASK, NeoLabel.GOAL, etc.) with
        # base_label=NeoLabel.ENTITY for multi-label CREATE: (n:Entity:Task)
        # (January 2026): Pass prometheus_metrics for database instrumentation
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
        # NOTE: journals_backend REMOVED (February 2026) - Journal uses Entity model
        # Journal entries are Entity nodes with entity_type="submission" and journal metadata
        transcription_backend = UniversalNeo4jBackend[Transcription](
            driver, NeoLabel.TRANSCRIPTION, Transcription, prometheus_metrics=prometheus_metrics
        )

        # IDENTITY/FOUNDATION - Use dedicated UserBackend (no DTO conversion lifecycle)
        # User is NOT an activity domain - it's the identity layer all domains reference
        # See: CLAUDE.md §2.11 Domain Architecture Categories
        from adapters.persistence.neo4j.user_backend import UserBackend
        from core.models.curriculum.article import Article

        users_backend = UserBackend(driver)
        knowledge_backend = ArticleBackend(
            driver,
            NeoLabel.ARTICLE,
            Article,
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
        from core.models.submissions.submission import Submission

        # NOTE: vectors_backend REMOVED (January 2026) - was unused dead code
        # submissions_backend uses :Entity label for cross-domain queries (submissions span 3 EntityTypes)
        # entity_class=Submission: base class for SUBMISSION, JOURNAL, FEEDBACK_REPORT
        # AI_FEEDBACK excluded: uses dedicated ai_feedback_backend (ActivityReport inherits UserOwnedEntity)
        submissions_backend = SubmissionsBackend(
            driver, NeoLabel.ENTITY, Submission, prometheus_metrics=prometheus_metrics
        )
        from core.models.feedback.activity_report import ActivityReport

        # Dedicated backend for ActivityReport (activity-level feedback — no file fields)
        ai_feedback_backend = UniversalNeo4jBackend[ActivityReport](
            driver,
            NeoLabel.ACTIVITY_REPORT,
            ActivityReport,
            base_label=NeoLabel.ENTITY,
            prometheus_metrics=prometheus_metrics,
        )
        askesis_backend = UniversalNeo4jBackend[Askesis](
            driver, NeoLabel.ASKESIS, Askesis, prometheus_metrics=prometheus_metrics
        )

        logger.info("✅ Domain backends created (100% dynamic pattern - direct instantiation)")

        # Create user service FIRST (foundation service with no dependencies)
        from core.services.user_service import create_user_service

        user_service = create_user_service(
            users_backend, query_executor, metrics_cache=metrics_cache
        )
        logger.info("✅ UserService created (foundation service)")

        # Ensure system user exists for infrastructure operations
        logger.info("Ensuring system user exists...")
        system_user_result = await user_service.ensure_system_user()
        if system_user_result.is_error:
            logger.warning(f"Failed to create system user: {system_user_result.error}")
        else:
            logger.info("✅ System user ready")

        # Create user relationship service (pinning, following, etc.)
        from core.services.user_relationship_service import UserRelationshipService

        user_relationships = UserRelationshipService(executor=query_executor)
        logger.info("✅ UserRelationshipService created (pinning, following)")

        # Create graph-native authentication service (January 2026)
        # Sessions stored in Neo4j with bcrypt password hashing
        from adapters.persistence.neo4j.session_backend import SessionBackend
        from core.auth.graph_auth import GraphAuthService

        session_backend = SessionBackend(driver)

        # Optional email service for password reset (March 2026)
        email_service = None
        resend_api_key = os.environ.get("RESEND_API_KEY")
        if resend_api_key:
            from adapters.outbound.email_service import ResendEmailService

            resend_from = os.environ.get("RESEND_FROM_EMAIL", "noreply@skuel.app")
            email_service = ResendEmailService(api_key=resend_api_key, from_email=resend_from)
            logger.info("✅ ResendEmailService created (password reset emails)")
        else:
            logger.warning("⚠️ RESEND_API_KEY not set — password reset emails disabled")

        app_url = os.environ.get("APP_URL", "http://localhost:8000")

        graph_auth = GraphAuthService(
            user_backend=users_backend,
            session_backend=session_backend,
            email_service=email_service,
            app_url=app_url,
        )
        logger.info("✅ GraphAuthService created (graph-native authentication)")

        # Create user context service (context-aware intelligence)
        # NOTE: UserContextBuilder now owns user resolution (Option A architecture, Nov 2025)
        # This eliminates repetitive user lookup in every service method.
        from core.services.user import UserContextBuilder, UserContextService

        context_builder = UserContextBuilder(query_executor, user_service=user_service)
        context_service = UserContextService(
            context_builder=context_builder,
            user_service=user_service,
            tasks_service=None,  # Will be wired after tasks service is created
        )
        logger.info("✅ UserContextService created (context-aware intelligence)")
        logger.info("   - UserContextBuilder owns user resolution (Option A architecture)")

        # Create graph intelligence (needed by tasks service)
        from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService

        graph_intelligence = GraphIntelligenceService(query_executor)
        logger.info("✅ GraphIntelligenceService created")

        # Create analytics services (needed by tasks service)
        from core.services.analytics_engine import AnalyticsEngine
        from core.services.entity_inference_service import EntityInferenceService
        from core.services.insight_generation_service import InsightGenerationService

        analytics_engine = AnalyticsEngine()
        ku_inference_service = EntityInferenceService()
        ku_generation_service = InsightGenerationService()
        logger.info("✅ Analytics and inference services created")

        # Create InsightStore
        from core.services.insight import InsightStore

        insight_store = InsightStore(query_executor)
        logger.info("✅ InsightStore created (event-driven insights)")

        # ========================================================================
        # ACTIVITY DOMAIN SERVICES (6) - Unified creation
        # ========================================================================
        activity_services = _create_activity_services(
            tasks_backend=tasks_backend,
            events_backend=events_backend,
            habits_backend=habits_backend,
            habit_completions_backend=habit_completions_backend,
            goals_backend=goals_backend,
            choices_backend=choices_backend,
            principles_backend=principles_backend,
            reflection_backend=reflection_backend,
            graph_intelligence=graph_intelligence,
            event_bus=event_bus,
            ku_inference_service=ku_inference_service,
            analytics_engine=analytics_engine,
            ku_generation_service=ku_generation_service,
            insight_store=insight_store,
        )
        logger.info("✅ Activity Domain services created (6 facades with embedded intelligence)")

        # Get Deepgram API key for transcription service
        from core.config.credential_store import get_credential

        deepgram_api_key = get_credential("DEEPGRAM_API_KEY", fallback_to_env=True)

        # Create core services (Finance, Transcription only - Activity Domains now in activity_services)
        core_services = _create_core_services(
            tasks_backend=tasks_backend,
            events_backend=events_backend,
            finance_backend=finance_backend,
            invoice_backend=invoice_backend,
            habits_backend=habits_backend,
            habit_completions_backend=habit_completions_backend,
            transcription_backend=transcription_backend,
            user_service=user_service,  # Pass user_service for context operations
            event_bus=event_bus,  # Event-driven architecture
            graph_intelligence=graph_intelligence,
            ku_inference_service=ku_inference_service,
            analytics_engine=analytics_engine,
            ku_generation_service=ku_generation_service,
            deepgram_api_key=deepgram_api_key,  # For audio transcription
        )
        logger.info("✅ Core services created (with event bus + Deepgram wiring)")

        # GRAPH-NATIVE: Wire analytics engine with TasksRelationshipService
        # tasks_service comes from activity_services (unified Activity Domain creation)
        tasks_service = activity_services["tasks"]
        analytics_engine.relationship_service = tasks_service.relationships
        logger.info("✅ AnalyticsEngine wired with TasksRelationshipService")

        # Wire tasks_service into context_service for context-aware operations
        context_service.tasks_service = tasks_service
        logger.info("✅ UserContextService wired with TasksService")

        # Note: TranscriptionService is already created in core_services with Deepgram wiring
        # Note: MarkdownSyncService DELETED (January 2026) - use UnifiedIngestionService

        # Create knowledge components using 100% dynamic backend pattern
        # IMPORTANT: chunking_service must be created BEFORE UnifiedIngestionService (January 2026)
        from adapters.persistence.neo4j.neo4j_connection import get_connection
        from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
        from core.services.entity_chunking_service import EntityChunkingService

        chunking_service = EntityChunkingService()
        logger.info("✅ EntityChunkingService created for automatic chunk generation")

        # Create UnifiedIngestionService (ADR-014: Merged MD + YAML ingestion)
        # January 2026 - Automatic Chunking: Pass chunking service for RAG-ready ingestion
        # January 2026 - GenAI Integration: Pass embeddings service for automatic embedding generation
        from core.services.ingestion import UnifiedIngestionService

        unified_ingestion = UnifiedIngestionService(
            driver=driver,
            executor=query_executor,
            embeddings_service=None,  # Optional - will be created later in learning_services
            chunking_service=chunking_service,  # Automatic chunk generation for KU entities
        )
        logger.info(
            "✅ Content services created (includes UnifiedIngestionService with automatic chunking)"
        )

        # Use Neo4jContentAdapter for ContentOperations protocol (store_content_with_chunks, get_chunks, etc.)
        connection = await get_connection()
        content_adapter = Neo4jContentAdapter(connection)

        # Create LLM service BEFORE learning services (OPTIONAL - enables AI features)
        # Gated by intelligence tier (ADR-043): CORE skips entirely
        llm_service = None
        if not tier.ai_enabled:
            logger.info("⏭️  LLM service skipped (intelligence tier: CORE)")
        else:
            from core.config.credential_store import get_credential
            from core.services.llm_service import LLMConfig, LLMProvider, LLMService

            try:
                openai_api_key = get_credential("OPENAI_API_KEY", fallback_to_env=True)
                # Check if key is valid (not placeholder/empty)
                if openai_api_key and openai_api_key not in ["your-openai-api-key-here", "", "sk-"]:
                    llm_config = LLMConfig(
                        provider=LLMProvider.OPENAI,
                        api_key=openai_api_key,
                        model_name="gpt-4",  # Use GPT-4 for high-quality RAG and intelligence insights
                    )
                    llm_service = LLMService(config=llm_config)
                    logger.info(
                        "✅ LLM service created (GPT-4 for RAG generation and intelligence services)"
                    )
                else:
                    logger.warning("⚠️ LLM service disabled - OPENAI_API_KEY not configured")
            except Exception as e:
                logger.error(f"Failed to initialize LLM service: {e}")
                logger.warning("⚠️ LLM service disabled - continuing with basic features")

        # Create learning services (graph_intelligence already created above)
        learning_services = _create_learning_services(
            driver=driver,
            neo4j_adapter=neo4j_adapter,
            progress_backend=progress_backend,
            knowledge_backend=knowledge_backend,
            atomic_ku_backend=ku_backend,
            content_adapter=content_adapter,
            chunking_service=chunking_service,
            user_service=user_service,
            graph_intelligence=graph_intelligence,
            llm_service=llm_service,  # Pass LLM service for askesis RAG
            _tasks_service=activity_services["tasks"],  # Placeholder - not yet implemented
            _habits_service=activity_services["habits"],  # Placeholder - not yet implemented
            _goals_service=activity_services["goals"],  # Placeholder - not yet implemented
            _events_service=activity_services["events"],  # Placeholder - not yet implemented
            event_bus=event_bus,  # Event-driven architecture
            prometheus_metrics=prometheus_metrics,  # Metrics instrumentation
            query_executor=query_executor,
        )
        logger.info("✅ Learning services created")

        # Extract embeddings and vector search services for use by intelligence services and SearchRouter
        embeddings_service = learning_services["embeddings_service"]
        vector_search_service = learning_services["vector_search_service"]

        # ========================================================================
        # CREATE BACKGROUND WORKERS (January 2026)
        # ========================================================================

        # Create embedding background worker (async embedding generation for all activity domains)
        # Worker processes EmbeddingRequested events in batches for zero-latency user experience
        embedding_worker = None
        if embeddings_service:
            try:
                from core.services.background.embedding_worker import EmbeddingBackgroundWorker

                embedding_worker = EmbeddingBackgroundWorker(
                    event_bus=event_bus,
                    embeddings_service=embeddings_service,
                    executor=query_executor,
                    config=config,
                    prometheus_metrics=prometheus_metrics,  # Real-time metrics exposure
                    batch_size=25,  # Process 25 entities per batch (cost-optimized)
                    batch_interval_seconds=30,  # Run every 30 seconds
                )
                logger.info("✅ Embedding background worker created (batch_size=25, interval=30s)")
                logger.info(
                    "   Worker will process embeddings for: Tasks, Goals, Habits, Events, Choices, Principles"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize embedding background worker: {e}")
                logger.warning("   Embeddings will only be generated during ingestion")
        else:
            logger.info("⏭️  Embedding background worker skipped (embeddings_service not available)")

        # ========================================================================
        # CREATE LATERAL RELATIONSHIP SERVICES (January 2026)
        # ========================================================================
        # Core lateral relationships infrastructure - foundational graph architecture
        # Enables explicit modeling of sibling, cousin, dependency, and semantic relationships
        # across all 8 hierarchical domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP)

        from core.services.lateral_relationships import LateralRelationshipService

        # Create core lateral relationship service (domain-agnostic)
        # Ownership verification happens at route level via domain_service param
        lateral_service = LateralRelationshipService(driver)
        logger.info("✅ LateralRelationshipService created (9 domains, ownership at route level)")

        # Create Askesis core service (CRUD operations for AI assistant instances)
        from core.services.askesis.askesis_core_service import AskesisCoreService

        askesis_core_service = AskesisCoreService(backend=askesis_backend)
        logger.info("✅ Askesis core service created (CRUD operations)")

        # NOTE: Askesis service now created in after intelligence_factory is available
        # This eliminates post-construction wiring (January 2026 architecture evolution)

        # Cross-cutting AI services (askesis_ai, context_aware_ai) created below
        # in the AI SERVICES section - they REQUIRE LLM/embeddings
        askesis_ai = None
        context_aware_ai = None

        # ========================================================================
        # AI SERVICES (Optional - ADR-030: Two-Tier Intelligence Design)
        # ========================================================================
        # Create AI services when LLM/embeddings are available
        # AI services are OPTIONAL - the app functions fully without them
        if llm_service and embeddings_service:
            from core.services.article.article_ai_service import ArticleAIService
            from core.services.askesis_ai_service import AskesisAIService
            from core.services.choices.choices_ai_service import ChoicesAIService
            from core.services.context_aware_ai_service import ContextAwareAIService
            from core.services.events.events_ai_service import EventsAIService
            from core.services.goals.goals_ai_service import GoalsAIService
            from core.services.habits.habits_ai_service import HabitsAIService
            from core.services.lp.lp_ai_service import LpAIService
            from core.services.ls.ls_ai_service import LsAIService
            from core.services.principles.principles_ai_service import PrinciplesAIService
            from core.services.tasks.tasks_ai_service import TasksAIService
            # NOTE: MocAIService removed (January 2026) - MOC is now KU-based

            # Create AI services for Activity Domains (6)
            tasks_ai = TasksAIService(
                backend=activity_services["tasks"].core.backend,
                llm_service=llm_service,
                embeddings_service=embeddings_service,
            )
            goals_ai = GoalsAIService(
                backend=activity_services["goals"].core.backend,
                llm_service=llm_service,
                embeddings_service=embeddings_service,
            )
            habits_ai = HabitsAIService(
                backend=activity_services["habits"].core.backend,
                llm_service=llm_service,
                embeddings_service=embeddings_service,
            )
            events_ai = EventsAIService(
                backend=activity_services["events"].core.backend,
                llm_service=llm_service,
                embeddings_service=embeddings_service,
            )
            choices_ai = ChoicesAIService(
                backend=activity_services["choices"].core.backend,
                llm_service=llm_service,
                embeddings_service=embeddings_service,
            )
            principles_ai = PrinciplesAIService(
                backend=activity_services["principles"].core.backend,
                llm_service=llm_service,
                embeddings_service=embeddings_service,
            )

            # Wire AI services into Activity Domain facades (post-construction)
            activity_services["tasks"].ai = tasks_ai
            activity_services["goals"].ai = goals_ai
            activity_services["habits"].ai = habits_ai
            activity_services["events"].ai = events_ai
            activity_services["choices"].ai = choices_ai
            activity_services["principles"].ai = principles_ai

            # Create AI services for Curriculum Domains (4)
            ku_ai = ArticleAIService(
                backend=learning_services["article_service"].core.backend,
                llm_service=llm_service,
                embeddings_service=embeddings_service,
            )
            ls_ai = LsAIService(
                backend=learning_services["learning_steps"].core.backend,
                llm_service=llm_service,
                embeddings_service=embeddings_service,
            )
            lp_ai = LpAIService(
                backend=learning_services["learning_paths"].core.backend,
                llm_service=llm_service,
                embeddings_service=embeddings_service,
            )
            # Wire AI services into Curriculum Domain facades (post-construction)
            learning_services["article_service"].ai = ku_ai
            learning_services["learning_steps"].ai = ls_ai
            learning_services["learning_paths"].ai = lp_ai

            # Create cross-cutting AI services (2)
            askesis_ai = AskesisAIService(
                backend=user_service,  # Uses UserService for user state
                llm_service=llm_service,
                embeddings_service=embeddings_service,
                graph_intelligence_service=graph_intelligence,
            )
            context_aware_ai = ContextAwareAIService(
                backend=user_service,  # Uses UserContextOperations
                llm_service=llm_service,
                embeddings_service=embeddings_service,
                graph_intelligence_service=graph_intelligence,
            )

            logger.info(
                "✅ AI services created and wired (12 services: 6 Activity + 4 Curriculum + 2 cross-cutting)"
            )
        else:
            logger.info("⚠️ AI services skipped (LLM or embeddings not available)")

        # Create calendar service
        from core.services.calendar_service import CalendarService

        calendar_service = CalendarService(
            tasks_service=activity_services["tasks"],
            events_service=activity_services["events"],
            habits_service=activity_services["habits"],
        )
        logger.info("✅ Calendar service created")

        # Create system service (health checks and monitoring)
        from core.services.system_service import SystemService

        system_service = SystemService()
        logger.info("✅ System service created (health checks enabled)")

        # Create visualization service (Chart.js/Vis.js/Gantt adapters)
        from core.services.visualization_service import VisualizationService

        visualization_service = VisualizationService()
        logger.info("✅ Visualization service created (Chart.js/Vis.js adapters)")

        # Create OpenAI service + content enrichment (gated by intelligence tier - ADR-043)
        from core.services.content_enrichment_service import ContentEnrichmentService

        ai_service = None
        if tier.ai_enabled:
            from core.config.credential_store import get_credential
            from core.services.ai_service import OpenAIService

            openai_api_key = get_credential("OPENAI_API_KEY", fallback_to_env=True)
            ai_service = OpenAIService(api_key=openai_api_key)
            logger.info("✅ OpenAI service created")
        else:
            logger.info("⏭️  OpenAI service skipped (intelligence tier: CORE)")

        content_enrichment = ContentEnrichmentService(
            backend=submissions_backend,  # February 2026: Uses Entity backend (domain-first model)
            transcription_service=core_services["transcription"],
            ai_service=ai_service,  # None in CORE tier — already handles None gracefully
            event_bus=event_bus,  # Event-driven architecture
        )
        logger.info("✅ Content enrichment service created")

        # Create Reports feedback and exercise services
        from adapters.persistence.neo4j.domain_backends import ExerciseBackend
        from core.models.curriculum.exercise import Exercise
        from core.services.exercises import ExerciseService
        from core.services.feedback import FeedbackService

        # FeedbackService: None in CORE tier — feedback generation requires AI
        feedback_service = None
        if ai_service:
            feedback_service = FeedbackService(
                openai_service=ai_service,
                anthropic_service=None,  # Only OpenAI configured for now
                executor=query_executor,  # Creates SUBMISSION_FEEDBACK entity + FEEDBACK_FOR relationship
                ku_interaction_service=learning_services[
                    "article_service"
                ].mastery,  # Closes mastery loop
            )

        exercise_backend = ExerciseBackend(
            driver=driver,
            label=NeoLabel.EXERCISE,
            entity_class=Exercise,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )

        exercise_service = ExerciseService(backend=exercise_backend)
        logger.info("✅ Reports feedback and exercise services created")

        # Create group service (ADR-040: Teacher Assignment Workflow)
        from core.models.group.group import Group
        from core.services.groups import GroupService

        group_backend = UniversalNeo4jBackend[Group](
            driver=driver,
            label=NeoLabel.GROUP,
            entity_class=Group,
            prometheus_metrics=prometheus_metrics,
        )

        group_service = GroupService(backend=group_backend, event_bus=event_bus)
        logger.info("✅ GroupService created (ADR-040)")

        # Create teacher review service (ADR-040: Teacher Assignment Workflow)
        from core.services.feedback.teacher_review_service import TeacherReviewService

        teacher_review_service = TeacherReviewService(
            executor=query_executor,
            ku_interaction_service=learning_services["article_service"].mastery,
            event_bus=event_bus,
        )
        logger.info("✅ TeacherReviewService created (ADR-040)")

        # Create notification service
        from core.services.notifications.notification_service import NotificationService

        notification_service = NotificationService(executor=query_executor)
        logger.info("✅ NotificationService created")

        # Seed default transcript exercise (idempotent create/update)
        seed_result = await exercise_service.seed_default_project()
        if seed_result.is_ok:
            logger.info("Default transcript project loaded")
        else:
            logger.warning(f"Default transcript project: {seed_result.error}")

        # Create submissions submission and processing pipeline services
        from core.services.submissions import (
            SubmissionsCoreService,
            SubmissionsProcessingService,
            SubmissionsSearchService,
            SubmissionsService,
        )

        # Get storage path from environment (default: /tmp/skuel_submissions)
        storage_path = os.getenv("SKUEL_SUBMISSIONS_STORAGE", "/tmp/skuel_submissions")

        submissions_service = SubmissionsService(
            backend=submissions_backend, storage_path=storage_path, event_bus=event_bus
        )

        # Create sharing backend + service (cross-domain, queries :Entity nodes)
        from adapters.persistence.neo4j.domain_backends import SharingBackend
        from core.models.entity import Entity
        from core.services.sharing import UnifiedSharingService

        sharing_backend = SharingBackend(
            driver, NeoLabel.ENTITY, Entity, prometheus_metrics=prometheus_metrics
        )
        unified_sharing_service = UnifiedSharingService(backend=sharing_backend)

        # Create Submissions core service (content management: categories, tags, bulk operations)
        # February 2026: content_enrichment for handle_transcription_completed
        submissions_core_service = SubmissionsCoreService(
            backend=submissions_backend,
            event_bus=event_bus,
            sharing_service=unified_sharing_service,
            content_enrichment=content_enrichment,
        )

        # LIFEPATH SERVICE (Domain #14: The Destination)
        # "Everything flows toward the life path"
        # Vision capture → Alignment measurement → Recommendations
        # =====================================================================
        from core.services.lifepath import LifePathService

        lifepath_service = LifePathService(
            executor=query_executor,
            lp_service=learning_services["learning_paths"],
            ku_service=learning_services["article_service"],
            user_service=user_service,
            llm_service=llm_service,
        )
        logger.info("✅ LifePath service created (Vision→Action bridge)")

        # Create report activity extractor (DSL integration for journal → entity extraction)
        from core.services.dsl import ActivityExtractorService

        activity_extractor = ActivityExtractorService(
            # Activity Domains (6) - access .core for CRUD operations
            tasks_service=activity_services["tasks"].core,
            habits_service=activity_services["habits"].core,
            goals_service=activity_services["goals"].core,
            events_service=activity_services["events"].core,
            principles_service=activity_services["principles"].core,
            choices_service=activity_services["choices"].core,
            # Finance Domain (1) - admin-only bookkeeping
            finance_service=core_services["finance"],
            # Curriculum Domains (3) - admin creates, all read
            ku_service=learning_services["article_service"],
            ls_service=learning_services["learning_steps"],
            lp_service=learning_services["learning_paths"],
            # Meta Domains (3)
            report_service=submissions_service,  # For metadata updates
            analytics_service=None,  # Not needed for extraction
            calendar_service=None,  # Not needed for extraction
            # The Destination (+1)
            lifepath_service=lifepath_service,
        )
        logger.info("✅ Submission activity extractor created (DSL journal → entity extraction)")

        # Create journal processing services (requires AI for LLM formatting)
        journal_generator = None
        if ai_service:
            from core.services.submissions import JournalOutputGenerator

            # Get journal storage path from environment (default: /tmp/skuel_journals)
            journal_storage = os.getenv("SKUEL_JOURNAL_STORAGE", "/tmp/skuel_journals")
            journal_generator = JournalOutputGenerator(
                openai_service=ai_service, storage_base=journal_storage
            )
            logger.info(f"✅ Journal output generator created (storage: {journal_storage})")
        else:
            logger.info("⏭️  Journal output generator skipped (intelligence tier: CORE)")

        submissions_processor = SubmissionsProcessingService(
            ku_submission_service=submissions_service,
            transcription_service=core_services["transcription"],  # Simplified TranscriptionService
            content_enrichment=content_enrichment,  # For LLM formatting
            activity_extractor=activity_extractor,  # DSL entity extraction
            journal_generator=journal_generator,  # je_output formatting and disk storage
            event_bus=event_bus,
        )

        # Create Submissions search service (unified query interface)
        submissions_search_service = SubmissionsSearchService(
            ku_backend=submissions_backend, event_bus=event_bus
        )

        logger.info("✅ Submissions pipeline services created")
        logger.info(
            "✅ Submissions core service created (content management: categories, tags, bulk ops)"
        )
        logger.info(
            "✅ Submissions search service created (unified query interface for all submission types)"
        )

        # Create progress report generator and schedule service
        from core.models.submissions.ku_schedule import KuSchedule
        from core.services.feedback.progress_feedback_generator import ProgressFeedbackGenerator
        from core.services.feedback.progress_schedule_service import ProgressScheduleService

        progress_schedule_backend = UniversalNeo4jBackend[KuSchedule](
            driver, NeoLabel.KU_SCHEDULE, KuSchedule, prometheus_metrics=prometheus_metrics
        )
        progress_schedule_service = ProgressScheduleService(backend=progress_schedule_backend)

        # Create ActivityReportService (processor-neutral ActivityReport CRUD)
        from core.services.feedback.activity_report_service import ActivityReportService
        from core.services.feedback.review_queue_service import ReviewQueueService

        activity_report_service = ActivityReportService(
            backend=ai_feedback_backend,
            context_builder=context_builder,
            executor=query_executor,
        )
        review_queue_service = ReviewQueueService(executor=query_executor)
        logger.info("✅ ActivityReportService + ReviewQueueService created")

        progress_generator = ProgressFeedbackGenerator(
            executor=query_executor,
            activity_report_service=activity_report_service,
            context_builder=context_builder,
            openai_service=ai_service,
            insight_store=insight_store,
            event_bus=event_bus,
        )

        # Create progress report background worker (February 2026)
        # Worker checks hourly for due schedules and generates AI_FEEDBACK Entity nodes
        from core.services.background.progress_feedback_worker import ProgressFeedbackWorker

        progress_feedback_worker = ProgressFeedbackWorker(
            schedule_service=progress_schedule_service,
            progress_generator=progress_generator,
            check_interval_seconds=3600,  # Hourly check
        )
        logger.info("✅ Progress report generator, schedule service, and background worker created")

        # Create analytics service
        from core.services.analytics_service import AnalyticsService

        analytics_service = AnalyticsService(
            tasks_service=activity_services["tasks"],
            habits_service=activity_services["habits"],
            goals_service=activity_services["goals"],
            events_service=activity_services["events"],
            finance_service=core_services["finance"],
            choices_service=activity_services["choices"],
            principle_service=activity_services["principles"],
            content_enrichment=content_enrichment,  # ✅ ContentEnrichmentService - Layer 2 reporting
            user_service=user_service,  # Life path alignment
            ku_service=learning_services["article_service"],  # Layer 0 reporting
            lp_service=learning_services["learning_paths"],  # Layer 0 reporting
            event_bus=event_bus,  # Event-driven report generation
        )
        logger.info("✅ Analytics service created")

        # =====================================================================
        # Create orchestration services (GoalTaskGenerator and HabitEventScheduler only)
        orchestration = _create_orchestration_services(
            goals_backend=goals_backend,
            tasks_backend=tasks_backend,
            habits_backend=habits_backend,
            events_backend=events_backend,
        )
        logger.info("✅ Orchestration services created")

        # Wire orchestration services into context_service
        context_service.goal_task_generator = orchestration["goal_task_generator"]
        context_service.habits_service = activity_services["habits"]
        logger.info("✅ UserContextService wired with GoalTaskGenerator and HabitsService")

        # Create advanced services
        advanced = _create_advanced_services(driver, query_executor=query_executor)
        await advanced["performance_optimization"].initialize()
        logger.info("✅ Advanced services created")

        # ========================================================================
        # WIRE EVENT SUBSCRIBERS (Event-Driven Architecture)
        # ========================================================================

        # Import event types
        from core.events import (
            CalendarEventCompleted,
            CalendarEventCreated,
            CalendarEventDeleted,
            CalendarEventRescheduled,
            CalendarEventUpdated,
            ChoiceCreated,
            ChoiceDeleted,
            ChoiceMade,
            ChoiceOutcomeRecorded,
            ChoiceUpdated,
            ExpenseCreated,
            ExpenseDeleted,
            ExpensePaid,
            ExpenseUpdated,
            GoalAbandoned,
            GoalAchieved,
            GoalCreated,
            GoalMilestoneReached,
            GoalProgressUpdated,
            HabitCompleted,
            HabitCompletionBulk,
            HabitCreated,
            HabitMissed,
            HabitStreakBroken,
            HabitStreakMilestone,
            # NOTE: JournalCreated/Updated/Deleted REMOVED (February 2026) - Journal merged into Submissions
            # Journal operations now fire SubmissionCreated/SubmissionDeleted events
            KnowledgeCreated,
            KnowledgeMastered,
            LearningPathCompleted,
            LearningPathProgressUpdated,
            LearningPathStarted,
            LearningStepCompleted,
            LearningStepCreated,
            LearningStepDeleted,
            LearningStepUpdated,
            # NOTE: MapOfContent events removed (January 2026) - MOC is now KU-based
            PrincipleAlignmentAssessed,
            PrincipleCreated,
            PrincipleDeleted,
            PrincipleStrengthChanged,
            PrincipleUpdated,
            TaskCompleted,
            TaskCreated,
            TaskDeleted,
            TaskPriorityChanged,
            TaskUpdated,
        )

        # Create event handlers for context invalidation
        async def invalidate_context_on_task_event(event) -> None:
            """Invalidate user context when task events occur."""
            logger.debug(
                f"Task event received: {event.__class__.__name__} for user {event.user_uid}"
            )
            await user_service.invalidate_context(event.user_uid)

        async def invalidate_context_on_goal_event(event) -> None:
            """Invalidate user context when goal events occur."""
            logger.debug(
                f"Goal event received: {event.__class__.__name__} for user {event.user_uid}"
            )
            await user_service.invalidate_context(event.user_uid)

        async def invalidate_context_on_habit_event(event) -> None:
            """Invalidate user context when habit events occur."""
            logger.debug(
                f"Habit event received: {event.__class__.__name__} for user {event.user_uid}"
            )
            await user_service.invalidate_context(event.user_uid)

        async def invalidate_context_on_principle_event(event) -> None:
            """Invalidate user context when principle events occur."""
            logger.debug(
                f"Principle event received: {event.__class__.__name__} for user {event.user_uid}"
            )
            await user_service.invalidate_context(event.user_uid)

        async def invalidate_context_on_choice_event(event) -> None:
            """Invalidate user context when choice events occur."""
            logger.debug(
                f"Choice event received: {event.__class__.__name__} for user {event.user_uid}"
            )
            await user_service.invalidate_context(event.user_uid)

        async def invalidate_context_on_calendar_event(event) -> None:
            """Invalidate user context when calendar event events occur."""
            logger.debug(
                f"Calendar event received: {event.__class__.__name__} for user {event.user_uid}"
            )
            await user_service.invalidate_context(event.user_uid)

        async def invalidate_context_on_finance_event(event) -> None:
            """Invalidate user context when finance events occur."""
            logger.debug(
                f"Finance event received: {event.__class__.__name__} for user {event.user_uid}"
            )
            await user_service.invalidate_context(event.user_uid)

        # NOTE: invalidate_context_on_journal_event REMOVED (February 2026)
        # Journal merged into Reports — context invalidation via report events

        async def invalidate_context_on_learning_event(event) -> None:
            """Invalidate user context when learning events occur."""
            # All learning events should have user_uid
            user_uid = getattr(event, "user_uid", None)
            if user_uid:
                logger.debug(
                    f"Learning event received: {event.__class__.__name__} for user {user_uid}"
                )
                await user_service.invalidate_context(user_uid)

        async def invalidate_context_on_ls_event(event) -> None:
            """Invalidate user context when learning step events occur."""
            # LS events may have user_uid for user-specific progress
            user_uid = getattr(event, "user_uid", None)
            if user_uid:
                logger.debug(
                    f"Learning step event received: {event.__class__.__name__} for user {user_uid}"
                )
                await user_service.invalidate_context(user_uid)

        # NOTE: invalidate_context_on_moc_event removed (January 2026) - MOC is now KU-based

        # Subscribe to task events
        event_bus.subscribe(TaskCreated, invalidate_context_on_task_event)
        event_bus.subscribe(TaskCompleted, invalidate_context_on_task_event)
        event_bus.subscribe(TaskUpdated, invalidate_context_on_task_event)
        event_bus.subscribe(TaskDeleted, invalidate_context_on_task_event)
        event_bus.subscribe(TaskPriorityChanged, invalidate_context_on_task_event)
        logger.info(
            "✅ UserService subscribed to task events "
            "(TaskCreated, TaskCompleted, TaskUpdated, TaskDeleted, TaskPriorityChanged)"
        )

        # Subscribe to goal events
        event_bus.subscribe(GoalCreated, invalidate_context_on_goal_event)
        event_bus.subscribe(GoalAchieved, invalidate_context_on_goal_event)
        event_bus.subscribe(GoalAbandoned, invalidate_context_on_goal_event)
        event_bus.subscribe(GoalMilestoneReached, invalidate_context_on_goal_event)
        event_bus.subscribe(GoalProgressUpdated, invalidate_context_on_goal_event)
        logger.info(
            "✅ UserService subscribed to goal events "
            "(GoalCreated, GoalAchieved, GoalAbandoned, GoalMilestoneReached, GoalProgressUpdated)"
        )

        # Subscribe to habit events
        event_bus.subscribe(HabitCreated, invalidate_context_on_habit_event)
        event_bus.subscribe(HabitCompleted, invalidate_context_on_habit_event)
        event_bus.subscribe(HabitCompletionBulk, invalidate_context_on_habit_event)
        event_bus.subscribe(HabitMissed, invalidate_context_on_habit_event)
        event_bus.subscribe(HabitStreakBroken, invalidate_context_on_habit_event)
        event_bus.subscribe(HabitStreakMilestone, invalidate_context_on_habit_event)
        logger.info(
            "✅ UserService subscribed to habit events "
            "(HabitCreated, HabitCompleted, HabitCompletionBulk, HabitMissed, HabitStreakBroken, HabitStreakMilestone)"
        )

        # Subscribe to principle events
        event_bus.subscribe(PrincipleCreated, invalidate_context_on_principle_event)
        event_bus.subscribe(PrincipleUpdated, invalidate_context_on_principle_event)
        event_bus.subscribe(PrincipleDeleted, invalidate_context_on_principle_event)
        event_bus.subscribe(PrincipleStrengthChanged, invalidate_context_on_principle_event)
        event_bus.subscribe(PrincipleAlignmentAssessed, invalidate_context_on_principle_event)
        logger.info(
            "✅ UserService subscribed to principle events "
            "(PrincipleCreated, PrincipleUpdated, PrincipleDeleted, PrincipleStrengthChanged, PrincipleAlignmentAssessed)"
        )

        # Subscribe to choice events
        event_bus.subscribe(ChoiceCreated, invalidate_context_on_choice_event)
        event_bus.subscribe(ChoiceUpdated, invalidate_context_on_choice_event)
        event_bus.subscribe(ChoiceDeleted, invalidate_context_on_choice_event)
        event_bus.subscribe(ChoiceMade, invalidate_context_on_choice_event)
        event_bus.subscribe(ChoiceOutcomeRecorded, invalidate_context_on_choice_event)
        logger.info(
            "✅ UserService subscribed to choice events "
            "(ChoiceCreated, ChoiceUpdated, ChoiceDeleted, ChoiceMade, ChoiceOutcomeRecorded)"
        )

        # Subscribe to calendar event events
        event_bus.subscribe(CalendarEventCreated, invalidate_context_on_calendar_event)
        event_bus.subscribe(CalendarEventUpdated, invalidate_context_on_calendar_event)
        event_bus.subscribe(CalendarEventCompleted, invalidate_context_on_calendar_event)
        event_bus.subscribe(CalendarEventDeleted, invalidate_context_on_calendar_event)
        event_bus.subscribe(CalendarEventRescheduled, invalidate_context_on_calendar_event)
        logger.info(
            "✅ UserService subscribed to calendar event events (CalendarEventCreated, CalendarEventUpdated, CalendarEventCompleted, CalendarEventDeleted, CalendarEventRescheduled)"
        )

        # Subscribe to finance events
        event_bus.subscribe(ExpenseCreated, invalidate_context_on_finance_event)
        event_bus.subscribe(ExpenseUpdated, invalidate_context_on_finance_event)
        event_bus.subscribe(ExpenseDeleted, invalidate_context_on_finance_event)
        event_bus.subscribe(ExpensePaid, invalidate_context_on_finance_event)
        logger.info(
            "✅ UserService subscribed to finance events (ExpenseCreated, ExpenseUpdated, ExpenseDeleted, ExpensePaid)"
        )

        # NOTE: Journal event subscriptions REMOVED (February 2026)
        # Journal merged into Reports — context invalidation via report events

        # Subscribe to transcription events for automatic journal-type report creation
        from core.events.transcription_events import TranscriptionCompleted

        event_bus.subscribe(
            TranscriptionCompleted,
            submissions_core_service.handle_transcription_completed,
        )
        logger.info(
            "✅ SubmissionsCoreService subscribed to TranscriptionCompleted "
            "(automatic journal report creation from voice transcriptions)"
        )

        # Subscribe to SubmissionCreated for exercise linking (ADR-040)
        import functools

        from core.events.handlers.exercise_handler import handle_exercise_submission
        from core.events.submission_events import SubmissionCreated

        exercise_handler = functools.partial(
            handle_exercise_submission,
            reports_core_service=submissions_core_service,
        )
        event_bus.subscribe(SubmissionCreated, exercise_handler)
        logger.info(
            "✅ Exercise handler subscribed to SubmissionCreated "
            "(automatic FULFILLS_EXERCISE + SHARES_WITH creation)"
        )

        # Subscribe to feedback events for student notifications
        from core.events.handlers.feedback_notification_handler import (
            handle_feedback_submitted,
            handle_revision_requested,
            handle_submission_approved,
        )
        from core.events.submission_events import (
            FeedbackSubmitted,
            SubmissionApproved,
            SubmissionRevisionRequested,
        )

        feedback_submitted_handler = functools.partial(
            handle_feedback_submitted,
            notification_service=notification_service,
        )
        submission_approved_handler = functools.partial(
            handle_submission_approved,
            notification_service=notification_service,
        )
        revision_requested_handler = functools.partial(
            handle_revision_requested,
            notification_service=notification_service,
        )
        event_bus.subscribe(FeedbackSubmitted, feedback_submitted_handler)
        event_bus.subscribe(SubmissionApproved, submission_approved_handler)
        event_bus.subscribe(SubmissionRevisionRequested, revision_requested_handler)
        logger.info(
            "✅ SubmissionFeedback notification handlers subscribed to FeedbackSubmitted + "
            "SubmissionApproved + SubmissionRevisionRequested (student notifications)"
        )

        # Subscribe to learning events
        event_bus.subscribe(KnowledgeCreated, invalidate_context_on_learning_event)
        event_bus.subscribe(KnowledgeMastered, invalidate_context_on_learning_event)
        event_bus.subscribe(LearningPathStarted, invalidate_context_on_learning_event)
        event_bus.subscribe(LearningPathCompleted, invalidate_context_on_learning_event)
        event_bus.subscribe(LearningPathProgressUpdated, invalidate_context_on_learning_event)
        logger.info(
            "✅ UserService subscribed to learning events "
            "(KnowledgeCreated, KnowledgeMastered, LearningPathStarted, LearningPathCompleted, LearningPathProgressUpdated)"
        )

        # Subscribe to learning step (LS) events
        event_bus.subscribe(LearningStepCreated, invalidate_context_on_ls_event)
        event_bus.subscribe(LearningStepUpdated, invalidate_context_on_ls_event)
        event_bus.subscribe(LearningStepDeleted, invalidate_context_on_ls_event)
        event_bus.subscribe(LearningStepCompleted, invalidate_context_on_ls_event)
        logger.info(
            "✅ UserService subscribed to learning step events "
            "(LearningStepCreated, LearningStepUpdated, LearningStepDeleted, LearningStepCompleted)"
        )

        # NOTE: MOC event subscriptions removed (January 2026)
        # MOC is Entity-based - MOC changes are Entity changes with ORGANIZES relationships
        # Context invalidation happens through Entity events, not separate MOC events

        # ========================================================================
        # CROSS-DOMAIN EVENT SUBSCRIPTIONS
        # "Events over dependencies" - Eliminate service-to-service coupling
        # ========================================================================

        # Task completion → Goal progress update
        goals_service = activity_services["goals"]  # Use unified activity service
        event_bus.subscribe(TaskCompleted, goals_service.progress.handle_task_completed)
        logger.info(
            "✅ GoalsProgressService subscribed to TaskCompleted (automatic progress updates)"
        )

        # Habit completion → Goal progress update
        from core.events.habit_events import HabitCompleted

        event_bus.subscribe(HabitCompleted, goals_service.progress.handle_habit_completed)
        logger.info(
            "✅ GoalsProgressService subscribed to HabitCompleted (automatic progress updates)"
        )

        # Goal achievement → Goal recommendations
        event_bus.subscribe(GoalAchieved, goals_service.recommendations.handle_goal_achieved)
        logger.info(
            "✅ GoalRecommendationService subscribed to GoalAchieved (intelligent recommendations)"
        )

        # Knowledge mastery → Learning Path progress update
        from core.events.learning_events import KnowledgeMastered

        lp_service = learning_services["learning_paths"]
        event_bus.subscribe(KnowledgeMastered, lp_service.progress.handle_knowledge_mastered)
        logger.info(
            "✅ LpProgressService subscribed to KnowledgeMastered (automatic LP progress updates)"
        )

        # Event completion → Knowledge practice tracking
        from core.events.calendar_event_events import CalendarEventCompleted

        ku_service = learning_services["article_service"]
        event_bus.subscribe(CalendarEventCompleted, ku_service.practice.handle_event_completed)
        logger.info(
            "✅ ArticlePracticeService subscribed to CalendarEventCompleted (automatic practice tracking)"
        )

        # Habit streak milestone → Achievement badges
        from core.events.habit_events import HabitStreakMilestone

        habits_service = activity_services["habits"]
        event_bus.subscribe(
            HabitStreakMilestone, habits_service.achievements.handle_habit_streak_milestone
        )
        logger.info(
            "✅ HabitAchievementService subscribed to HabitStreakMilestone (badge awarding)"
        )

        # Learning path completion & knowledge mastery → Learning recommendations
        from core.events.learning_events import KnowledgeMastered, LearningPathCompleted

        learning_intelligence = learning_services["learning_intelligence"]
        event_bus.subscribe(
            LearningPathCompleted,
            learning_intelligence.recommendation_engine.handle_learning_path_completed,
        )
        event_bus.subscribe(
            KnowledgeMastered, learning_intelligence.recommendation_engine.handle_knowledge_mastered
        )
        logger.info(
            "✅ LearningRecommendationEngine subscribed to LearningPathCompleted & KnowledgeMastered "
            "(intelligent next-step recommendations)"
        )

        # Multi-domain analytics → Track activity across all domains
        from core.events.calendar_event_events import CalendarEventCompleted
        from core.events.habit_events import HabitCompleted
        from core.events.task_events import TaskCompleted

        cross_domain_analytics_service = advanced["cross_domain_analytics"]
        event_bus.subscribe(TaskCompleted, cross_domain_analytics_service.handle_task_completed)
        event_bus.subscribe(HabitCompleted, cross_domain_analytics_service.handle_habit_completed)
        event_bus.subscribe(
            CalendarEventCompleted, cross_domain_analytics_service.handle_event_completed
        )
        event_bus.subscribe(ExpenseCreated, cross_domain_analytics_service.handle_expense_created)
        event_bus.subscribe(ExpensePaid, cross_domain_analytics_service.handle_expense_paid)
        event_bus.subscribe(GoalCreated, cross_domain_analytics_service.handle_goal_created)
        event_bus.subscribe(
            KnowledgeMastered, cross_domain_analytics_service.handle_knowledge_mastered
        )
        event_bus.subscribe(
            LearningPathCompleted, cross_domain_analytics_service.handle_path_completed
        )
        # NOTE: JournalCreated subscription REMOVED (February 2026)
        # Journal merged into Reports — cross_domain_analytics needs update in
        # to subscribe to SubmissionCreated and filter for entity_type="journal"
        logger.info(
            "✅ CrossDomainAnalyticsService subscribed to 8 event types "
            "(Tasks, Habits, Events, Expenses, Goals, Knowledge, Paths)"
        )

        # Milestone achievements → Automatic report generation
        from core.events.goal_events import GoalAchieved

        event_bus.subscribe(GoalAchieved, analytics_service.handle_goal_achieved)
        event_bus.subscribe(LearningPathCompleted, analytics_service.handle_learning_path_completed)
        event_bus.subscribe(HabitStreakMilestone, analytics_service.handle_habit_streak_milestone)
        logger.info(
            "✅ AnalyticsService subscribed to 3 milestone events "
            "(GoalAchieved, LearningPathCompleted, HabitStreakMilestone) for auto-report generation"
        )

        # ========================================================================
        # SUBSTANCE TRACKING EVENT SUBSCRIPTIONS (October 17, 2025)
        # "Applied knowledge, not pure theory" - Track real-world knowledge application
        # ========================================================================

        from core.events.article_events import (
            KnowledgeAppliedInTask,
            KnowledgeBuiltIntoHabit,
            KnowledgeBulkAppliedInTask,
            KnowledgeBulkBuiltIntoHabit,
            KnowledgeBulkInformedChoice,
            KnowledgeInformedChoice,
            KnowledgePracticedInEvent,
        )

        # Get KU service from learning services
        ku_service = learning_services["article_service"]

        # Subscribe to substance tracking events (single-entity)
        event_bus.subscribe(KnowledgeAppliedInTask, ku_service.handle_knowledge_applied_in_task)
        event_bus.subscribe(
            KnowledgePracticedInEvent, ku_service.handle_knowledge_practiced_in_event
        )
        event_bus.subscribe(KnowledgeBuiltIntoHabit, ku_service.handle_knowledge_built_into_habit)
        event_bus.subscribe(KnowledgeInformedChoice, ku_service.handle_knowledge_informed_choice)

        # Subscribe to BATCH substance tracking events (O(1) vs O(n))
        event_bus.subscribe(
            KnowledgeBulkAppliedInTask, ku_service.handle_knowledge_bulk_applied_in_task
        )
        event_bus.subscribe(
            KnowledgeBulkBuiltIntoHabit, ku_service.handle_knowledge_bulk_built_into_habit
        )
        event_bus.subscribe(
            KnowledgeBulkInformedChoice, ku_service.handle_knowledge_bulk_informed_choice
        )

        logger.info("✅ ArticleService subscribed to substance tracking events:")
        logger.info("   - KnowledgeAppliedInTask (weight: 0.05)")
        logger.info("   - KnowledgePracticedInEvent (weight: 0.05)")
        logger.info("   - KnowledgeBuiltIntoHabit (weight: 0.10, lifestyle integration)")
        logger.info("   - KnowledgeInformedChoice (weight: 0.07, decision-making)")
        logger.info(
            "   - Bulk events: KnowledgeBulkAppliedInTask, KnowledgeBulkBuiltIntoHabit, KnowledgeBulkInformedChoice"
        )

        # ========================================================================
        # DOMAIN INTELLIGENCE EVENT SUBSCRIPTIONS (January 2026)
        # "Events enable cross-domain intelligence"
        # ========================================================================

        # Habit intelligence - recovery suggestions when streaks break
        from core.events.habit_events import HabitStreakBroken

        habits_service = activity_services["habits"]
        event_bus.subscribe(
            HabitStreakBroken, habits_service.intelligence.handle_habit_streak_broken
        )
        logger.info("✅ HabitsIntelligenceService subscribed to HabitStreakBroken")

        # Choice intelligence - decision learning when outcomes are recorded
        from core.events.choice_events import ChoiceOutcomeRecorded

        choices_service = activity_services["choices"]
        event_bus.subscribe(
            ChoiceOutcomeRecorded, choices_service.intelligence.handle_choice_outcome_recorded
        )
        logger.info("✅ ChoicesIntelligenceService subscribed to ChoiceOutcomeRecorded")

        # Principle intelligence - alignment cascade when strength changes
        from core.events.principle_events import PrincipleStrengthChanged

        principles_service = activity_services["principles"]
        event_bus.subscribe(
            PrincipleStrengthChanged,
            principles_service.intelligence.handle_principle_strength_changed,
        )
        logger.info("✅ PrinciplesIntelligenceService subscribed to PrincipleStrengthChanged")

        # ========================================================================
        # TIER 1 HANDLERS: Quick-Win Event Intelligence (January 2026)
        # ========================================================================

        # Habit intelligence - difficulty tracking when habits are missed
        from core.events.habit_events import HabitMissed

        event_bus.subscribe(HabitMissed, habits_service.intelligence.handle_habit_missed)
        logger.info("✅ HabitsIntelligenceService subscribed to HabitMissed")

        # Choice intelligence - decision pattern tracking when choice is made
        from core.events.choice_events import ChoiceMade

        event_bus.subscribe(ChoiceMade, choices_service.intelligence.handle_choice_made)
        logger.info("✅ ChoicesIntelligenceService subscribed to ChoiceMade")

        # KU intelligence - learning progress when learning steps are completed
        from core.events.curriculum_events import LearningStepCompleted

        event_bus.subscribe(
            LearningStepCompleted, ku_service.intelligence.handle_learning_step_completed
        )
        logger.info("✅ ArticleIntelligenceService subscribed to LearningStepCompleted")

        # ========================================================================
        # TIER 2 HANDLERS: Pattern-Based Event Intelligence (January 2026)
        # ========================================================================

        # Principles intelligence - cross-domain insights from reflections
        from core.events.principle_events import (
            PrincipleConflictRevealed,
            PrincipleReflectionRecorded,
        )

        event_bus.subscribe(
            PrincipleReflectionRecorded,
            principles_service.intelligence.handle_reflection_recorded,
        )
        logger.info("✅ PrinciplesIntelligenceService subscribed to PrincipleReflectionRecorded")

        # Principles intelligence - conflict detection and resolution guidance
        event_bus.subscribe(
            PrincipleConflictRevealed,
            principles_service.intelligence.handle_conflict_revealed,
        )
        logger.info("✅ PrinciplesIntelligenceService subscribed to PrincipleConflictRevealed")

        # NOTE: MOC intelligence subscription removed (January 2026)
        # MOC is Entity-based - intelligence operations happen through Entity ORGANIZES relationships
        # MapOfContentUpdated event type is deprecated - MOC changes are Entity changes

        logger.info(
            "✅ Domain intelligence event subscriptions wired (8 handlers): "
            "Tier 1: HabitStreakBroken, ChoiceOutcomeRecorded, PrincipleStrengthChanged, "
            "HabitMissed, ChoiceMade, LearningStepCompleted | "
            "Tier 2: PrincipleReflectionRecorded, PrincipleConflictRevealed"
        )

        logger.info("✅ Event-driven architecture wired (40 event types subscribed)")
        logger.info("✅ All services initialized")

        # Compose the services container
        services = Services(
            # Activity Domains (6) - All from unified activity_services
            tasks=activity_services["tasks"],
            goals=activity_services["goals"],
            habits=activity_services["habits"],
            events=activity_services["events"],
            choices=activity_services["choices"],
            principles=activity_services["principles"],
            # Finance (NOT an Activity Domain - separate facade)
            finance=core_services["finance"],
            # Knowledge
            article=learning_services["article_service"],
            ku=learning_services["atomic_ku_service"],
            cross_domain=learning_services["cross_domain"],
            # Content
            content_enrichment=content_enrichment,
            feedback=feedback_service,  # LLM feedback on submissions/journals
            exercises=exercise_service,  # Reusable LLM instruction templates
            journal_generator=journal_generator,  # je_output formatting and disk storage
            # Group & Teaching (ADR-040: Teacher exercise workflow)
            group_service=group_service,
            teacher_review=teacher_review_service,
            # Notifications
            notification_service=notification_service,
            # Note: audio_service removed (Dec 2025) - use transcription service directly
            # Reports
            submissions=submissions_service,
            submissions_core=submissions_core_service,  # Content management (categories, tags, bulk ops)
            sharing=unified_sharing_service,  # Cross-domain sharing and visibility control
            submissions_processor=submissions_processor,
            submissions_search=submissions_search_service,  # Unified submission queries
            # Progress feedback (February 2026)
            progress_feedback_generator=progress_generator,
            progress_schedule=progress_schedule_service,
            # Activity report + review queue (March 2026 refactor)
            activity_report=activity_report_service,
            review_queue=review_queue_service,
            # System
            # Note: sync field removed (January 2026) - use unified_ingestion
            unified_ingestion=unified_ingestion,  # ADR-014: Merged MD + YAML ingestion
            calendar=calendar_service,
            system_service=system_service,
            visualization=visualization_service,  # Chart.js/Vis.js/Gantt adapters
            transcription=core_services["transcription"],
            # User management
            user_service=core_services["user"],
            user_relationships=user_relationships,  # UserRelationshipService (pinning, following)
            graph_auth=graph_auth,  # Graph-native authentication (January 2026)
            context_service=context_service,  # Context-aware intelligence (NEW: 2025-11-18)
            # Learning services
            user_progress=learning_services["user_progress"],
            # unified_progress DELETED (January 2026) - use user_progress
            lp=learning_services["learning_paths"],  # ku, ls, lp short-name consistency
            ls=learning_services[
                "learning_steps"
            ],  # Renamed from learning_steps (consistency: ku, ls, lp)
            learning_intelligence=learning_services["learning_intelligence"],
            askesis=None,  # Created in PHASE 4 after intelligence_factory (January 2026)
            askesis_core=askesis_core_service,  # Priority 1.1: CRUD operations for Askesis AI
            # Infrastructure
            graph_adapter=neo4j_adapter,
            event_bus=event_bus,
            prometheus_metrics=prometheus_metrics,
            neo4j_driver=driver,
            query_executor=query_executor,
            insight_store=insight_store,  # Event-driven insights
            # GenAI services (Neo4j native - January 2026)
            embeddings_service=embeddings_service,
            vector_search_service=vector_search_service,
            # Background workers (January 2026)
            embedding_worker=embedding_worker,
            progress_feedback_worker=progress_feedback_worker,
            # Analytics
            analytics=analytics_service,
            cross_domain_analytics=advanced["cross_domain_analytics"],
            # LifePath (Domain #14: The Destination)
            lifepath=lifepath_service,
            # Orchestration (Activity Domains already assigned above)
            goal_task_generator=orchestration["goal_task_generator"],
            habit_event_scheduler=orchestration["habit_event_scheduler"],
            # Advanced
            calendar_optimization=advanced["calendar_optimization"],
            jupyter_sync=advanced["jupyter_sync"],
            performance_optimization=advanced["performance_optimization"],
            # Cross-cutting AI services (require LLM/embeddings)
            askesis_ai=askesis_ai,
            context_aware_ai=context_aware_ai,
            # Lateral relationship services (January 2026 - Core graph architecture)
            lateral=lateral_service,
            # Cross-domain graph queries
            cross_domain_queries=cross_domain_queries_svc,
            # Intelligence tier (ADR-043)
            intelligence_tier=tier,
        )

        # ========================================================================
        # CREATE USER CONTEXT INTELLIGENCE (13-Domain Architecture)
        # ========================================================================
        # UserContextIntelligence = UserContext + 13 Domain Services
        # This is THE service that answers: "What should I work on next?"
        #
        # Entity Types:
        # - Activity Domains (6): Tasks, Goals, Habits, Events, Choices, Principles
        # - Curriculum Domains (3): KU, LS, LP
        # - Processing Domains (2): Reports (includes journals), Analytics
        # - Temporal Domain (1): Calendar

        from core.services.analytics_relationship_service import AnalyticsRelationshipService
        from core.services.feedback import FeedbackRelationshipService
        from core.services.submissions import SubmissionsRelationshipService
        from core.services.user.intelligence import UserContextIntelligenceFactory

        # Create processing domain relationship services
        # NOTE: JournalRelationshipService REMOVED (February 2026) - Journal merged into Entity model
        # SubmissionsRelationshipService handles all submission content relationships
        submissions_relationship_service = SubmissionsRelationshipService(
            backend=submissions_backend
        )
        feedback_relationship_service = FeedbackRelationshipService(backend=submissions_backend)
        analytics_relationship_service = AnalyticsRelationshipService(driver)
        logger.info(
            "✅ Processing domain relationship services created (Submissions, Feedback, Analytics)"
        )

        # ========================================================================
        # CREATE ZPD SERVICE (March 2026 — pedagogical core of Askesis)
        # ========================================================================
        # ZPDService computes the user's Zone of Proximal Development from the
        # Neo4j curriculum graph. Gated by INTELLIGENCE_TIER=FULL — requires
        # behavioral signals from choices + habits intelligence services.
        # Returns empty assessment (not an error) when curriculum graph < 3 KUs.
        from core.services.zpd import ZPDService

        zpd_service: ZPDOperations | None = None
        if tier.ai_enabled:
            zpd_service = ZPDService(
                driver=driver,
                choices_intelligence=activity_services["choices"].intelligence,
                habits_intelligence=activity_services["habits"].intelligence,
            )
            services.zpd_service = zpd_service
            logger.info("✅ ZPDService created (behavioral signals: choices + habits)")
        else:
            logger.info("⏭️  ZPDService skipped (intelligence tier: CORE)")

        # Create factory with all 13 domain services
        context_intelligence_factory = UserContextIntelligenceFactory(
            # Activity Domains (6) - All from unified activity_services
            tasks=activity_services["tasks"].relationships,
            goals=activity_services["goals"].relationships,
            habits=activity_services["habits"].relationships,
            events=activity_services["events"].relationships,
            choices=activity_services["choices"].relationships,
            principles=activity_services["principles"].relationships,
            # Curriculum Domains (3)
            article=learning_services["article_service"].graph,  # ArticleGraphService
            ls=learning_services[
                "learning_steps"
            ].relationships,  # Factory expects 'ls' parameter name
            lp=learning_services[
                "learning_paths"
            ].relationships,  # Factory expects 'lp' parameter name
            # Processing Domains (3)
            submissions=submissions_relationship_service,  # SubmissionsRelationshipService
            feedback=feedback_relationship_service,  # FeedbackRelationshipService
            analytics=analytics_relationship_service,  # AnalyticsRelationshipService
            # Temporal Domain (1)
            calendar=calendar_service,
            # Optional: Vector search for semantic enhancements
            vector_search_service=vector_search_service,
            # Optional: ZPD service for curriculum-graph-aware learning step ranking
            zpd_service=zpd_service,
        )
        services.context_intelligence = context_intelligence_factory
        logger.info("✅ UserContextIntelligence factory created (13 domain services + ZPD wired)")

        # Wire intelligence factory to UserService (post-construction wiring)
        user_service.intelligence_factory = context_intelligence_factory
        logger.info("✅ UserService wired with intelligence factory")

        # Wire intelligence factory to UserContextService (post-construction wiring)
        # This enables get_context_summary() to use factory.create() for intelligence queries
        context_service.intelligence_factory = context_intelligence_factory
        logger.info("✅ UserContextService wired with intelligence factory")

        # Create Askesis service NOW with intelligence_factory as REQUIRED parameter
        # (January 2026: Moved from _create_learning_services() to eliminate post-wiring)
        from core.services.askesis_factory import create_askesis_service

        services.askesis = create_askesis_service(
            intelligence_factory=context_intelligence_factory,
            learning_services=learning_services,
            activity_services=activity_services,
            user_service=user_service,
            zpd_service=zpd_service,
        )
        logger.info(
            "✅ Askesis service created with intelligence_factory (13-domain synthesis + ZPD)"
        )

        # ========================================================================
        # CREATE SEARCH ROUTER (One Path Forward, January 2026)
        # ========================================================================
        # SearchRouter = THE path for all search. No fallback needed.
        # Activity Domains → graph_aware_faceted_search()
        # Curriculum Domains → simple text search via domain services
        # Cross-domain → aggregates from all searchable domains
        from core.models.search.search_router import SearchRouter

        search_router = SearchRouter(services)
        services.search_router = search_router
        logger.info("✅ SearchRouter created (One Path Forward)")

        logger.info("✅ Service composition complete")
        # Return only (services, knowledge_backend) - search_backend is internal to SearchRouter
        return Result.ok((services, knowledge_backend))

    except Exception as e:
        import traceback

        logger.error(f"❌ Service composition failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return Result.fail(
            Errors.system(
                f"Service initialization failed: {e!s}",
                service="ServiceContainer",
                error_type=type(e).__name__,
            )
        )


# Export the main functions
__all__ = [
    "EventBusOperations",
    "Services",
    "compose_services",
]
