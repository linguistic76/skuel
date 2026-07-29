"""Curriculum service creation — KU, PS, LP, embeddings, vector search."""

from typing import TYPE_CHECKING, Any

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
    chunking_service: Any,
    user_service: Any,
    graph_intelligence: Any,
    llm_service: Any,  # LLMService for RAG generation (None when CORE tier)
    event_bus: Any = None,
    prometheus_metrics: "PrometheusMetrics | None" = None,
    query_executor: Any = None,
    activity_knowledge_intelligence: Any = None,
) -> dict[str, Any]:
    """Create all learning-related services using 100% dynamic backends."""
    from adapters.persistence.neo4j.query_builders import QueryBuilder
    from adapters.persistence.neo4j.schema_service import Neo4jSchemaService
    from core.models.pathways.learning_path import LearningPath
    from core.services.lp_service import LpService  # Intelligence created internally
    from core.services.ps_service import PsService
    from core.services.user_progress_service import UserProgressService

    # Create embedding + vector search services (ADR-068: OpenAI now, BGE long-term)
    # Gated by intelligence tier (ADR-043): CORE skips entirely, FULL creates normally
    embeddings_service = None
    vector_search_service = None

    from core.config.intelligence_tier import IntelligenceTier

    tier = IntelligenceTier.from_env()

    if not tier.ai_enabled:
        logger.info("⏭️  Embedding services skipped (intelligence tier: CORE)")
    else:
        try:
            from adapters.external.embeddings import create_embedding_client
            from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
            from core.services.embeddings_service import EmbeddingsService
            from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

            # Inference client (vendor SDK + credential read) lives below the
            # hexagonal boundary; the factory is the provider chokepoint (ADR-068).
            # Missing key → adapter raises ValueError, wrapped below with tier guidance.
            embedding_client = create_embedding_client()

            embeddings_backend = EmbeddingsBackend(executor=query_executor)
            embeddings_service = EmbeddingsService(
                backend=embeddings_backend,
                embedding_client=embedding_client,
                prometheus_metrics=prometheus_metrics,
            )
            logger.info(
                f"✅ Embeddings service created ({embedding_client.model}, "
                f"{embedding_client.dimension}d)"
            )

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
                "FULL-tier bootstrap requires embedding services. "
                "Set INTELLIGENCE_TIER=core to run without vector search, or fix the "
                f"underlying init error: {e}"
            ) from e

    # NOTE: LpIntelligenceService now created internally by LpService (January 2026)
    # See LpService.__init__ for intelligence creation pattern (unified with other domains)

    # Create query builder
    schema_service = Neo4jSchemaService(driver)
    query_builder = QueryBuilder(schema_service)

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
    # PsBackend passed in from _backends.py with all 5 domain mixins.
    # PsIntelligenceBackend built here (composition root) and injected — the PS
    # intelligence service never imports the adapter (ADR-044 / SKUEL022).
    from adapters.persistence.neo4j.ps_intelligence_backend import PsIntelligenceBackend

    ps_service = PsService(
        backend=knowledge_backend,
        executor=query_executor,
        graph_intel=graph_intelligence,
        event_bus=event_bus,
        # Content and search dependencies
        ku_backend=atomic_ku_backend,
        chunking_service=chunking_service,
        query_builder=query_builder,  # QueryBuilder is now REQUIRED
        user_service=user_service,  # KU-Activity Integration
        vector_search_service=vector_search_service,  # GenAI vector search
        embeddings_service=embeddings_service,  # EmbeddingClientOperations-backed (ADR-068)
        ps_intelligence_backend=PsIntelligenceBackend(query_executor),
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
        graph_intel=graph_intelligence,  # gates graph-context retrieval (mechanism B, REQUIRED)
        event_bus=event_bus,  # Event-driven architecture
        progress_backend=progress_backend,
        user_service=user_service,
    )

    # NOTE: Askesis creation MOVED to compose_services() (January 2026)
    # This allows intelligence_factory to be passed at construction time (not post-wired)

    return {
        "learning_intelligence": learning_paths.intelligence,  # Access via facade
        "atomic_ku_service": atomic_ku_service,
        "user_progress": user_progress,
        # unified_progress DELETED (January 2026)
        "learning_paths": learning_paths,
        "ps": ps_service,
        # NOTE: "askesis" MOVED to compose_services() (January 2026)
        "activity_knowledge_intelligence": activity_knowledge_intelligence,
        "embeddings_service": embeddings_service,  # For intelligence services
        "vector_search_service": vector_search_service,  # For semantic search
        # Components needed for Askesis creation in compose_services()
        "graph_intelligence": graph_intelligence,
        "llm_service": llm_service,
    }
