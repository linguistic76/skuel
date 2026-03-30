"""Curriculum service creation — Lesson, KU, LS, LP, embeddings, vector search."""

from typing import TYPE_CHECKING, Any

from core.constants import MasteryLevel
from core.models.enums.neo_labels import NeoLabel
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics

logger = get_logger("skuel.bootstrap")


def _create_learning_services(
    driver: Any,
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
    activity_knowledge_intelligence: Any = None,
) -> dict[str, Any]:
    """Create all learning-related services using 100% dynamic backends."""
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.path_step import PathStep
    from core.services.entity_retrieval import EntityRetrieval
    from core.services.lesson_service import LessonService
    from core.services.lp_service import LpService  # Intelligence created internally
    from core.services.ps_service import PsService
    from core.services.query_builder import QueryBuilder
    from core.services.schema_service import Neo4jSchemaService
    from core.services.user_progress_service import UserProgressService

    # Create embedding + vector search services (March 2026 - HuggingFace Migration)
    # Uses HuggingFace Inference API with BAAI/bge-large-en-v1.5 (1024 dims)
    # Replaces Neo4j GenAI plugin + OpenAI text-embedding-3-small (ADR-049)
    # Gated by intelligence tier (ADR-043): CORE skips entirely, FULL creates normally
    embeddings_service = None
    vector_search_service = None

    from core.config.intelligence_tier import IntelligenceTier

    tier = IntelligenceTier.from_env()

    if not tier.ai_enabled:
        logger.info("⏭️  Embedding services skipped (intelligence tier: CORE)")
    else:
        try:
            from core.services.embeddings_service import HuggingFaceEmbeddingsService
            from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

            # Create HuggingFace embeddings service
            embeddings_service = HuggingFaceEmbeddingsService(
                executor=query_executor,
                prometheus_metrics=prometheus_metrics,
            )
            logger.info("✅ HuggingFace embeddings service created (BAAI/bge-large-en-v1.5)")

            # Create vector search service (uses db.index.vector.queryNodes() — native Neo4j)
            vector_search_service = Neo4jVectorSearchService(query_executor, embeddings_service)
            logger.info("✅ Neo4j vector search service created")

        except Exception as e:  # safety-net: service bootstrap must report initialization failures
            logger.warning(f"Failed to initialize embedding services: {e}")
            logger.warning("   Vector search will not be available - using keyword search fallback")
            embeddings_service = None
            vector_search_service = None

    # NOTE: LpIntelligenceService now created internally by LpService (January 2026)
    # See LpService.__init__ for intelligence creation pattern (unified with other domains)

    # Create query builder
    schema_service = Neo4jSchemaService(driver)
    unified_query_builder = QueryBuilder(schema_service)

    # Create knowledge service using dynamic backends with REQUIRED query_builder
    # January 2026: LessonIntelligenceService created internally, no longer passed in
    # January 2026 - GenAI Integration: Pass vector search and embeddings services
    ku_service = LessonService(
        repo=knowledge_backend,
        content_repo=content_adapter,  # Neo4jContentAdapter implements ContentOperations protocol
        ku_backend=atomic_ku_backend,
        chunking_service=chunking_service,
        graph_intelligence_service=graph_intelligence,
        query_builder=unified_query_builder,  # QueryBuilder is now REQUIRED
        event_bus=event_bus,  # Event-driven architecture
        # executor removed: LessonOrganizationService now uses backend directly
        user_service=user_service,  # January 2026: KU-Activity Integration
        vector_search_service=vector_search_service,  # January 2026: GenAI vector search
        embeddings_service=embeddings_service,  # March 2026: HuggingFace embeddings (bge-large-en-v1.5)
    )

    # Create atomic Ku service (lightweight ontology/reference nodes)
    from core.services.ku_service import KuService

    atomic_ku_service = KuService(
        backend=atomic_ku_backend,
        graph_intel=graph_intelligence,
        event_bus=event_bus,
    )

    # Create progress services
    user_progress = UserProgressService(query_executor)
    # Note: unified_progress DELETED (January 2026) - use user_progress or UserContextBuilder

    # Create path step service (LS operations)
    # January 2026: graph_intel now REQUIRED for unified Curriculum architecture (ADR-030)
    # Backend created here (composition root) — core services never import adapters
    from adapters.persistence.neo4j.domain_backends import PsBackend

    ps_backend = PsBackend(driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    ps_service = PsService(
        backend=ps_backend,
        executor=query_executor,
        graph_intel=graph_intelligence,
        event_bus=event_bus,
    )

    # Create path service (LP operations - delegates LS operations to PsService)
    # January 2026: Intelligence created internally (unified with other domains)
    # Backend created here (composition root) — core services never import adapters
    from adapters.persistence.neo4j.domain_backends import LpBackend

    lp_backend = LpBackend(driver, NeoLabel.LEARNING_PATH, LearningPath, base_label=NeoLabel.ENTITY)
    learning_paths = LpService(
        backend=lp_backend,
        executor=query_executor,
        ps_service=ps_service,  # Delegate LS operations to PsService
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

    # Adaptive SEL removed — now LessonService.adaptive sub-service (February 2026)

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
        "lesson_service": ku_service,
        "atomic_ku_service": atomic_ku_service,
        "user_progress": user_progress,
        # unified_progress DELETED (January 2026)
        "learning_paths": learning_paths,
        "path_steps": ps_service,  # NEW: Dedicated LS service
        "ku_retrieval": ku_retrieval,
        # NOTE: "askesis" MOVED to compose_services() (January 2026)
        "cross_domain": cross_domain_service,
        "activity_knowledge_intelligence": activity_knowledge_intelligence,
        "embeddings_service": embeddings_service,  # For intelligence services
        "vector_search_service": vector_search_service,  # For semantic search
        # Components needed for Askesis creation in compose_services()
        "graph_intelligence": graph_intelligence,
        "llm_service": llm_service,
    }
