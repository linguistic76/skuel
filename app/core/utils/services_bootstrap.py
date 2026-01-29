"""
Lightweight Service Bootstrap for SKUEL
=======================================

SKUEL's 14-Domain + 4-System Service Composition
-------------------------------------------------

This module is the composition root for SKUEL's complete architecture.
It wires together all domain services and cross-cutting systems using
constructor injection - no heavy DI framework required.

THE 14 DOMAINS COMPOSED HERE
----------------------------

**Activity Domain Services (7):**
    1. tasks      → TasksService      - Work items and dependencies
    2. goals      → GoalsService      - Objectives and milestones
    3. habits     → HabitsService     - Recurring behaviors and streaks
    4. events     → EventsService     - Calendar items and scheduling
    5. choices    → ChoicesService    - Decisions and outcomes
    6. principles → PrinciplesService - Values and alignment
    7. finance    → FinanceService    - Expenses and budgets

**Curriculum Domain Services (3):**
    8. knowledge  → KuService         - Knowledge Units (ku:)
    9. ls         → LsService         - Learning Steps (ls:)
    10. lp        → LpService         - Learning Paths (lp:)

**Content/Organization Domain Services (4):**
    11. journals/assignments → AssignmentsCoreService - File processing
    12. moc       → MocService        - Map of Content organization
    13. life_path → ReportLifePathService - Life goal alignment
    14. reports   → ReportService     - Statistical aggregation

THE 4 CROSS-CUTTING SYSTEMS
---------------------------

**Foundation & Infrastructure:**
    1. user_context → UserContextBuilder - ~240 fields cross-domain state
    2. search       → SearchOperations   - Unified search across domains
    3. askesis      → AskesisService     - Life context synthesis
    4. messaging    → Conversation       - Turn-based chat interface

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
    - Neo4j          ✅ Graph database (runs from /infra) - REQUIRED
    - Deepgram API   ✅ Audio transcription - REQUIRED

**Optional AI Services:**
    - OpenAI API     🟡 AI/LLM features and embeddings - OPTIONAL (graceful degradation)

**Future Services (Pre-wired but Disabled):**
    - Redis          🟡 Distributed caching (in-memory cache currently used)
    - Ollama         🟡 Local LLM inference (OpenAI API currently used)
    - RabbitMQ/Kafka 🟡 Message queue (in-memory event bus currently used)
    - Prometheus     🟡 Metrics (manual monitoring currently used)
    - Grafana        🟡 Dashboards (manual monitoring currently used)
    - Nginx          🟡 Reverse proxy (direct access currently used)

See: /FUTURE_SERVICES.md for detailed explanation of why these services
     are pre-wired but disabled, and when to enable them.

Configuration for future services exists in:
    - core/config/unified_config.py (CacheConfig, MessageQueueConfig)
    - docker-compose.production.yml (Service definitions)

They are intentionally disabled to reduce operational overhead during
development. Enable when production requirements demand them.

See Also:
    /core/models/shared_enums.py - Domain enum definitions
    /core/services/protocols/domain_protocols.py - Service interfaces
    /adapters/persistence/neo4j/universal_backend.py - Generic backend
    /FUTURE_SERVICES.md - Pre-wired infrastructure services explanation
"""

__version__ = "4.0"  # Updated with 14-domain + 4-system architecture


import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.constants import MasteryLevel
from core.models.enums.neo_labels import NeoLabel

if TYPE_CHECKING:
    from core.services.adaptive_sel_service import AdaptiveSELService

from core.services.protocols import (
    AskesisOperations,
    AsyncCloseable,
    ChoicesOperations,
    Closeable,
    # Infrastructure
    EventBusOperations,
    EventsOperations,
    FinancesOperations,
    GoalsOperations,
    HabitsOperations,
    IntelligenceOperations,
    JournalsOperations,
    # Knowledge operations
    KuOperations,
    # NOTE: LearningOperations DELETED January 2026 - was dead code (type hint wrong)
    # NOTE: LearningPathsOperations DELETED January 2026 - replaced by LpOperations
    LpOperations,
    LsOperations,
    PrinciplesOperations,
    SearchOperations,
    # Domain operations
    TasksOperations,
    UserContextOperations,
    UserOperations,
)
from core.services.protocols.facade_protocols import LpFacadeProtocol
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
    # ========================================================================
    tasks: TasksOperations | None = None
    goals: GoalsOperations | None = None
    habits: HabitsOperations | None = None
    events: EventsOperations | None = None
    choices: ChoicesOperations | None = None
    principles: PrinciplesOperations | None = None

    # ========================================================================
    # FINANCE (1) - NOT an Activity Domain (standalone facade)
    # ========================================================================
    finance: FinancesOperations | None = None

    # ========================================================================
    # CURRICULUM DOMAINS (3) - KU, LS, LP
    # Note: MOC is a Content/Organization domain, not Curriculum
    # ========================================================================
    ku: KuOperations | None = None  # KuService (Knowledge Units) - atomic knowledge content
    personalized_discovery: Any = None  # PersonalizedKnowledgeDiscoveryAdapter - THE way
    adaptive_sel: "AdaptiveSELService | None" = (
        None  # AdaptiveSELService - personalized curriculum delivery
    )
    cross_domain: Any = None  # AdaptiveLpCrossDomainService - Cross-domain learning opportunities

    # Content services (Protocol-typed)
    journals: JournalsOperations | None = None
    journals_core: JournalsOperations | None = None  # JournalsCoreService - CRUD for Journal nodes (January 2026)
    transcript_processor: Any = (
        None  # TranscriptProcessorService - Processes transcripts into documents
    )
    transcription: Any = None  # TranscriptionService (simplified, Dec 2025)

    # Journal services (LLM-based journal processing)
    journal_feedback: Any = None  # JournalFeedbackService - LLM feedback on journals
    journal_projects: Any = None  # JournalProjectService - Reusable LLM project templates

    # Assignment services (Phase 1 - File submission pipeline)
    assignments: Any = None  # AssignmentSubmissionService - File upload and assignment management
    assignments_core: Any = (
        None  # AssignmentsCoreService - Content management (categories, tags, bulk operations)
    )
    assignment_processor: Any = (
        None  # AssignmentProcessorService - Orchestrates processing (LLM, human, hybrid)
    )
    processing_pipeline: Any = None  # Alias for assignment_processor

    # Assignments query service (Unified query interface for all assignment types)
    assignments_query: Any = None  # AssignmentsQueryService - Query all assignment types (journals, essays, projects, etc.)

    # System services
    # Note: sync field REMOVED (January 2026) - use unified_ingestion instead
    # Note: events moved to Activity Domains section above
    calendar: Any = None  # CalendarService - unified calendar aggregation (no CalendarOperations protocol yet)
    system_service: Any = None  # SystemService - health checks and system monitoring

    # User management (fundamental)
    user_service: UserOperations | None = None  # UserService - user profile management
    user_relationships: Any = None  # UserRelationshipService - pinning, following, etc. (no protocol yet)
    graph_auth: Any = None  # GraphAuthService - graph-native authentication
    context_service: UserContextOperations | None = None  # UserContextService - context-aware intelligence (NEW: 2025-11-18)
    context_intelligence: Any = (
        None  # UserContextIntelligenceFactory - 13-domain intelligence (2025-11-26)
    )

    # Consolidated Learning Services (V4)
    # learning facade uses LpFacadeProtocol for MyPy type checking
    learning: LpFacadeProtocol | None = None  # LpService facade (routes access .intelligence, .core, .search)
    user_progress: Any = None  # UserProgressService - User knowledge profile and mastery tracking
    # Note: unified_progress DELETED (January 2026) - use user_progress or UserContextBuilder
    learning_paths: LpOperations | None = (
        None  # LpService - All path management (Protocol-typed for GraphQL)
    )
    learning_steps: LsOperations | None = (
        None  # LsService - Dedicated learning step management (NEW: October 24, 2025)
    )
    learning_intelligence: IntelligenceOperations | None = None  # LpIntelligenceService - analysis and recommendations
    askesis: AskesisOperations | None = None  # AskesisService - Unified retrieval chatbot (requires OPENAI_API_KEY)
    askesis_core: Any = (
        None  # AskesisCoreService - CRUD operations for Askesis AI assistant instances
    )

    # Infrastructure adapters
    graph_adapter: Any = None  # Neo4jAdapter - database connection
    event_bus: EventBusOperations | None = None

    # Note: choices moved to Activity Domains section above

    # Content organization (Added: October 17, 2025)
    # Note: MOC is KU-based (January 2026), uses KuOperations protocol
    moc: KuOperations | None = None  # MOCService - Maps of Content for non-linear knowledge organization

    # New YAML/Graph services
    yaml_loader: Any = None
    markdown_parser: Any = None
    apoc_adapter: Any = None

    # Unified Ingestion Service (ADR-014: Merged MD + YAML ingestion)
    unified_ingestion: Any = (
        None  # UnifiedIngestionService - handles both MD and YAML for all 14 entity types
    )

    # The Destination - LifePath (Domain #14)
    # "Everything flows toward the life path"
    # Vision capture + alignment measurement + recommendations
    lifepath: Any = None  # LifePathService - Vision→Action bridge (January 2026)

    # Report services (meta-service, not a domain)
    reports: Any = None  # ReportService - Statistical report generation
    cross_domain_analytics: Any = (
        None  # CrossDomainAnalyticsService - Event-driven analytics (Phase 5)
    )

    # Search infrastructure (One Path Forward, January 2026)
    search_router: SearchOperations | None = None  # SearchRouter - THE path for all search

    # Orchestration services (Phase 1 - Essential)
    # Note: principles moved to Activity Domains section above
    goal_task_generator: Any = None  # GoalTaskGenerator - Auto-generate tasks from goals
    habit_event_scheduler: Any = None  # HabitEventScheduler - Auto-schedule events from habits

    # Advanced services (Phase 2 - Optional)
    calendar_optimization: Any = None  # CalendarOptimizationService - Cognitive load optimization
    jupyter_sync: Any = None  # JupyterNeo4j-Obsidian sync
    performance_optimization: Any = (
        None  # PerformanceOptimizationService - Scale optimization & caching
    )

    # Intelligence services (Phase 3 - Real implementations replacing mock data)
    tasks_intelligence: Any = None  # TasksIntelligenceService - Task intelligence (knowledge, learning, behavioral, performance)
    habits_intelligence: Any = (
        None  # HabitsIntelligenceService - Habit formation and behavioral science
    )
    goals_intelligence: Any = (
        None  # GoalsIntelligenceService - Achievement prediction and motivation
    )
    events_intelligence: Any = (
        None  # EventsIntelligenceService - Scheduling patterns and time optimization
    )
    choices_intelligence: Any = (
        None  # ChoicesIntelligenceService - Decision analysis and bias detection
    )
    askesis_ai: Any = (
        None  # AskesisAIService - AI-powered discipline tracking (requires LLM/embeddings)
    )
    ku_intelligence: Any = (
        None  # KuIntelligenceService - Knowledge graph and semantic relationships
    )
    principles_intelligence: Any = (
        None  # PrinciplesIntelligenceService - Value alignment and ethical guidance
    )
    context_aware_ai: Any = (
        None  # ContextAwareAIService - AI-powered context intelligence (requires LLM/embeddings)
    )

    # Infrastructure - Neo4j driver (exposed for routes that need context building)
    driver: Any = None  # Neo4j AsyncDriver - Exposed for routes requiring UserContextBuilder
    neo4j_driver: Any = None  # Alias for driver (backward compatibility)

    # GenAI services (Neo4j native embeddings and vector search - January 2026)
    embeddings_service: Any = None  # Neo4jGenAIEmbeddingsService - Embeddings via ai.text.embed()
    vector_search_service: Any = (
        None  # Neo4jVectorSearchService - Vector search via db.index.vector.queryNodes()
    )

    # Services are ready when constructed - no lifecycle needed

    async def cleanup(self) -> None:
        """Clean up all async resources"""
        logger.info("Cleaning up service container...")

        # Close database connection with detailed logging
        if self.graph_adapter:
            try:
                logger.info("Closing graph adapter...")
                if isinstance(self.graph_adapter, AsyncCloseable):
                    await self.graph_adapter.close()
                elif isinstance(self.graph_adapter, Closeable):
                    self.graph_adapter.close()
                logger.info("Graph adapter closed")
            except Exception as e:
                logger.warning(f"Error closing graph adapter: {e}")

        # Close event bus with detailed logging
        if self.event_bus:
            try:
                logger.info("Closing event bus...")
                if isinstance(self.event_bus, AsyncCloseable):
                    await self.event_bus.close()
                elif isinstance(self.event_bus, Closeable):
                    self.event_bus.close()
                logger.info("Event bus closed")
            except Exception as e:
                logger.warning(f"Error closing event bus: {e}")

        # Close individual services if they have cleanup methods
        services_to_close = [
            ("tasks", self.tasks),
            ("events", self.events),
            ("finance", self.finance),
            ("journals", self.journals),
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
    driver=None,  # Phase 4: Neo4j driver for event-driven integrations
) -> dict[str, Any]:
    """Create core productivity services.

    Args:
        tasks_backend: UniversalNeo4jBackend[Task],
        events_backend: UniversalNeo4jBackend[Event],
        finance_backend: UniversalNeo4jBackend[ExpensePure],
        invoice_backend: UniversalNeo4jBackend[InvoicePure],
        habits_backend: UniversalNeo4jBackend[Habit],
        habit_completions_backend: UniversalNeo4jBackend[HabitCompletion],
        transcription_backend: UniversalNeo4jBackend[Transcription],
        user_service: UserService for context operations (REQUIRED),
        event_bus: Event bus for publishing domain events (optional),
        graph_intelligence: GraphIntelligenceService for Phase 1-4 queries (optional),
        ku_inference_service: KuInferenceService for knowledge inference (optional),
        analytics_engine: KuAnalyticsEngine for advanced analytics (optional),
        ku_generation_service: KuGenerationService for knowledge generation (optional),
        deepgram_api_key: Deepgram API key for audio transcription (REQUIRED)
    """
    from adapters.external.deepgram import DeepgramAdapter
    from core.services.events_service import EventsService
    from core.services.finance_service import FinanceService
    from core.services.habits_service import HabitsService
    from core.services.tasks_service import TasksService
    from core.services.transcription import TranscriptionService

    # Create DeepgramAdapter (REQUIRED - fail-fast if key missing)
    deepgram_adapter = DeepgramAdapter(deepgram_api_key)

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
            driver=driver,  # REQUIRED - fail-fast
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
        goals_backend: UniversalNeo4jBackend[Goal]
        tasks_backend: UniversalNeo4jBackend[Task]
        habits_backend: UniversalNeo4jBackend[Habit]
        events_backend: UniversalNeo4jBackend[Event]
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
    driver: Any,
    neo4j_adapter: Any,
    progress_backend: Any,
    knowledge_backend: Any,
    content_adapter: Any,  # ContentOperations protocol (Neo4jContentAdapter),
    chunking_service: Any,
    user_service: Any,
    graph_intelligence: Any,
    llm_service: Any,  # LLMService for RAG generation (Phase 1)
    _tasks_service: Any = None,  # Placeholder: TasksService for entity extraction (Phase 2.5)
    _habits_service: Any = None,  # Placeholder: HabitsService for entity extraction (Phase 2.5)
    _goals_service: Any = None,  # Placeholder: GoalsService for entity extraction (Phase 2.5)
    _events_service: Any = None,  # Placeholder: EventsService for entity extraction (Phase 2.5)
    event_bus: Any = None,
) -> dict[str, Any]:
    """Create all learning-related services using 100% dynamic backends."""
    from adapters.personalized_knowledge_discovery_adapter import (
        create_personalized_knowledge_discovery_adapter,
    )
    from core.services.adaptive_sel_service import AdaptiveSELService
    from core.services.ku_retrieval import KuRetrieval
    from core.services.ku_service import KuService
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
    embeddings_service = None
    vector_search_service = None

    try:
        from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService
        from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

        # Create GenAI embeddings service (uses ai.text.embed())
        embeddings_service = Neo4jGenAIEmbeddingsService(driver)
        logger.info("✅ Neo4j GenAI embeddings service created")

        # Create vector search service (uses db.index.vector.queryNodes())
        vector_search_service = Neo4jVectorSearchService(driver, embeddings_service)
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

    # Phase 3: Create knowledge service using dynamic backends with REQUIRED query_builder
    # January 2026: KuIntelligenceService created internally, no longer passed in
    # January 2026 - GenAI Integration: Pass vector search and embeddings services
    ku_service = KuService(
        repo=knowledge_backend,
        content_repo=content_adapter,  # Neo4jContentAdapter implements ContentOperations protocol
        neo4j_adapter=neo4j_adapter,
        chunking_service=chunking_service,
        graph_intelligence_service=graph_intelligence,
        query_builder=unified_query_builder,  # Phase 3: QueryBuilder is now REQUIRED
        event_bus=event_bus,  # Event-driven architecture
        driver=driver,  # Phase 4: For event-driven practice tracking
        user_service=user_service,  # January 2026: KU-Activity Integration
        vector_search_service=vector_search_service,  # January 2026: GenAI vector search
        embeddings_service=embeddings_service,  # January 2026: GenAI embeddings (THE ONLY service)
    )

    # Create progress services
    user_progress = UserProgressService(driver)
    # Note: unified_progress DELETED (January 2026) - use user_progress or UserContextBuilder

    # Create learning step service (LS operations)
    # January 2026: graph_intel now REQUIRED for unified Curriculum architecture (ADR-030)
    ls_service = LsService(driver=driver, graph_intel=graph_intelligence, event_bus=event_bus)

    # Create path service (LP operations - delegates LS operations to LsService)
    # January 2026: Intelligence created internally (unified with other domains)
    learning_paths = LpService(
        driver=driver,
        ls_service=ls_service,  # Delegate LS operations to LsService
        ku_service=ku_service,
        progress_service=user_progress,
        graph_intelligence_service=graph_intelligence,  # Phase 1-4 graph queries (REQUIRED)
        event_bus=event_bus,  # Event-driven architecture
        progress_backend=progress_backend,
        user_service=user_service,
    )

    # Create retrieval service (embeddings_service is OPTIONAL - graceful degradation)
    ku_retrieval = KuRetrieval(
        knowledge_repo=knowledge_backend,
        embeddings_service=embeddings_service,  # Can be None - will use keyword search fallback
        unified_query_builder=unified_query_builder,
        user_progress_service=user_progress,
        chunking_service=chunking_service,
    )

    # Create personalized discovery (ku_retrieval with optional embeddings)
    personalized_discovery = create_personalized_knowledge_discovery_adapter(
        user_service=user_service,
        ku_retrieval=ku_retrieval,
        driver=driver,
        user_progress_service=user_progress,
    )

    # Create adaptive SEL service
    adaptive_sel = AdaptiveSELService(ku_backend=knowledge_backend, user_service=user_service)

    # NOTE: Askesis creation MOVED to compose_services() (January 2026)
    # This allows intelligence_factory to be passed at construction time (not post-wired)
    # Askesis needs: learning_paths.intelligence, graph_intelligence, user_service, llm_service,
    #                embeddings_service, ku_service, tasks/goals/habits/events services

    # Create cross-domain service (circular import resolved via adaptive_lp_models.py)
    from core.services.adaptive_lp.adaptive_lp_cross_domain_service import (
        AdaptiveLpCrossDomainService,
    )

    cross_domain_service = AdaptiveLpCrossDomainService(MasteryLevel.BEGINNER)

    return {
        "learning_intelligence": learning_paths.intelligence,  # Access via facade
        "ku_service": ku_service,
        "user_progress": user_progress,
        # unified_progress DELETED (January 2026)
        "learning_paths": learning_paths,
        "learning_steps": ls_service,  # NEW: Dedicated LS service
        "ku_retrieval": ku_retrieval,
        "personalized_discovery": personalized_discovery,
        "adaptive_sel": adaptive_sel,
        # NOTE: "askesis" MOVED to compose_services() (January 2026)
        "cross_domain": cross_domain_service,
        "embeddings_service": embeddings_service,  # For intelligence services
        "vector_search_service": vector_search_service,  # For semantic search (Phase 1)
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
    driver: Any = None,
    # Tasks-specific optional dependencies
    ku_inference_service: Any = None,
    analytics_engine: Any = None,
    ku_generation_service: Any = None,
) -> dict[str, Any]:
    """Create all 6 Activity Domain services.

    Activity Domains share:
        - backend: UniversalNeo4jBackend[T] for CRUD
        - graph_intelligence: Pure Cypher graph queries (REQUIRED)
        - event_bus: Domain event publishing (optional)

    Domain-specific dependencies:
        - Tasks: ku_inference_service, analytics_engine, ku_generation_service
        - Habits: completions_backend, driver (for achievements)
        - Goals: driver (for event-driven recommendations)
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
            driver=driver,  # REQUIRED - fail-fast
            event_bus=event_bus,
        ),
        "goals": GoalsService(
            backend=goals_backend,
            graph_intelligence_service=graph_intelligence,
            event_bus=event_bus,
            driver=driver,
        ),
        "choices": ChoicesService(
            backend=choices_backend,
            graph_intelligence_service=graph_intelligence,
            event_bus=event_bus,
        ),
        "principles": PrinciplesService(
            backend=principles_backend,
            graph_intelligence_service=graph_intelligence,
            goals_backend=goals_backend,
            habits_backend=habits_backend,
            reflection_backend=reflection_backend,
            event_bus=event_bus,
        ),
    }


def _create_advanced_services(driver: Any) -> dict[str, Any]:
    """Create Phase 2 advanced services."""
    from pathlib import Path

    from core.services.calendar_optimization_service import CalendarOptimizationService
    from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService
    from core.services.jupyter_neo4j_sync import JupyterNeo4jSync
    from core.services.performance_optimization_service import PerformanceOptimizationService

    vault_path = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/home/mike/0bsidian/skuel"))

    return {
        "calendar_optimization": CalendarOptimizationService(),
        "jupyter_sync": JupyterNeo4jSync(driver=driver, vault_path=vault_path),
        "performance_optimization": PerformanceOptimizationService(),
        "cross_domain_analytics": CrossDomainAnalyticsService(driver=driver),  # Phase 4
    }


# ============================================================================
# BOOTSTRAP FUNCTION (The Single Wiring Point)
# ============================================================================


async def compose_services(
    neo4j_adapter: Any, event_bus: EventBusOperations = None
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
        event_bus: Event bus adapter (optional, will create default if None)

    Returns:
        Result[tuple[Services, knowledge_backend]]: Success with wired services or failure
        with detailed error. Returns tuple of (Services, KnowledgeUniversalBackend) for
        GraphQL injection. SearchRouter is available via services.search_router.

    Raises:
        ValueError: If any required dependency is missing
    """
    logger.info("🔧 Composing service dependencies (FAIL-FAST mode)...")

    try:
        # ========================================================================
        # PHASE 0: CREATE EVENT BUS (Event-Driven Architecture)
        # ========================================================================

        # Create event bus if not provided
        if not event_bus:
            from adapters.infrastructure.event_bus import InMemoryEventBus

            event_bus = InMemoryEventBus()
            logger.info("✅ InMemoryEventBus created (event-driven architecture enabled)")
        else:
            logger.info("✅ Using provided event bus")
        # ========================================================================
        # PHASE 1: VALIDATE ALL REQUIRED DEPENDENCIES (FAIL-FAST)
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

        # ========================================================================
        # PHASE 1.5: SYNC AUTH INDEXES AND CLEANUP (Startup Tasks)
        # ========================================================================
        from core.utils.neo4j_schema_manager import Neo4jSchemaManager

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
        # PHASE 2: CREATE SERVICES (All dependencies are guaranteed available)
        # ========================================================================

        # 100% Dynamic Pattern: Instantiate UniversalNeo4jBackend directly at point of use
        # "The plant (models) grows on the lattice (UniversalNeo4jBackend)"
        from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
        from core.models.askesis.askesis import Askesis
        from core.models.assignment.assignment import Assignment
        from core.models.choice.choice import Choice
        from core.models.event.event import Event
        from core.models.finance.finance_pure import ExpensePure
        from core.models.finance.invoice import InvoicePure
        from core.models.goal.goal import Goal
        from core.models.habit.completion import HabitCompletion
        from core.models.habit.habit import Habit
        from core.models.journal.journal_pure import JournalPure
        from core.models.ku.ku import Ku

        # NOTE: MapOfContent import removed (January 2026) - MOC is now KU-based
        # MOC is a KU with ORGANIZES relationships, not a separate entity
        from core.models.principle.principle import Principle
        from core.models.principle.reflection import PrincipleReflection
        from core.models.progress import UserProgress
        from core.models.task.task import Task
        from core.models.transcription.transcription import Transcription

        # Create backends directly (no wrapper) - makes lattice pattern visible
        # ACTIVITY DOMAINS - Use UniversalNeo4jBackend (requires DomainModelProtocol)
        # Labels use NeoLabel enum for type-safety and codebase self-awareness
        tasks_backend = UniversalNeo4jBackend[Task](driver, NeoLabel.TASK, Task)
        events_backend = UniversalNeo4jBackend[Event](driver, NeoLabel.EVENT, Event)
        habits_backend = UniversalNeo4jBackend[Habit](driver, NeoLabel.HABIT, Habit)
        habit_completions_backend = UniversalNeo4jBackend[HabitCompletion](
            driver, NeoLabel.HABIT_COMPLETION, HabitCompletion
        )
        goals_backend = UniversalNeo4jBackend[Goal](driver, NeoLabel.GOAL, Goal)
        finance_backend = UniversalNeo4jBackend[ExpensePure](driver, NeoLabel.EXPENSE, ExpensePure)
        invoice_backend = UniversalNeo4jBackend[InvoicePure](driver, NeoLabel.INVOICE, InvoicePure)
        journals_backend = UniversalNeo4jBackend[JournalPure](driver, NeoLabel.JOURNAL, JournalPure)
        transcription_backend = UniversalNeo4jBackend[Transcription](
            driver, NeoLabel.TRANSCRIPTION, Transcription
        )

        # IDENTITY/FOUNDATION - Use dedicated UserBackend (no DTO conversion lifecycle)
        # User is NOT an activity domain - it's the identity layer all domains reference
        # See: CLAUDE.md §2.11 Domain Architecture Categories
        from adapters.persistence.neo4j.user_backend import UserBackend

        users_backend = UserBackend(driver)
        knowledge_backend = UniversalNeo4jBackend[Ku](driver, NeoLabel.KU, Ku)
        principle_backend = UniversalNeo4jBackend[Principle](driver, NeoLabel.PRINCIPLE, Principle)
        reflection_backend = UniversalNeo4jBackend[PrincipleReflection](
            driver, NeoLabel.PRINCIPLE_REFLECTION, PrincipleReflection
        )
        choice_backend = UniversalNeo4jBackend[Choice](driver, NeoLabel.CHOICE, Choice)
        progress_backend = UniversalNeo4jBackend[UserProgress](
            driver, NeoLabel.USER_PROGRESS, UserProgress
        )
        # NOTE: vectors_backend REMOVED (January 2026) - was unused dead code
        # NOTE: MOC backend REMOVED (January 2026) - MOC is now KU-based
        # MOC is a KU with ORGANIZES relationships, uses KU backend via MOCService
        # See /docs/domains/moc.md for the KU-based architecture
        assignments_backend = UniversalNeo4jBackend[Assignment](
            driver, NeoLabel.ASSIGNMENT, Assignment
        )
        askesis_backend = UniversalNeo4jBackend[Askesis](driver, NeoLabel.ASKESIS, Askesis)

        logger.info("✅ Domain backends created (100% dynamic pattern - direct instantiation)")

        # Create user service FIRST (foundation service with no dependencies)
        from core.services.user_service import create_user_service

        user_service = create_user_service(users_backend, driver)
        logger.info("✅ UserService created (foundation service)")

        # Create user relationship service (pinning, following, etc.)
        from core.services.user_relationship_service import UserRelationshipService

        user_relationships = UserRelationshipService(driver=driver)
        logger.info("✅ UserRelationshipService created (pinning, following)")

        # Create graph-native authentication service (January 2026)
        # Sessions stored in Neo4j with bcrypt password hashing
        from adapters.persistence.neo4j.session_backend import SessionBackend
        from core.auth.graph_auth import GraphAuthService

        session_backend = SessionBackend(driver)
        graph_auth = GraphAuthService(
            user_backend=users_backend,
            session_backend=session_backend,
        )
        logger.info("✅ GraphAuthService created (graph-native authentication)")

        # Create user context service (context-aware intelligence)
        # NOTE: UserContextBuilder now owns user resolution (Option A architecture, Nov 2025)
        # This eliminates repetitive user lookup in every service method.
        from core.services.user import UserContextBuilder, UserContextService

        context_builder = UserContextBuilder(driver, user_service=user_service)
        context_service = UserContextService(
            context_builder=context_builder,
            user_service=user_service,
            tasks_service=None,  # Will be wired after tasks service is created
            driver=driver,
        )
        logger.info("✅ UserContextService created (context-aware intelligence)")
        logger.info("   - UserContextBuilder owns user resolution (Option A architecture)")

        # Create graph intelligence (needed by tasks service)
        from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService

        graph_intelligence = GraphIntelligenceService(driver)
        logger.info("✅ GraphIntelligenceService created")

        # Create analytics services (needed by tasks service)
        from core.services.ku_analytics_engine import KuAnalyticsEngine
        from core.services.ku_generation_service import KuGenerationService
        from core.services.ku_inference_service import KuInferenceService

        analytics_engine = KuAnalyticsEngine()
        ku_inference_service = KuInferenceService()
        ku_generation_service = KuGenerationService()
        logger.info("✅ Analytics and inference services created")

        # ========================================================================
        # ACTIVITY DOMAIN SERVICES (6) - Unified creation
        # ========================================================================
        activity_services = _create_activity_services(
            tasks_backend=tasks_backend,
            events_backend=events_backend,
            habits_backend=habits_backend,
            habit_completions_backend=habit_completions_backend,
            goals_backend=goals_backend,
            choices_backend=choice_backend,
            principles_backend=principle_backend,
            reflection_backend=reflection_backend,
            graph_intelligence=graph_intelligence,
            event_bus=event_bus,
            driver=driver,
            ku_inference_service=ku_inference_service,
            analytics_engine=analytics_engine,
            ku_generation_service=ku_generation_service,
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
            driver=driver,  # Phase 4: For event-driven integrations (Habit→Achievements)
            deepgram_api_key=deepgram_api_key,  # For audio transcription
        )
        logger.info("✅ Core services created (with event bus + Deepgram wiring)")

        # GRAPH-NATIVE: Wire analytics engine with TasksRelationshipService
        # tasks_service comes from activity_services (unified Activity Domain creation)
        tasks_service = activity_services["tasks"]
        analytics_engine.relationship_service = tasks_service.relationships
        logger.info("✅ KuAnalyticsEngine wired with TasksRelationshipService")

        # Wire tasks_service into context_service for context-aware operations
        context_service.tasks_service = tasks_service
        logger.info("✅ UserContextService wired with TasksService")

        # Note: TranscriptionService is already created in core_services with Deepgram wiring
        # Note: MarkdownSyncService DELETED (January 2026) - use UnifiedIngestionService

        # Create UnifiedIngestionService (ADR-014: Merged MD + YAML ingestion)
        # January 2026 - GenAI Integration: Pass embeddings service for automatic embedding generation
        from core.services.ingestion import UnifiedIngestionService

        unified_ingestion = UnifiedIngestionService(
            driver=driver,
            embeddings_service=None,  # Optional - will be created later in learning_services
        )
        logger.info(
            "✅ Content services created (includes UnifiedIngestionService with optional embeddings)"
        )

        # Create knowledge components using 100% dynamic backend pattern
        from adapters.persistence.neo4j.neo4j_connection import get_connection
        from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
        from core.services.ku_chunking_service import KuChunkingService

        chunking_service = KuChunkingService()

        # Use Neo4jContentAdapter for ContentOperations protocol (store_content_with_chunks, get_chunks, etc.)
        connection = await get_connection()
        content_adapter = Neo4jContentAdapter(connection)

        # Create LLM service BEFORE learning services (OPTIONAL - enables AI features)
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
                llm_service = None
                logger.warning("⚠️ LLM service disabled - OPENAI_API_KEY not configured")
        except Exception as e:
            logger.error(f"Failed to initialize LLM service: {e}")
            llm_service = None
            logger.warning("⚠️ LLM service disabled - continuing with basic features")

        # Create learning services (graph_intelligence already created above)
        learning_services = _create_learning_services(
            driver=driver,
            neo4j_adapter=neo4j_adapter,
            progress_backend=progress_backend,
            knowledge_backend=knowledge_backend,
            content_adapter=content_adapter,
            chunking_service=chunking_service,
            user_service=user_service,
            graph_intelligence=graph_intelligence,
            llm_service=llm_service,  # Pass LLM service for askesis RAG (Phase 1)
            _tasks_service=activity_services["tasks"],  # Placeholder: Phase 2.5 entity extraction
            _habits_service=activity_services["habits"],  # Placeholder: Phase 2.5 entity extraction
            _goals_service=activity_services["goals"],  # Placeholder: Phase 2.5 entity extraction
            _events_service=activity_services["events"],  # Placeholder: Phase 2.5 entity extraction
            event_bus=event_bus,  # Event-driven architecture
        )
        logger.info("✅ Learning services created")

        # Extract embeddings and vector search services for use by intelligence services and SearchRouter
        embeddings_service = learning_services["embeddings_service"]
        vector_search_service = learning_services["vector_search_service"]

        # Create Askesis core service (CRUD operations for AI assistant instances)
        from core.services.askesis.askesis_core_service import AskesisCoreService

        askesis_core_service = AskesisCoreService(backend=askesis_backend)
        logger.info("✅ Askesis core service created (CRUD operations for AI assistant)")

        # NOTE: Askesis service now created in PHASE 4 after intelligence_factory is available
        # This eliminates post-construction wiring (January 2026 architecture evolution)

        # ========================================================================
        # PHASE 3: INTELLIGENCE SERVICES (Real implementations replacing mock data)
        # ========================================================================
        # All 6 Activity Domain facades created in activity_services (access via facade.intelligence):
        # - tasks_intelligence → activity_services["tasks"].intelligence
        # - habits_intelligence → activity_services["habits"].intelligence
        # - events_intelligence → activity_services["events"].intelligence
        # - goals_intelligence → activity_services["goals"].intelligence
        # - choices_intelligence → activity_services["choices"].intelligence
        # - principles_intelligence → activity_services["principles"].intelligence
        #
        # Curriculum/meta intelligence services (no facades):

        # January 2026: KuIntelligenceService now created inside KuService facade
        # Access via learning_services["ku_service"].intelligence
        ku_intelligence = learning_services["ku_service"].intelligence

        # Cross-cutting AI services (askesis_ai, context_aware_ai) created below
        # in the AI SERVICES section - they REQUIRE LLM/embeddings
        askesis_ai = None
        context_aware_ai = None

        logger.info("✅ Intelligence services ready (6 Activity via facades, KU via facade)")
        # Note: choices_service and principle_service now come from activity_services

        # ========================================================================
        # AI SERVICES (Optional - ADR-030: Two-Tier Intelligence Design)
        # ========================================================================
        # Create AI services when LLM/embeddings are available
        # AI services are OPTIONAL - the app functions fully without them
        if llm_service and embeddings_service:
            from core.services.askesis_ai_service import AskesisAIService
            from core.services.choices.choices_ai_service import ChoicesAIService
            from core.services.context_aware_ai_service import ContextAwareAIService
            from core.services.events.events_ai_service import EventsAIService
            from core.services.goals.goals_ai_service import GoalsAIService
            from core.services.habits.habits_ai_service import HabitsAIService
            from core.services.ku.ku_ai_service import KuAIService
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
            ku_ai = KuAIService(
                backend=learning_services["ku_service"].core.backend,
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
            # NOTE: MocAIService removed (January 2026) - MOC is now KU-based

            # Wire AI services into Curriculum Domain facades (post-construction)
            learning_services["ku_service"].ai = ku_ai
            learning_services["learning_steps"].ai = ls_ai
            learning_services["learning_paths"].ai = lp_ai
            # NOTE: moc_service.ai removed (January 2026) - MOC is now KU-based

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

        # Create transcript processor service (OpenAI API key required)
        from core.config.credential_store import get_credential
        from core.services.ai_service import OpenAIService
        from core.services.transcript_processor_service import TranscriptProcessorService

        # Get required API key (already validated in PHASE 1)
        openai_api_key = get_credential("OPENAI_API_KEY", fallback_to_env=True)
        ai_service = OpenAIService(api_key=openai_api_key)

        transcript_processor = TranscriptProcessorService(
            backend=journals_backend,
            transcription_service=core_services["transcription"],
            ai_service=ai_service,  # REQUIRED - always available
            event_bus=event_bus,  # Event-driven architecture
        )
        logger.info("✅ Transcript processor service created")

        # Create journals core service for dedicated Journal node CRUD (January 2026)
        # Domain Separation: Journals (personal reflections) vs Assignments (file submission)
        from core.services.journals import JournalsCoreService

        journals_core_service = JournalsCoreService(
            backend=journals_backend,
            event_bus=event_bus,
            transcript_processor=transcript_processor,
        )
        logger.info("✅ Journals core service created (domain separation)")

        # Create journal feedback and project services for LLM processing
        from core.services.journals import JournalFeedbackService, JournalProjectService

        journal_feedback_service = JournalFeedbackService(
            openai_service=ai_service,
            anthropic_service=None,  # Only OpenAI configured for now
        )

        # Create journal project backend
        from core.models.journal import JournalProjectPure

        journal_projects_backend = UniversalNeo4jBackend[JournalProjectPure](
            driver=driver, label=NeoLabel.JOURNAL_PROJECT, entity_class=JournalProjectPure
        )

        journal_project_service = JournalProjectService(backend=journal_projects_backend)
        logger.info("✅ Journal feedback and project services created")

        # Load default transcript instructions from file
        # This creates/updates a reusable project that users can edit by modifying the file
        default_instructions_path = "/home/mike/skuel0/data/instructions - transcripts 0.md"
        default_project_uid = "jp.transcript_default"

        try:
            from pathlib import Path

            if Path(default_instructions_path).exists():
                # load_project_from_file handles both create and update
                result = await journal_project_service.load_project_from_file(
                    file_path=default_instructions_path,
                    user_uid="system",  # System-owned default project
                    project_uid=default_project_uid,
                    model="gpt-4o",
                )
                if result.is_ok:
                    logger.info(f"✅ Default transcript project loaded: {default_project_uid}")
                else:
                    logger.warning(f"Failed to load default transcript project: {result.error}")
            else:
                logger.warning(f"Default instructions file not found: {default_instructions_path}")
        except Exception as e:
            logger.warning(f"Failed to load default transcript project: {e}")

        # Create assignment submission and processing pipeline services (Phase 1)
        from core.services.assignments import (
            AssignmentProcessorService,
            AssignmentsCoreService,
            AssignmentsQueryService,
            AssignmentSubmissionService,
        )

        # Get storage path from environment (default: /tmp/skuel_assignments)
        storage_path = os.getenv("SKUEL_ASSIGNMENT_STORAGE", "/tmp/skuel_assignments")

        assignment_service = AssignmentSubmissionService(
            backend=assignments_backend, storage_path=storage_path, event_bus=event_bus
        )

        # Create assignments core service (content management: categories, tags, bulk operations)
        assignments_core_service = AssignmentsCoreService(
            backend=assignments_backend, event_bus=event_bus
        )

        assignment_processor = AssignmentProcessorService(
            assignment_service=assignment_service,
            transcription_service=core_services["transcription"],  # Simplified TranscriptionService
            transcript_processor=transcript_processor,  # For LLM formatting
            event_bus=event_bus,
        )

        # Create assignments query service (unified query interface)
        assignments_query_service = AssignmentsQueryService(
            assignment_backend=assignments_backend, event_bus=event_bus
        )

        logger.info("✅ Assignment submission and processing pipeline services created (Phase 1)")
        logger.info(
            "✅ Assignments core service created (content management: categories, tags, bulk ops)"
        )
        logger.info(
            "✅ Assignments query service created (unified query interface for all assignment types)"
        )

        # Create report service
        from core.services.report_service import ReportService

        report_service = ReportService(
            tasks_service=activity_services["tasks"],
            habits_service=activity_services["habits"],
            goals_service=activity_services["goals"],
            events_service=activity_services["events"],
            finance_service=core_services["finance"],
            choices_service=activity_services["choices"],
            principle_service=activity_services["principles"],
            transcript_processor=transcript_processor,  # ✅ TranscriptProcessorService - Layer 2 reporting
            user_service=user_service,  # Life path alignment
            ku_service=learning_services["ku_service"],  # Layer 0 reporting
            lp_service=learning_services["learning_paths"],  # Layer 0 reporting
            event_bus=event_bus,  # Phase 4: Event-driven report generation
        )
        logger.info("✅ Report service created")

        # =====================================================================
        # LIFEPATH SERVICE (Domain #14: The Destination)
        # "Everything flows toward the life path"
        # Vision capture → Alignment measurement → Recommendations
        # =====================================================================
        from core.services.lifepath import LifePathService

        lifepath_service = LifePathService(
            driver=driver,
            lp_service=learning_services["learning_paths"],
            ku_service=learning_services["ku_service"],
            user_service=user_service,
            llm_service=llm_service,
        )
        logger.info("✅ LifePath service created (Vision→Action bridge)")

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

        # Create MOC (Map of Content) service for knowledge organization
        # January 2026: MOC is now KU-based - MOC is a KU with ORGANIZES relationships
        from core.services.moc_service import MOCService

        # MOCService delegates to MocNavigationService which operates on KUs
        moc_service = MOCService(
            ku_service=learning_services["ku_service"],
            driver=driver,
        )
        logger.info("MOC service created (KU-based architecture - January 2026)")

        # Create advanced services
        advanced = _create_advanced_services(driver)
        await advanced["performance_optimization"].initialize()
        logger.info("✅ Advanced services created")

        # ========================================================================
        # PHASE 3: WIRE EVENT SUBSCRIBERS (Event-Driven Architecture)
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
            JournalCreated,
            JournalDeleted,
            JournalUpdated,
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

        async def invalidate_context_on_journal_event(event) -> None:
            """Invalidate user context when journal events occur."""
            logger.debug(
                f"Journal event received: {event.__class__.__name__} for user {event.user_uid}"
            )
            await user_service.invalidate_context(event.user_uid)

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

        # Subscribe to journal events
        event_bus.subscribe(JournalCreated, invalidate_context_on_journal_event)
        event_bus.subscribe(JournalUpdated, invalidate_context_on_journal_event)
        event_bus.subscribe(JournalDeleted, invalidate_context_on_journal_event)
        logger.info(
            "✅ UserService subscribed to journal events (JournalCreated, JournalUpdated, JournalDeleted)"
        )

        # Subscribe to transcription events for automatic journal creation
        from core.events.transcription_events import TranscriptionCompleted

        event_bus.subscribe(
            TranscriptionCompleted,
            journals_core_service.handle_transcription_completed,
        )
        logger.info(
            "✅ JournalsCoreService subscribed to TranscriptionCompleted "
            "(automatic journal creation from voice transcriptions)"
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
        # MOC is now KU-based - MOC changes are KU changes with ORGANIZES relationships
        # Context invalidation happens through KU events, not separate MOC events

        # ========================================================================
        # CROSS-DOMAIN EVENT SUBSCRIPTIONS (Phase 4: November 5, 2025)
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

        # Goal achievement → Goal recommendations (Phase 4)
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

        ku_service = learning_services["ku_service"]
        event_bus.subscribe(CalendarEventCompleted, ku_service.practice.handle_event_completed)
        logger.info(
            "✅ KuPracticeService subscribed to CalendarEventCompleted (automatic practice tracking)"
        )

        # Habit streak milestone → Achievement badges (Phase 4)
        from core.events.habit_events import HabitStreakMilestone

        habits_service = activity_services["habits"]
        event_bus.subscribe(
            HabitStreakMilestone, habits_service.achievements.handle_habit_streak_milestone
        )
        logger.info(
            "✅ HabitAchievementService subscribed to HabitStreakMilestone (badge awarding)"
        )

        # Learning path completion & knowledge mastery → Learning recommendations (Phase 4)
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

        # Multi-domain analytics → Track activity across all domains (Phase 4)
        from core.events.calendar_event_events import CalendarEventCompleted
        from core.events.habit_events import HabitCompleted
        from core.events.task_events import TaskCompleted

        analytics_service = advanced["cross_domain_analytics"]
        event_bus.subscribe(TaskCompleted, analytics_service.handle_task_completed)
        event_bus.subscribe(HabitCompleted, analytics_service.handle_habit_completed)
        event_bus.subscribe(CalendarEventCompleted, analytics_service.handle_event_completed)
        event_bus.subscribe(ExpenseCreated, analytics_service.handle_expense_created)
        event_bus.subscribe(ExpensePaid, analytics_service.handle_expense_paid)
        event_bus.subscribe(GoalCreated, analytics_service.handle_goal_created)
        event_bus.subscribe(KnowledgeMastered, analytics_service.handle_knowledge_mastered)
        event_bus.subscribe(LearningPathCompleted, analytics_service.handle_path_completed)
        event_bus.subscribe(JournalCreated, analytics_service.handle_journal_created)
        logger.info(
            "✅ CrossDomainAnalyticsService subscribed to 9 event types "
            "(Tasks, Habits, Events, Expenses, Goals, Knowledge, Paths, Journals)"
        )

        # Milestone achievements → Automatic report generation (Phase 4)
        from core.events.goal_events import GoalAchieved

        event_bus.subscribe(GoalAchieved, report_service.handle_goal_achieved)
        event_bus.subscribe(LearningPathCompleted, report_service.handle_learning_path_completed)
        event_bus.subscribe(HabitStreakMilestone, report_service.handle_habit_streak_milestone)
        logger.info(
            "✅ ReportService subscribed to 3 milestone events "
            "(GoalAchieved, LearningPathCompleted, HabitStreakMilestone) for auto-report generation"
        )

        # ========================================================================
        # SUBSTANCE TRACKING EVENT SUBSCRIPTIONS (October 17, 2025)
        # "Applied knowledge, not pure theory" - Track real-world knowledge application
        # ========================================================================

        from core.events.knowledge_events import (
            KnowledgeAppliedInTask,
            KnowledgeBuiltIntoHabit,
            KnowledgeBulkAppliedInTask,
            KnowledgeBulkBuiltIntoHabit,
            KnowledgeBulkInformedChoice,
            KnowledgeInformedChoice,
            KnowledgePracticedInEvent,
        )

        # Get KU service from learning services
        ku_service = learning_services["ku_service"]

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

        logger.info("✅ KuService subscribed to substance tracking events:")
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
        logger.info("✅ KuIntelligenceService subscribed to LearningStepCompleted")

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
        # MOC is now KU-based - intelligence operations happen through KU's ORGANIZES relationships
        # MapOfContentUpdated event type is deprecated - MOC changes are KU changes

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
            ku=learning_services["ku_service"],
            personalized_discovery=learning_services["personalized_discovery"],
            adaptive_sel=learning_services["adaptive_sel"],
            cross_domain=learning_services["cross_domain"],
            # Content
            journals=transcript_processor,  # TranscriptProcessorService
            journals_core=journals_core_service,  # JournalsCoreService - CRUD for Journal nodes
            transcript_processor=transcript_processor,
            journal_feedback=journal_feedback_service,  # LLM feedback on journals
            journal_projects=journal_project_service,  # Reusable LLM project templates
            # Note: audio_service removed (Dec 2025) - use transcription service directly
            # Assignments (Phase 1 - File submission pipeline)
            assignments=assignment_service,
            assignments_core=assignments_core_service,  # Content management (categories, tags, bulk ops)
            assignment_processor=assignment_processor,
            processing_pipeline=assignment_processor,  # Alias for assignment_processor
            assignments_query=assignments_query_service,  # Phase 3 - Unified assignment queries
            # System
            # Note: sync field removed (January 2026) - use unified_ingestion
            unified_ingestion=unified_ingestion,  # ADR-014: Merged MD + YAML ingestion
            calendar=calendar_service,
            system_service=system_service,
            transcription=core_services["transcription"],
            # User management
            user_service=core_services["user"],
            user_relationships=user_relationships,  # UserRelationshipService (pinning, following)
            graph_auth=graph_auth,  # Graph-native authentication (January 2026)
            context_service=context_service,  # Context-aware intelligence (NEW: 2025-11-18)
            # Content organization
            moc=moc_service,  # Maps of Content
            # Learning services
            learning=learning_services[
                "learning_paths"
            ],  # LpService facade (routes access .intelligence)
            user_progress=learning_services["user_progress"],
            # unified_progress DELETED (January 2026) - use user_progress
            learning_paths=learning_services["learning_paths"],
            learning_steps=learning_services["learning_steps"],  # NEW: Dedicated LS service
            learning_intelligence=learning_services["learning_intelligence"],
            askesis=None,  # Created in PHASE 4 after intelligence_factory (January 2026)
            askesis_core=askesis_core_service,  # Priority 1.1: CRUD operations for Askesis AI
            # Infrastructure
            graph_adapter=neo4j_adapter,
            event_bus=event_bus,
            driver=driver,  # Exposed for routes requiring UserContextBuilder
            neo4j_driver=driver,  # Alias for backward compatibility
            # GenAI services (Neo4j native - January 2026)
            embeddings_service=embeddings_service,
            vector_search_service=vector_search_service,
            # Reports
            reports=report_service,
            cross_domain_analytics=advanced["cross_domain_analytics"],  # Phase 5
            # LifePath (Domain #14: The Destination)
            lifepath=lifepath_service,
            # Orchestration (Activity Domains already assigned above)
            goal_task_generator=orchestration["goal_task_generator"],
            habit_event_scheduler=orchestration["habit_event_scheduler"],
            # Advanced
            calendar_optimization=advanced["calendar_optimization"],
            jupyter_sync=advanced["jupyter_sync"],
            performance_optimization=advanced["performance_optimization"],
            # Intelligence (10 domains)
            # Activity Domains (6) - ALL via unified activity_services facades
            tasks_intelligence=activity_services["tasks"].intelligence,
            habits_intelligence=activity_services["habits"].intelligence,
            events_intelligence=activity_services["events"].intelligence,
            goals_intelligence=activity_services["goals"].intelligence,
            principles_intelligence=activity_services["principles"].intelligence,
            choices_intelligence=activity_services["choices"].intelligence,
            # Curriculum/meta (no facades)
            ku_intelligence=ku_intelligence,
            # Cross-cutting AI services (require LLM/embeddings)
            askesis_ai=askesis_ai,
            context_aware_ai=context_aware_ai,
        )

        # ========================================================================
        # PHASE 4: CREATE USER CONTEXT INTELLIGENCE (13-Domain Architecture)
        # ========================================================================
        # UserContextIntelligence = UserContext + 13 Domain Services
        # This is THE service that answers: "What should I work on next?"
        #
        # The 13 Domains:
        # - Activity Domains (6): Tasks, Goals, Habits, Events, Choices, Principles
        # - Curriculum Domains (3): KU, LS, LP
        # - Processing Domains (3): Assignments, Journals, Reports
        # - Temporal Domain (1): Calendar

        from core.services.assignments import AssignmentRelationshipService
        from core.services.journals import JournalRelationshipService
        from core.services.report_relationship_service import ReportRelationshipService
        from core.services.user.intelligence import UserContextIntelligenceFactory

        # Create processing domain relationship services (Direct Driver pattern)
        assignment_relationship_service = AssignmentRelationshipService(driver)
        journal_relationship_service = JournalRelationshipService(driver)
        report_relationship_service = ReportRelationshipService(driver)
        logger.info(
            "✅ Processing domain relationship services created (Assignments, Journals, Reports)"
        )

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
            ku=learning_services["ku_service"].graph,  # KuGraphService
            ls=learning_services[
                "learning_steps"
            ].relationships,  # UnifiedRelationshipService (January 2026)
            lp=learning_services["learning_paths"].relationships,
            # Processing Domains (3)
            assignments=assignment_relationship_service,
            journals=journal_relationship_service,
            reports=report_relationship_service,
            # Temporal Domain (1)
            calendar=calendar_service,
            # Optional: Vector search for semantic enhancements (Phase 1 - January 2026)
            vector_search_service=vector_search_service,
        )
        services.context_intelligence = context_intelligence_factory
        logger.info("✅ UserContextIntelligence factory created (13 domain services wired)")

        # Wire intelligence factory to UserService (post-construction wiring)
        user_service.intelligence_factory = context_intelligence_factory
        logger.info("✅ UserService wired with intelligence factory")

        # Wire intelligence factory to UserContextService (post-construction wiring)
        # This enables get_context_summary() to use factory.create() for intelligence queries
        context_service.intelligence_factory = context_intelligence_factory
        logger.info("✅ UserContextService wired with intelligence factory")

        # Create Askesis service NOW with intelligence_factory as REQUIRED parameter
        # (January 2026: Moved from _create_learning_services() to eliminate post-wiring)
        from core.services.askesis_service import AskesisService

        askesis_service = AskesisService(
            graph_intelligence_service=learning_services["graph_intelligence"],
            user_service=user_service,
            llm_service=learning_services["llm_service"],
            embeddings_service=learning_services["embeddings_service"],
            knowledge_service=learning_services["ku_service"],
            tasks_service=activity_services["tasks"],
            goals_service=activity_services["goals"],
            habits_service=activity_services["habits"],
            events_service=activity_services["events"],
            intelligence_factory=context_intelligence_factory,  # REQUIRED (not post-wired)
        )
        services.askesis = askesis_service
        logger.info("✅ Askesis service created with intelligence_factory (13-domain synthesis)")

        # ========================================================================
        # PHASE 5: CREATE SEARCH ROUTER (One Path Forward, January 2026)
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
