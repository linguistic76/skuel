"""Main bootstrap orchestration — compose_services() wires everything together."""

__version__ = "4.0"  # Entity type + cross-cutting system architecture

import os
from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.ports import EventBusOperations
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from services_bootstrap._activity_services import _create_activity_services
from services_bootstrap._ai_wiring import _wire_ai_services
from services_bootstrap._backends import create_all_backends
from services_bootstrap._container import Services
from services_bootstrap._core_services import (
    _create_advanced_services,
    _create_core_services,
    _create_orchestration_services,
)
from services_bootstrap._event_wiring import _wire_event_subscribers
from services_bootstrap._intelligence_hub import _create_intelligence_hub
from services_bootstrap._learning_services import _create_learning_services

if TYPE_CHECKING:
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics

logger = get_logger("skuel.bootstrap")


async def compose_services(
    neo4j_adapter: Any,
    event_bus: EventBusOperations | None = None,
    config: Any = None,
    prometheus_metrics: "PrometheusMetrics | None" = None,
    metrics_cache: Any = None,
) -> Result[Services]:
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
        Result[Services]: Success with wired services or failure with detailed error.
        SearchRouter is available via services.search_router.

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

        # Create vector indexes for semantic search (FULL tier only — ADR-043)
        # CORE tier has no embeddings, so vector indexes are unnecessary
        if tier.ai_enabled:
            vector_labels = [
                "Entity",  # Base label — covers all entity types via multi-label
                "ContentChunk",  # RAG chunks
            ]
            vector_result = await schema_manager.sync_vector_indexes(
                entity_labels=vector_labels, dimension=1024, similarity="cosine"
            )
            if vector_result.is_ok:
                created = vector_result.value.get("created", [])
                logger.info(
                    f"✅ Vector indexes synced: {', '.join(created) if created else 'all exist'}"
                )
            else:
                logger.warning(f"⚠️ Vector index sync had issues: {vector_result.error}")
        else:
            logger.info("⏭️  Vector indexes skipped (intelligence tier: CORE)")

        # Drop stale indexes from removed labels
        stale_result = await schema_manager.drop_stale_indexes()
        if stale_result.is_ok:
            dropped = stale_result.value.get("dropped", [])
            if dropped:
                logger.info(f"✅ Dropped stale indexes: {', '.join(dropped)}")

        # Sync domain indexes (UID, user_uid, status, date, composite)
        domain_idx_result = await schema_manager.sync_domain_indexes()
        if domain_idx_result.is_ok:
            created = domain_idx_result.value.get("created", [])
            failed = domain_idx_result.value.get("failed", [])
            logger.info(
                f"✅ Domain indexes synced: {len(created)} created/verified"
                + (f", {len(failed)} failed" if failed else "")
            )
        else:
            logger.warning(f"⚠️ Domain index sync had issues: {domain_idx_result.error}")

        # Sync full-text indexes (Cypher-first search foundation — always created)
        fulltext_result = await schema_manager.sync_fulltext_indexes()
        if fulltext_result.is_ok:
            created = fulltext_result.value.get("created", [])
            failed = fulltext_result.value.get("failed", [])
            logger.info(
                f"✅ Fulltext indexes synced: {len(created)} created/verified"
                + (f", {len(failed)} failed" if failed else "")
            )
        else:
            logger.warning(f"⚠️ Fulltext index sync had issues: {fulltext_result.error}")

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
            "OPENAI_API_KEY": "OpenAI API (optional - enables LLM chat, content processing, and AI features)",
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
        # CREATE DOMAIN BACKENDS (100% Dynamic Pattern)
        # ========================================================================
        backends = create_all_backends(driver, prometheus_metrics=prometheus_metrics)

        # Unpack backends for readability
        tasks_backend = backends["tasks_backend"]
        events_backend = backends["events_backend"]
        habits_backend = backends["habits_backend"]
        habit_completions_backend = backends["habit_completions_backend"]
        goals_backend = backends["goals_backend"]
        finance_backend = backends["finance_backend"]
        invoice_backend = backends["invoice_backend"]
        transcription_backend = backends["transcription_backend"]
        users_backend = backends["users_backend"]
        ps_backend = backends["ps_backend"]
        ku_backend = backends["ku_backend"]
        principles_backend = backends["principles_backend"]
        # reflection_backend shelved (2026-03-28)
        choices_backend = backends["choices_backend"]
        progress_backend = backends["progress_backend"]
        submissions_backend = backends["submissions_backend"]
        activity_report_backend = backends["activity_report_backend"]
        askesis_backend = backends["askesis_backend"]

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
        # ACTIVITY KNOWLEDGE INTELLIGENCE (shared singleton for all 6 domains)
        # ========================================================================
        # Created here (not in _create_learning_services) to break circular
        # dependency: activity_services needs this, learning_services needs activity_services.
        from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
        from core.models.entity import Entity
        from core.services.knowledge import ActivityKnowledgeIntelligenceService

        activity_entity_backend = UniversalNeo4jBackend[Entity](
            driver, NeoLabel.ENTITY, Entity, base_label=NeoLabel.ENTITY
        )
        activity_knowledge_intelligence = ActivityKnowledgeIntelligenceService(
            backend=activity_entity_backend,
            graph_intelligence_service=graph_intelligence,
        )
        logger.info("✅ ActivityKnowledgeIntelligenceService created")

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
            # reflection_backend removed — PrinciplesReflectionService shelved (2026-03-28)
            graph_intelligence=graph_intelligence,
            event_bus=event_bus,
            ku_inference_service=ku_inference_service,
            analytics_engine=analytics_engine,
            ku_generation_service=ku_generation_service,
            insight_store=insight_store,
            activity_knowledge_intelligence=activity_knowledge_intelligence,
        )
        logger.info("✅ Activity Domain services created (6 facades with embedded intelligence)")

        # Get Deepgram API key for transcription service
        from core.config.credential_store import get_credential

        deepgram_api_key = get_credential("DEEPGRAM_API_KEY", fallback_to_env=True)

        # Create core services (Finance, Transcription only - Activity Domains in activity_services)
        core_services = _create_core_services(
            finance_backend=finance_backend,
            invoice_backend=invoice_backend,
            transcription_backend=transcription_backend,
            user_service=user_service,
            deepgram_api_key=deepgram_api_key,
            event_bus=event_bus,
        )
        logger.info("✅ Core services created (with event bus + Deepgram wiring)")

        # GRAPH-NATIVE: Wire analytics engine with UnifiedRelationshipService
        # tasks_service comes from activity_services (unified Activity Domain creation)
        tasks_service = activity_services["tasks"]
        analytics_engine.relationship_service = tasks_service.relationships
        logger.info("✅ AnalyticsEngine wired with UnifiedRelationshipService")

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

        # Per-user bulk upload service (wraps UnifiedIngestionService)
        from core.services.ingestion.user_upload_service import UserUploadService

        user_upload_service = UserUploadService(
            ingestion_service=unified_ingestion,
            user_vaults_base=config.vault.user_vaults_path,
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
            except (
                Exception
            ) as e:  # safety-net: service bootstrap must report initialization failures
                logger.error(f"Failed to initialize LLM service: {e}")
                logger.warning("⚠️ LLM service disabled - continuing with basic features")

        # Create learning services (graph_intelligence already created above)
        learning_services = _create_learning_services(
            driver=driver,
            progress_backend=progress_backend,
            knowledge_backend=ps_backend,
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
            activity_knowledge_intelligence=activity_knowledge_intelligence,
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
                    "   Worker handles: 6 Activity + 7 Curriculum entity types + content chunks"
                )
            except (
                Exception
            ) as e:  # safety-net: service bootstrap must report initialization failures
                logger.warning(f"Failed to initialize embedding background worker: {e}")
                logger.warning("   Embeddings will only be generated during ingestion")
        else:
            logger.info("⏭️  Embedding background worker skipped (embeddings_service not available)")

        # ========================================================================
        # CREATE LATERAL RELATIONSHIP SERVICES (January 2026)
        # ========================================================================
        # Core lateral relationships infrastructure - foundational graph architecture
        # Enables explicit modeling of sibling, cousin, dependency, and semantic relationships
        # across all 8 hierarchical domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, PS, LP)

        from adapters.persistence.neo4j.domain_backends import LateralRelationshipBackend
        from core.services.lateral_relationships import LateralRelationshipService

        # Create backend + service for lateral relationships (domain-agnostic)
        # Ownership verification happens at route level via domain_service param
        lateral_backend = LateralRelationshipBackend(executor=query_executor)
        lateral_service = LateralRelationshipService(backend=lateral_backend)
        logger.info("✅ LateralRelationshipService created (9 domains, ownership at route level)")

        # Create Askesis core service (CRUD operations for AI assistant instances)
        from core.services.askesis.askesis_core_service import AskesisCoreService

        askesis_core_service = AskesisCoreService(backend=askesis_backend)
        logger.info("✅ Askesis core service created (CRUD operations)")

        # NOTE: Askesis service now created in after intelligence_factory is available
        # This eliminates post-construction wiring (January 2026 architecture evolution)

        # Wire AI services into domain facades (ADR-030: Two-Tier Intelligence)
        askesis_ai, context_aware_ai = _wire_ai_services(
            llm_service=llm_service,
            embeddings_service=embeddings_service,
            _activity_services=activity_services,
            learning_services=learning_services,
            user_service=user_service,
            graph_intelligence=graph_intelligence,
        )

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

        # AdminStatsService: cross-domain stats for admin dashboard
        from core.services.admin_stats_service import AdminStatsService

        # Create visualization service (Chart.js/Vis.js/Gantt adapters)
        from core.services.visualization_service import VisualizationService

        visualization_service = VisualizationService(
            tasks_service=activity_services["tasks"],
            habits_service=activity_services["habits"],
            goals_service=activity_services["goals"],
            calendar_service=calendar_service,
        )
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

        # Create report and exercise services
        from adapters.persistence.neo4j.domain_backends import (
            ExerciseBackend,
            ExerciseReportBackend,
        )
        from core.models.exercises.exercise import Exercise
        from core.models.report.exercise_report import ExerciseReport
        from core.services.exercises import ExerciseService
        from core.services.report.report_mastery_service import ReportMasteryService

        report_mastery_service = ReportMasteryService(
            submissions_backend=submissions_backend,
            ku_interaction_service=learning_services["ps"].mastery,
        )
        logger.info("✅ ReportMasteryService created")

        # UnifiedLLMCaller: routes to OpenAI or Anthropic based on model prefix
        from core.services.llm_caller import UnifiedLLMCaller
        from core.services.report import ExerciseReportService

        llm_caller = None
        if ai_service:
            llm_caller = UnifiedLLMCaller(
                openai=ai_service,
                anthropic=None,  # Only OpenAI configured for now
            )
            logger.info("✅ UnifiedLLMCaller created")

        exercise_report_backend = ExerciseReportBackend(
            driver=driver,
            label=NeoLabel.EXERCISE_REPORT,
            entity_class=ExerciseReport,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )

        # ExerciseReportService: None in CORE tier — report generation requires AI
        exercise_report_service = None
        if llm_caller:
            exercise_report_service = ExerciseReportService(
                llm_caller=llm_caller,
                backend=exercise_report_backend,  # Creates ExerciseReport entity + REPORT_FOR relationship
                ku_interaction_service=learning_services["ps"].mastery,  # Closes mastery loop
                report_mastery_service=report_mastery_service,
            )

        exercise_backend = ExerciseBackend(
            driver=driver,
            label=NeoLabel.EXERCISE,
            entity_class=Exercise,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )

        exercise_service = ExerciseService(backend=exercise_backend)

        # ResourceService: curated content (books, talks, films, podcasts)
        from adapters.persistence.neo4j.domain_backends import ResourceBackend
        from core.models.resource.resource import Resource as ResourceModel
        from core.services.resource_service import ResourceService

        resource_backend = ResourceBackend(
            driver=driver,
            label=NeoLabel.RESOURCE,
            entity_class=ResourceModel,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )
        resource_service = ResourceService(backend=resource_backend)

        logger.info("✅ Report, exercise, and resource services created")

        # Create revised exercise service (five-phase learning loop)
        from adapters.persistence.neo4j.domain_backends import RevisedExerciseBackend
        from core.models.exercises.revised_exercise import RevisedExercise
        from core.services.revised_exercises import RevisedExerciseService

        revised_exercise_backend = RevisedExerciseBackend(
            driver=driver,
            label=NeoLabel.REVISED_EXERCISE,
            entity_class=RevisedExercise,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )
        revised_exercise_service = RevisedExerciseService(
            backend=revised_exercise_backend, event_bus=event_bus
        )
        logger.info("✅ RevisedExerciseService created (five-phase learning loop)")

        # Create form services (general-purpose form system)
        from adapters.persistence.neo4j.domain_backends import (
            FormSubmissionBackend,
            FormTemplateBackend,
        )
        from core.models.forms.form_submission import FormSubmission
        from core.models.forms.form_template import FormTemplate
        from core.services.forms import FormSubmissionService, FormTemplateService

        form_template_backend = FormTemplateBackend(
            driver=driver,
            label=NeoLabel.FORM_TEMPLATE,
            entity_class=FormTemplate,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )
        form_template_service = FormTemplateService(
            backend=form_template_backend, event_bus=event_bus
        )

        form_submission_backend = FormSubmissionBackend(
            driver=driver,
            label=NeoLabel.FORM_SUBMISSION,
            entity_class=FormSubmission,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )
        form_submission_service = FormSubmissionService(
            backend=form_submission_backend,
            event_bus=event_bus,
            form_template_service=form_template_service,
        )
        logger.info("✅ Form services created (FormTemplate + FormSubmission)")

        # Create interaction service (User Interaction Contract — EntityType.INTERACTION)
        from adapters.persistence.neo4j.domain_backends import InteractionBackend
        from core.models.interaction.interaction import Interaction
        from core.services.interaction import InteractionService

        interaction_backend = InteractionBackend(
            driver=driver,
            label=NeoLabel.INTERACTION,
            entity_class=Interaction,
            prometheus_metrics=prometheus_metrics,
            base_label=NeoLabel.ENTITY,
        )
        interaction_service = InteractionService(
            backend=interaction_backend,
            event_bus=event_bus,
        )
        logger.info("✅ InteractionService created (User Interaction Contract)")

        # Create group service (ADR-040: Teacher Exercise Workflow)
        from adapters.persistence.neo4j.domain_backends import GroupBackend
        from core.models.group.group import Group
        from core.services.groups import GroupService

        group_backend = GroupBackend(
            driver=driver,
            label=NeoLabel.GROUP,
            entity_class=Group,
            prometheus_metrics=prometheus_metrics,
        )

        group_service = GroupService(backend=group_backend, event_bus=event_bus)
        logger.info("✅ GroupService created (ADR-040)")

        # Create teacher review service (ADR-040: Teacher Exercise Workflow)
        from core.services.report.teacher_review_service import TeacherReviewService

        teacher_review_service = TeacherReviewService(
            submissions_backend=submissions_backend,
            exercise_backend=exercise_backend,
            group_backend=group_backend,
            ku_interaction_service=learning_services["ps"].mastery,
            report_mastery_service=report_mastery_service,
            event_bus=event_bus,
        )
        logger.info("✅ TeacherReviewService created (ADR-040)")

        # Create notification service
        from adapters.persistence.neo4j.domain_backends import NotificationBackend
        from core.services.notifications.notification_service import NotificationService

        notification_backend = NotificationBackend(executor=query_executor)
        notification_service = NotificationService(executor=notification_backend)
        logger.info("✅ NotificationService created")

        # Seed default transcript exercise (idempotent create/update)
        seed_result = await exercise_service.seed_default_exercise()
        if seed_result.is_ok:
            logger.info("Default transcript exercise loaded")
        else:
            logger.warning(f"Default transcript exercise: {seed_result.error}")

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
            backend=submissions_backend,
            storage_path=storage_path,
            event_bus=event_bus,
            interaction_service=interaction_service,
        )

        # Create sharing backend + service (cross-domain, queries :Entity nodes)
        from adapters.persistence.neo4j.domain_backends import SharingBackend
        from core.models.entity import Entity
        from core.services.sharing import UnifiedSharingService

        sharing_backend = SharingBackend(
            driver, NeoLabel.ENTITY, Entity, prometheus_metrics=prometheus_metrics
        )
        unified_sharing_service = UnifiedSharingService(backend=sharing_backend)

        # Wire sharing into form submission service (created earlier without sharing)
        form_submission_service.sharing_service = unified_sharing_service

        # Create Submissions core service (content management: categories, tags, bulk operations)
        submissions_core_service = SubmissionsCoreService(
            backend=submissions_backend,
            event_bus=event_bus,
            sharing_service=unified_sharing_service,
        )

        # LIFEPATH SERVICE (Domain #14: The Destination)
        # "Everything flows toward the life path"
        # Vision capture → Alignment measurement → Recommendations
        # =====================================================================
        from core.services.lifepath import LifePathService

        lifepath_service = LifePathService(
            executor=query_executor,
            lp_service=learning_services["learning_paths"],
            ku_service=learning_services["ps"],
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
            ku_service=learning_services["ps"],
            ps_service=learning_services["ps"],
            lp_service=learning_services["learning_paths"],
            # Meta Domains (3)
            report_service=submissions_service,  # For metadata updates
            analytics_service=None,  # Not needed for extraction
            calendar_service=None,  # Not needed for extraction
            # The Destination (+1)
            lifepath_service=lifepath_service,
        )
        logger.info("✅ Submission activity extractor created (DSL journal → entity extraction)")

        # Create instruction resolver (stateless — works without AI)
        from core.services.output import InstructionResolver

        instruction_resolver = InstructionResolver()
        logger.info("✅ InstructionResolver created")

        # Journal input service (CRUD + file upload → JeInput entities)
        from adapters.persistence.neo4j.domain_backends import JournalInputBackend
        from core.models.journal.je_input import JeInput
        from core.services.journal import JournalInputService

        journal_storage = os.getenv("SKUEL_JOURNAL_STORAGE", "/tmp/skuel_journals")
        journal_input_backend = JournalInputBackend(
            driver, NeoLabel.JE_INPUT, JeInput, base_label=NeoLabel.ENTITY
        )
        journal_input_service = JournalInputService(
            backend=journal_input_backend,
            storage_base=journal_storage,
            event_bus=event_bus,
        )
        logger.info(f"✅ JournalInputService created (storage: {journal_storage})")

        # Journal output service (LLM processing → JeOutput entities)
        from adapters.persistence.neo4j.domain_backends import JournalOutputBackend
        from core.models.journal.je_output import JeOutput
        from core.services.journal import JournalOutputService

        journal_output_backend = JournalOutputBackend(
            driver, NeoLabel.JE_OUTPUT, JeOutput, base_label=NeoLabel.ENTITY
        )
        journal_output_service = None
        if llm_caller:
            journal_output_service = JournalOutputService(
                llm_caller=llm_caller,
                instruction_resolver=instruction_resolver,
                backend=journal_output_backend,
                storage_base=journal_storage,
                event_bus=event_bus,
            )
            logger.info(f"✅ JournalOutputService created (storage: {journal_storage})")
        else:
            logger.info("⏭️  JournalOutputService skipped (intelligence tier: CORE)")

        # Create batch transcription service (Tier 1: audio → txt)
        from core.services.transcription import BatchTranscriptionService

        batch_transcription = BatchTranscriptionService(
            deepgram_adapter=core_services["deepgram_adapter"],
            max_concurrent=5,
        )
        logger.info("✅ BatchTranscriptionService created (Tier 1: audio → txt)")

        # Create batch processing service (Tier 2: txt → md via LLM)
        from core.services.transcription import BatchProcessingService

        batch_processing = None
        if journal_output_service:
            batch_processing = BatchProcessingService(
                output_generator=journal_output_service,
                instruction_resolver=instruction_resolver,
                max_concurrent=3,
            )
            logger.info("✅ BatchProcessingService created (Tier 2: txt → md)")
        else:
            logger.info("⏭️  BatchProcessingService skipped (requires JournalOutputService)")

        submissions_processor = SubmissionsProcessingService(
            submission_service=submissions_service,
            transcription_service=core_services["transcription"],  # Simplified TranscriptionService
            content_enrichment=content_enrichment,  # For LLM formatting
            activity_extractor=activity_extractor,  # DSL entity extraction
            journal_output_service=journal_output_service,  # JournalOutputService
            event_bus=event_bus,
        )

        # Create Submissions search service (unified query interface)
        submissions_search_service = SubmissionsSearchService(
            submissions_backend=submissions_backend, event_bus=event_bus
        )

        logger.info("✅ Submissions pipeline services created")
        logger.info(
            "✅ Submissions core service created (content management: categories, tags, bulk ops)"
        )
        logger.info(
            "✅ Submissions search service created (unified query interface for all submission types)"
        )

        # Create progress report generator and schedule service
        from core.models.submissions.report_schedule import ReportSchedule
        from core.services.report.progress_report_generator import ProgressReportGenerator
        from core.services.report.progress_schedule_service import ProgressScheduleService

        progress_schedule_backend = UniversalNeo4jBackend[ReportSchedule](
            driver, NeoLabel.REPORT_SCHEDULE, ReportSchedule, prometheus_metrics=prometheus_metrics
        )
        progress_schedule_service = ProgressScheduleService(backend=progress_schedule_backend)

        # Create ActivityReportService (processor-neutral ActivityReport CRUD)
        from core.services.report.activity_report_service import ActivityReportService
        from core.services.report.review_queue_service import ReviewQueueService

        activity_report_service = ActivityReportService(
            backend=activity_report_backend,
            context_builder=context_builder,
            event_bus=event_bus,
        )
        review_queue_service = ReviewQueueService(executor=query_executor)
        logger.info("✅ ActivityReportService + ReviewQueueService created")

        progress_generator = ProgressReportGenerator(
            executor=query_executor,
            activity_report_service=activity_report_service,
            context_builder=context_builder,
            openai_service=ai_service,
            insight_store=insight_store,
            event_bus=event_bus,
            analytics_service=None,  # Post-wired below after analytics_service creation
            knowledge_intelligence=activity_knowledge_intelligence,
        )

        # Create progress report background worker (February 2026)
        # Worker checks hourly for due schedules and generates ActivityReport Entity nodes
        from core.services.background.progress_report_worker import ProgressReportWorker

        progress_report_worker = ProgressReportWorker(
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
            ku_service=learning_services["ps"],  # Layer 0 reporting
            lp_service=learning_services["learning_paths"],  # Layer 0 reporting
            event_bus=event_bus,  # Event-driven report generation
        )
        logger.info("✅ Analytics service created")

        # Post-wire analytics_service into progress generator (created before analytics)
        progress_generator.analytics_service = analytics_service
        logger.info(
            "✅ ProgressReportGenerator wired with AnalyticsService + knowledge intelligence"
        )

        # =====================================================================
        # Create orchestration services (GoalTaskGenerator and HabitEventScheduler only)
        orchestration = _create_orchestration_services(
            goals_backend=goals_backend,
            tasks_backend=tasks_backend,
            habits_backend=habits_backend,
            events_backend=events_backend,
        )
        logger.info("✅ Orchestration services created")

        from core.orchestrator.profile_orchestrator import ProfileOrchestrator

        profile_orchestrator = ProfileOrchestrator(
            tasks_service=activity_services["tasks"],
            goals_service=activity_services["goals"],
            habits_service=activity_services["habits"],
            events_service=activity_services["events"],
            choices_service=activity_services["choices"],
            principles_service=activity_services["principles"],
            exercise_report_service=exercise_report_service,
            activity_report_service=activity_report_service,
            sharing_service=unified_sharing_service,
            ps_service=learning_services["ps"],
            exercises_service=exercise_service,
            context_intelligence=context_service.intelligence_factory,
        )
        logger.info("✅ Profile Orchestrator created")

        from core.orchestrator.submissions_orchestrator import SubmissionsOrchestrator

        submissions_orchestrator = SubmissionsOrchestrator(
            submissions_service=submissions_service,
            exercises_service=exercise_service,
            submissions_search_service=submissions_search_service,
            submissions_core_service=submissions_core_service,
            teacher_review_service=teacher_review_service,
            user_service=user_service,
            activity_report_service=activity_report_service,
            revised_exercise_service=revised_exercise_service,
        )
        logger.info("✅ Submissions Orchestrator created")

        from core.orchestrator.explore_orchestrator import ExploreOrchestrator

        explore_orchestrator = ExploreOrchestrator(
            ku_service=learning_services["atomic_ku_service"],
            ps_service=learning_services["ps"],
            user_relationship_service=user_relationships,
            exercises_service=exercise_service,
            submissions_search_service=submissions_search_service,
        )
        logger.info("✅ Explore Orchestrator created")

        from core.orchestrator.library_orchestrator import LibraryOrchestrator

        library_orchestrator = LibraryOrchestrator(
            exercises_service=exercise_service,
            resource_service=resource_service,
            ku_service=learning_services["atomic_ku_service"],
            ps_service=learning_services["ps"],
            submissions_service=submissions_service,
            user_relationship_service=user_relationships,
        )
        logger.info("✅ Library Orchestrator created")

        admin_stats_service = AdminStatsService(query_executor=query_executor)

        from core.orchestrator.teacher_orchestrator import TeacherOrchestrator

        teacher_orchestrator = TeacherOrchestrator(
            teacher_review_service=teacher_review_service,
            admin_stats=admin_stats_service,
        )
        logger.info("✅ Teacher Orchestrator created")

        from core.orchestrator.admin_orchestrator import AdminOrchestrator

        admin_orchestrator = AdminOrchestrator(
            user_service=user_service,
            admin_stats=admin_stats_service,
            system_service=system_service,
        )
        logger.info("✅ Admin Orchestrator created")

        from core.orchestrator.journal_orchestrator import JournalOrchestrator

        journal_orchestrator = JournalOrchestrator(
            journal_input_service=journal_input_service,
            journal_output_service=journal_output_service,
            exercises_service=exercise_service,
            user_service=user_service,
        )
        logger.info("✅ Journal Orchestrator created")

        from core.orchestrator.activity_review_orchestrator import ActivityReviewOrchestrator

        activity_review_orchestrator = ActivityReviewOrchestrator(
            activity_report=activity_report_service,
            user_service=user_service,
            review_queue=review_queue_service,
            context_builder=context_builder,
        )
        logger.info("✅ Activity Review Orchestrator created")

        from core.orchestrator.pathways_orchestrator import PathwaysOrchestrator

        pathways_orchestrator = PathwaysOrchestrator(
            lp_service=learning_services["learning_paths"],
            user_progress=learning_services["user_progress"],
        )
        logger.info("✅ Pathways Orchestrator created")

        from core.orchestrator.lateral_relationships_orchestrator import (
            LateralRelationshipsOrchestrator,
        )

        lateral_orchestrator = LateralRelationshipsOrchestrator(
            lateral_service=lateral_service,
            tasks_service=activity_services["tasks"],
            goals_service=activity_services["goals"],
            habits_service=activity_services["habits"],
            events_service=activity_services["events"],
            choices_service=activity_services["choices"],
            principles_service=activity_services["principles"],
        )
        logger.info("✅ Lateral Relationships Orchestrator created")

        # Create advanced services
        advanced = _create_advanced_services(driver, query_executor=query_executor)
        await advanced["performance_optimization"].initialize()
        logger.info("✅ Advanced services created")

        from core.orchestrator.calendar_optimization_orchestrator import (
            CalendarOptimizationOrchestrator,
        )

        calendar_optimization_orchestrator = CalendarOptimizationOrchestrator(
            calendar_service=advanced["calendar_optimization"],
            tasks_service=activity_services["tasks"],
            events_service=activity_services["events"],
        )
        logger.info("✅ Calendar Optimization Orchestrator created")

        # Wire orchestration services into context_service
        context_service.goal_task_generator = orchestration["goal_task_generator"]
        context_service.habits_service = activity_services["habits"]
        logger.info("✅ UserContextService wired with GoalTaskGenerator and HabitsService")

        # Post-wire goals_service into habits (cross-domain dependency)
        activity_services["habits"].goals_service = activity_services["goals"]
        # HabitsGoalAnalyticsService shelved (2026-03-28)
        logger.info("✅ HabitsService wired with GoalsService")

        # Post-wire habits_service into goals intelligence (cross-domain dependency)
        activity_services["goals"].intelligence.habits_service = activity_services["habits"]
        logger.info("✅ GoalsIntelligenceService wired with HabitsService")

        # Wire all event subscribers (context invalidation + cross-domain + intelligence)
        _wire_event_subscribers(
            event_bus=event_bus,
            user_service=user_service,
            activity_services=activity_services,
            learning_services=learning_services,
            submissions_core_service=submissions_core_service,
            notification_service=notification_service,
            advanced=advanced,
            analytics_service=analytics_service,
            submissions_backend=submissions_backend,
            insight_store=insight_store,
            group_backend=group_backend,
        )
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
            # Curriculum
            ku=learning_services["atomic_ku_service"],
            knowledge_domains=learning_services["knowledge_domains"],
            resource=resource_service,
            activity_knowledge_intelligence=learning_services["activity_knowledge_intelligence"],
            cross_domain=learning_services["cross_domain"],
            # Content
            content_enrichment=content_enrichment,
            report_mastery=report_mastery_service,  # Explicit mastery propagation
            exercise_report=exercise_report_service,  # LLM report on submissions/journals
            exercises=exercise_service,  # Reusable LLM instruction templates
            revised_exercises=revised_exercise_service,  # Five-phase learning loop revisions
            form_templates=form_template_service,  # General-purpose form templates
            form_submissions=form_submission_service,  # User form submissions
            interaction_service=interaction_service,  # User Interaction Contract
            journal_input=journal_input_service,  # JournalInputService
            journal_generator=journal_output_service,  # JournalOutputService
            # Batch transcription/processing (March 2026)
            batch_transcription=batch_transcription,
            batch_processing=batch_processing,
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
            # Progress report (February 2026)
            progress_report_generator=progress_generator,
            progress_schedule=progress_schedule_service,
            # Activity report + review queue (March 2026 refactor)
            activity_report=activity_report_service,
            review_queue=review_queue_service,
            # System
            # Note: sync field removed (January 2026) - use unified_ingestion
            unified_ingestion=unified_ingestion,  # ADR-014: Merged MD + YAML ingestion
            user_upload_service=user_upload_service,  # Per-user bulk upload
            calendar=calendar_service,
            system_service=system_service,
            admin_stats=admin_stats_service,
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
            lp=learning_services["learning_paths"],  # ku, ps, lp short-name consistency
            ps=learning_services["ps"],  # ku, ps, lp short-name consistency
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
            progress_report_worker=progress_report_worker,
            # Analytics
            analytics=analytics_service,
            cross_domain_analytics=advanced["cross_domain_analytics"],
            # LifePath (Domain #14: The Destination)
            lifepath=lifepath_service,
            # Orchestration (Activity Domains already assigned above)
            goal_task_generator=orchestration["goal_task_generator"],
            habit_event_scheduler=orchestration["habit_event_scheduler"],
            admin_orchestrator=admin_orchestrator,
            profile_orchestrator=profile_orchestrator,
            submissions_orchestrator=submissions_orchestrator,
            explore_orchestrator=explore_orchestrator,
            library_orchestrator=library_orchestrator,
            teacher_orchestrator=teacher_orchestrator,
            journal_orchestrator=journal_orchestrator,
            activity_review_orchestrator=activity_review_orchestrator,
            pathways_orchestrator=pathways_orchestrator,
            lateral_orchestrator=lateral_orchestrator,
            calendar_optimization_orchestrator=calendar_optimization_orchestrator,
            # Advanced
            jupyter_sync=advanced["jupyter_sync"],
            performance_optimization=advanced["performance_optimization"],
            # Cross-cutting AI services (require LLM/embeddings)
            askesis_ai=askesis_ai,
            context_aware_ai=context_aware_ai,
            # Lateral relationship services (January 2026 - Core graph architecture)
            lateral=lateral_service,
            # Intelligence tier (ADR-043)
            intelligence_tier=tier,
        )

        # Create UserContextIntelligence factory, ZPD service, and Askesis
        await _create_intelligence_hub(
            services=services,
            activity_services=activity_services,
            learning_services=learning_services,
            submissions_backend=submissions_backend,
            calendar_service=calendar_service,
            vector_search_service=vector_search_service,
            driver=driver,
            event_bus=event_bus,
            tier=tier,
            context_builder=context_builder,
            user_service=user_service,
            context_service=context_service,
            askesis_core_service=askesis_core_service,
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
        services.search_router = search_router  # type: ignore[assignment]  # SearchRouter implements SearchOperations
        logger.info("✅ SearchRouter created (One Path Forward)")

        # ========================================================================
        # VALIDATE POST-CONSTRUCTION WIRING (fail-fast if any was missed)
        # ========================================================================
        post_wiring_checks = {
            "analytics_engine.relationship_service": analytics_engine.relationship_service,
            "context_service.tasks_service": context_service.tasks_service,
            "context_service.goal_task_generator": context_service.goal_task_generator,
            "context_service.habits_service": context_service.habits_service,
            "context_service.intelligence_factory": context_service.intelligence_factory,
            "user_service.intelligence_factory": user_service.intelligence_factory,
            "services.context_intelligence": services.context_intelligence,
            "services.search_router": services.search_router,
            "form_submission_service.sharing_service": form_submission_service.sharing_service,
            # habits.goal_analytics shelved (2026-03-28)
        }
        missing = [name for name, value in post_wiring_checks.items() if value is None]
        if missing:
            raise ValueError(
                f"Post-construction wiring incomplete — these attributes are None: "
                f"{', '.join(missing)}"
            )
        logger.info(
            f"✅ Post-construction wiring validated ({len(post_wiring_checks)} attributes checked)"
        )

        logger.info("✅ Service composition complete")
        return Result.ok(services)

    except (TypeError, AttributeError, ImportError, NameError):
        # Programming errors must propagate — they indicate real bugs in wiring,
        # not runtime configuration failures. Masking them as Result.fail() hides
        # the root cause during development.
        raise
    except Exception as e:  # safety-net: bootstrap boundary catches config/infra failures
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
