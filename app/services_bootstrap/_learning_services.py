"""Curriculum service creation — KU, PS, LP, embeddings, vector search."""

from typing import TYPE_CHECKING

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.config.intelligence_tier import IntelligenceTier
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics
    from core.models.progress import UserProgress
    from core.ports import BackendOperations, EventBusOperations
    from core.ports.curriculum_protocols import KuOperations, PsOperations
    from core.services.entity_chunking_service import EntityChunkingService
    from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
    from core.services.learning_services import LearningServices
    from core.services.user_service import UserService
    from services_bootstrap._backends import Backends

logger = get_logger("skuel.bootstrap")


def _create_learning_services(
    *,
    backends: Backends,
    progress_backend: BackendOperations[UserProgress],
    knowledge_backend: PsOperations,
    atomic_ku_backend: KuOperations,  # KuBackend for atomic Ku entities
    chunking_service: EntityChunkingService,
    user_service: UserService,
    graph_intelligence: GraphIntelligenceService,
    tier: IntelligenceTier,  # resolved once in compose_services — the single from_env() read
    event_bus: EventBusOperations,
    prometheus_metrics: PrometheusMetrics | None = None,
) -> LearningServices:
    """Create the curriculum facades, the progress service and the embedding pair.

    The embedding and vector search services are built in the FULL tier only and
    are ``None`` in CORE.
    """
    from core.services.lp_service import LpService  # Intelligence created internally
    from core.services.ps_service import PsService
    from core.services.user_progress_service import UserProgressService

    # Create embedding + vector search services (ADR-068: OpenAI now, BGE long-term)
    # Gated by intelligence tier (ADR-043): CORE skips entirely, FULL creates normally
    embeddings_service = None
    vector_search_service = None

    if not tier.ai_enabled:
        logger.info("⏭️  Embedding services skipped (intelligence tier: CORE)")
    else:
        try:
            from adapters.external.embeddings import create_embedding_client
            from core.services.embeddings_service import EmbeddingsService
            from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

            # Inference client (vendor SDK + credential read) lives below the
            # hexagonal boundary; the factory is the provider chokepoint (ADR-068).
            # Missing key → adapter raises ValueError, wrapped below with tier guidance.
            embedding_client = create_embedding_client()

            embeddings_service = EmbeddingsService(
                backend=backends["embeddings_backend"],
                embedding_client=embedding_client,
                prometheus_metrics=prometheus_metrics,
            )
            logger.info(
                f"✅ Embeddings service created ({embedding_client.model}, "
                f"{embedding_client.dimension}d)"
            )

            vector_search_service = Neo4jVectorSearchService(
                backends["vector_search_backend"], embeddings_service
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

    # Create atomic Ku service (lightweight ontology/reference nodes)
    from core.services.ku_service import KuService

    atomic_ku_service = KuService(
        backend=atomic_ku_backend,
        graph_intel=graph_intelligence,
        event_bus=event_bus,
    )

    # Create progress services
    user_progress = UserProgressService(backends["user_progress_backend"])
    # Note: unified_progress DELETED (January 2026) - use user_progress or UserContextBuilder

    # Create path step service (PS operations)
    # PsBackend and PsIntelligenceBackend come from create_all_backends and are
    # injected — the PS intelligence service never imports the adapter (ADR-044 / SKUEL022).

    ps_service = PsService(
        backend=knowledge_backend,
        graph_intel=graph_intelligence,
        event_bus=event_bus,
        # Content and search dependencies
        ku_backend=atomic_ku_backend,
        chunking_service=chunking_service,
        user_service=user_service,  # KU-Activity Integration
        vector_search_service=vector_search_service,  # GenAI vector search
        embeddings_service=embeddings_service,  # EmbeddingClientOperations-backed (ADR-068)
        ps_intelligence_backend=backends["ps_intelligence_backend"],
    )

    # Create path service (LP operations - delegates PS operations to PsService)
    # January 2026: Intelligence created internally (unified with other domains)
    # Backend from create_all_backends — core services never import adapters
    learning_paths = LpService(
        backend=backends["lp_backend"],
        ps_service=ps_service,  # Delegate PS operations to PsService
        ku_service=ps_service,  # PsService handles curriculum content
        progress_service=user_progress,
        graph_intel=graph_intelligence,  # gates graph-context retrieval (mechanism B, REQUIRED)
        event_bus=event_bus,  # Event-driven architecture
        progress_backend=progress_backend,
        user_service=user_service,
    )

    return {
        "learning_intelligence": learning_paths.intelligence,  # Access via facade
        "atomic_ku_service": atomic_ku_service,
        "user_progress": user_progress,
        "learning_paths": learning_paths,
        "ps": ps_service,
        "embeddings_service": embeddings_service,  # For intelligence services
        "vector_search_service": vector_search_service,  # For semantic search
    }
