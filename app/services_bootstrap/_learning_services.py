"""Curriculum service creation — KU, PS, LP, embeddings, vector search."""

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
            from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
            from core.services.embeddings_service import HuggingFaceEmbeddingsService
            from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

            # Create HuggingFace embeddings service
            embeddings_backend = EmbeddingsBackend(executor=query_executor)
            embeddings_service = HuggingFaceEmbeddingsService(
                backend=embeddings_backend,
                prometheus_metrics=prometheus_metrics,
            )
            logger.info("✅ HuggingFace embeddings service created (BAAI/bge-large-en-v1.5)")

            # Create vector search backend + service
            from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend

            vector_search_backend = VectorSearchBackend(executor=query_executor)
            vector_search_service = Neo4jVectorSearchService(
                vector_search_backend, embeddings_service
            )
            logger.info("✅ Neo4j vector search service created")

        except Exception as e:  # safety-net: surface FULL-tier embedding init failure loudly
            # Fail-fast per CLAUDE.md "Fail-Fast Dependency Philosophy": FULL tier promises
            # vector search to downstream services (Askesis, intelligence). Silently degrading
            # leaves the system in a half-on state where Askesis exists but produces
            # graph-only answers — exactly the silent fallback Gap #6 calls out.
            logger.error(f"FULL-tier embedding services failed to initialize: {e}")
            raise RuntimeError(
                "FULL-tier bootstrap requires HuggingFace embedding services. "
                "Set INTELLIGENCE_TIER=core to run without vector search, or fix the "
                f"underlying init error: {e}"
            ) from e

    # NOTE: LpIntelligenceService now created internally by LpService (January 2026)
    # See LpService.__init__ for intelligence creation pattern (unified with other domains)

    # Create query builder
    schema_service = Neo4jSchemaService(driver)
    unified_query_builder = QueryBuilder(schema_service)

    # Create atomic Ku service (lightweight ontology/reference nodes)
    from core.services.ku_service import KuService

    atomic_ku_service = KuService(
        backend=atomic_ku_backend,
        graph_intel=graph_intelligence,
        event_bus=event_bus,
    )

    # Create progress services
    from adapters.persistence.neo4j.user_progress_backend import UserProgressBackend

    user_progress_backend = UserProgressBackend(query_executor)
    user_progress = UserProgressService(user_progress_backend)
    # Note: unified_progress DELETED (January 2026) - use user_progress or UserContextBuilder

    # Create path step service (PS operations)
    # PsBackend passed in from _backends.py with all 5 domain mixins
    ps_service = PsService(
        backend=knowledge_backend,
        executor=query_executor,
        graph_intel=graph_intelligence,
        event_bus=event_bus,
        # Content and search dependencies
        content_repo=content_adapter,  # Neo4jContentAdapter implements ContentOperations protocol
        ku_backend=atomic_ku_backend,
        chunking_service=chunking_service,
        query_builder=unified_query_builder,  # QueryBuilder is now REQUIRED
        user_service=user_service,  # KU-Activity Integration
        vector_search_service=vector_search_service,  # GenAI vector search
        embeddings_service=embeddings_service,  # HuggingFace embeddings (bge-large-en-v1.5)
    )

    # Create path service (LP operations - delegates PS operations to PsService)
    # January 2026: Intelligence created internally (unified with other domains)
    # Backend created here (composition root) — core services never import adapters
    from adapters.persistence.neo4j.backends.curriculum_backends import LpBackend

    lp_backend = LpBackend(driver, NeoLabel.LEARNING_PATH, LearningPath, base_label=NeoLabel.ENTITY)
    learning_paths = LpService(
        backend=lp_backend,
        ps_service=ps_service,  # Delegate PS operations to PsService
        ku_service=ps_service,  # PsService handles curriculum content
        progress_service=user_progress,
        graph_intel=graph_intelligence,  # GraphContextLoader (REQUIRED)
        event_bus=event_bus,  # Event-driven architecture
        progress_backend=progress_backend,
        user_service=user_service,
    )

    # NOTE: Askesis creation MOVED to compose_services() (January 2026)
    # This allows intelligence_factory to be passed at construction time (not post-wired)

    # Create cross-domain service (circular import resolved via adaptive_lp_models.py)
    from core.services.adaptive_lp.adaptive_lp_cross_domain_service import (
        AdaptiveLpCrossDomainService,
    )

    cross_domain_service = AdaptiveLpCrossDomainService(MasteryLevel.BEGINNER)

    # Create knowledge domain service (world-layer taxonomy — read-only)
    from adapters.persistence.neo4j.knowledge_domain_backend import KnowledgeDomainBackend
    from core.services.knowledge_domain_service import KnowledgeDomainService

    knowledge_domain_backend = KnowledgeDomainBackend(executor=query_executor)
    knowledge_domain_service = KnowledgeDomainService(backend=knowledge_domain_backend)

    return {
        "learning_intelligence": learning_paths.intelligence,  # Access via facade
        "atomic_ku_service": atomic_ku_service,
        "knowledge_domains": knowledge_domain_service,
        "user_progress": user_progress,
        # unified_progress DELETED (January 2026)
        "learning_paths": learning_paths,
        "ps": ps_service,
        # NOTE: "askesis" MOVED to compose_services() (January 2026)
        "cross_domain": cross_domain_service,
        "activity_knowledge_intelligence": activity_knowledge_intelligence,
        "embeddings_service": embeddings_service,  # For intelligence services
        "vector_search_service": vector_search_service,  # For semantic search
        # Components needed for Askesis creation in compose_services()
        "graph_intelligence": graph_intelligence,
        "llm_service": llm_service,
    }
