"""
Curriculum Domain Configuration Registry
=========================================

Centralizes configuration for 4 Curriculum Domain facades.

Each domain has:
- core_module/class: CoreService class for CRUD operations
- search_module/class: SearchService class for discovery
- intelligence_module/class: IntelligenceService class for analytics
- relationship_config: DomainRelationshipConfig from registry (direct reference)

Usage:
    from core.utils.curriculum_domain_config import (
        CURRICULUM_DOMAIN_CONFIGS,
        create_curriculum_sub_services,
    )

    # In facade __init__:
    common = create_curriculum_sub_services(
        domain="ls",
        backend=backend,
        graph_intel=graph_intelligence_service,
        event_bus=event_bus,
    )
    self.core = common.core
    self.search = common.search
    self.relationships = common.relationships
    self.intelligence = common.intelligence

Created: January 2026
Reason: Unify Curriculum domain architecture with Activity domains (ADR-030)
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from core.models.relationship_registry import (
    KU_CONFIG,
    LP_CONFIG,
    LS_CONFIG,
)
from core.services.relationships import UnifiedRelationshipService

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.ports import EventBusOperations, KuOperations, QueryBuilderOperations
    from core.services.ku.ku_adaptive_service import KuAdaptiveService
    from core.services.ku.ku_core_service import KuCoreService
    from core.services.ku.ku_graph_service import KuGraphService
    from core.services.ku.ku_interaction_service import KuInteractionService
    from core.services.ku.ku_practice_service import KuPracticeService
    from core.services.ku.ku_search_service import KuSearchService
    from core.services.ku.ku_semantic_service import KuSemanticService
    from core.services.ku_intelligence_service import KuIntelligenceService
    from core.services.lp.lp_core_service import LpCoreService
    from core.services.lp.lp_progress_service import LpProgressService
    from core.services.lp.lp_search_service import LpSearchService
    from core.services.lp_intelligence_service import LpIntelligenceService
    from core.services.ls_service import LsService

# Type vars for generics
T = TypeVar("T")  # Domain model type
T_Intelligence = TypeVar("T_Intelligence")  # Intelligence service type
B = TypeVar("B")  # Backend operations protocol


@dataclass(frozen=True)
class CurriculumDomainConfig:
    """Configuration for a Curriculum Domain's common sub-services."""

    # Service classes (imported lazily to avoid circular imports)
    core_module: str
    core_class: str
    search_module: str
    search_class: str
    intelligence_module: str
    intelligence_class: str

    # Relationship config (direct from registry)
    relationship_config: Any

    # Domain metadata
    domain_name: str
    entity_label: str


# Registry of all 4 Curriculum Domain configurations
CURRICULUM_DOMAIN_CONFIGS: dict[str, CurriculumDomainConfig] = {
    "ku": CurriculumDomainConfig(
        core_module="core.services.ku.ku_core_service",
        core_class="KuCoreService",
        search_module="core.services.ku.ku_search_service",
        search_class="KuSearchService",
        intelligence_module="core.services.ku_intelligence_service",
        intelligence_class="KuIntelligenceService",
        relationship_config=KU_CONFIG,
        domain_name="ku",
        entity_label="Entity",
    ),
    "ls": CurriculumDomainConfig(
        core_module="core.services.ls.ls_core_service",
        core_class="LsCoreService",
        search_module="core.services.ls.ls_search_service",
        search_class="LsSearchService",
        intelligence_module="core.services.ls.ls_intelligence_service",
        intelligence_class="LsIntelligenceService",
        relationship_config=LS_CONFIG,
        domain_name="ls",
        entity_label="Entity",
    ),
    "lp": CurriculumDomainConfig(
        core_module="core.services.lp.lp_core_service",
        core_class="LpCoreService",
        search_module="core.services.lp.lp_search_service",
        search_class="LpSearchService",
        intelligence_module="core.services.lp_intelligence_service",
        intelligence_class="LpIntelligenceService",
        relationship_config=LP_CONFIG,
        domain_name="lp",
        entity_label="Entity",
    ),
}


@dataclass
class CurriculumCommonSubServices(Generic[T_Intelligence]):
    """
    Container for the 4 common sub-services created by the factory.

    Generic over T_Intelligence to preserve the concrete intelligence service type.
    Facades should annotate the assignment to get proper type checking:

        common: CurriculumCommonSubServices[LpIntelligenceService] = create_curriculum_sub_services(...)
        self.intelligence = common.intelligence  # MyPy knows this is LpIntelligenceService
    """

    core: Any
    search: Any
    relationships: UnifiedRelationshipService
    intelligence: T_Intelligence


def create_curriculum_sub_services(
    domain: str,
    backend: Any,
    graph_intel: Any,
    event_bus: Any = None,
) -> CurriculumCommonSubServices[Any]:
    """
    Factory function to create the 4 common sub-services for Curriculum Domain facades.

    This mirrors the Activity domain factory pattern (create_common_sub_services).
    It eliminates repetitive initialization code and ensures consistent wiring.

    Args:
        domain: Domain name ("ku", "ls", "lp")
        backend: Domain backend operations (UniversalNeo4jBackend[T])
        graph_intel: GraphIntelligenceService for analytics (REQUIRED for consistency)
        event_bus: Event bus for domain events (optional)

    Returns:
        CurriculumCommonSubServices dataclass with core, search, relationships, intelligence.
        Callers should annotate with specific intelligence type for type safety:

            common: CurriculumCommonSubServices[LsIntelligenceService] = create_curriculum_sub_services(...)

    Example:
        common: CurriculumCommonSubServices[LsIntelligenceService] = create_curriculum_sub_services(
            "ls", backend, graph_intel, event_bus
        )
        self.core = common.core
        self.search = common.search
        self.relationships = common.relationships
        self.intelligence = common.intelligence  # Typed as LsIntelligenceService

    Note:
        For domains with non-standard core/search signatures (KU, LP, MOC),
        the facade may create those services manually instead of using this factory,
        similar to how TasksService creates its core manually due to ku_inference_service.
    """
    import importlib

    config = CURRICULUM_DOMAIN_CONFIGS[domain]

    # Create relationships service FIRST (needed by intelligence)
    relationships = UnifiedRelationshipService(
        backend=backend,
        config=config.relationship_config,
        graph_intel=graph_intel,
    )

    # Dynamically import intelligence class
    intel_module = importlib.import_module(config.intelligence_module)
    intel_class = getattr(intel_module, config.intelligence_class)

    # Create intelligence service (backend + graph_intel + relationships)
    intelligence = intel_class(
        backend=backend,
        graph_intelligence_service=graph_intel,
        relationship_service=relationships,
    )

    # Dynamically import core class
    core_module = importlib.import_module(config.core_module)
    core_class = getattr(core_module, config.core_class)

    # Create core service (backend + event_bus)
    # Note: This assumes standard signature. For non-standard (KU, LP, MOC),
    # facades create core manually with additional dependencies.
    core = core_class(backend=backend, event_bus=event_bus)

    # Dynamically import search class
    search_module = importlib.import_module(config.search_module)
    search_class = getattr(search_module, config.search_class)

    # Create search service (just backend for BaseService pattern)
    search = search_class(backend=backend)

    return CurriculumCommonSubServices(
        core=core,
        search=search,
        relationships=relationships,
        intelligence=intelligence,
    )


# =============================================================================
# DOMAIN-SPECIFIC FACTORIES
# KU and LP have complex dependencies that require specialized factories.
# LS uses the generic create_curriculum_sub_services() above.
# =============================================================================


@dataclass
class KuSubServices:
    """Container for all KuService sub-services created by the factory."""

    core: "KuCoreService"
    search: "KuSearchService"
    graph: "KuGraphService"
    semantic: "KuSemanticService"
    practice: "KuPracticeService"
    interaction: "KuInteractionService"
    relationships: "UnifiedRelationshipService"
    intelligence: "KuIntelligenceService"
    adaptive: "KuAdaptiveService"


@dataclass
class LpSubServices:
    """Container for all LpService sub-services created by the factory."""

    core: "LpCoreService"
    search: "LpSearchService"
    relationships: "UnifiedRelationshipService"
    intelligence: "LpIntelligenceService"
    progress: "LpProgressService"
    backend: Any  # BackendOperations[Ku] — protocol-typed to avoid adapter import


def create_ku_sub_services(
    backend: "KuOperations",
    content_repo: Any | None,
    neo4j_adapter: Any | None,
    chunking_service: Any | None,
    graph_intelligence_service: Any,
    query_builder: "QueryBuilderOperations | None",
    event_bus: "EventBusOperations | None",
    _driver: "AsyncDriver | None",
    user_service: Any | None = None,
    vector_search_service: Any | None = None,
    embeddings_service: Any | None = None,
) -> KuSubServices:
    """
    Factory function to create all 8 KuService sub-services.

    Handles the circular dependency: Intelligence must be created
    BEFORE Core (Core depends on intelligence for content analysis).

    Creation Order:
    1. UnifiedRelationshipService (backend, config, graph_intel)
    2. KuIntelligenceService (backend, graph_intel, relationships, embeddings, llm)
    3. KuCoreService (repo, content_repo, intelligence, chunking, event_bus)
    4. KuSearchService (backend, content_repo, intelligence, query_builder, vector_search, embeddings)
    5. KuGraphService (repo, neo4j_adapter, graph_intel)
    6. KuSemanticService (repo, neo4j_adapter, intelligence)
    7. KuPracticeService (backend, event_bus)
    8. KuInteractionService (backend, event_bus)

    Args:
        backend: KuOperations backend - REQUIRED
        content_repo: Content storage backend (optional)
        neo4j_adapter: Neo4j adapter for graph operations (optional)
        chunking_service: Chunking service for RAG (optional)
        graph_intelligence_service: GraphIntelligenceService - REQUIRED
        query_builder: QueryBuilder service for optimized queries (optional)
        event_bus: Event bus for publishing domain events (optional)
        driver: Neo4j async driver for Phase 4 event-driven operations (optional)
        user_service: UserService for UserContext access (January 2026 - KU-Activity Integration)
        vector_search_service: Optional Neo4jVectorSearchService for semantic search (January 2026 - GenAI)
        embeddings_service: Optional Neo4jGenAIEmbeddingsService for embedding generation (January 2026 - GenAI)

    Returns:
        KuSubServices dataclass with all 8 sub-services
    """
    # Lazy imports to avoid circular dependencies
    from core.services.ku.ku_adaptive_service import KuAdaptiveService
    from core.services.ku.ku_core_service import KuCoreService
    from core.services.ku.ku_graph_service import KuGraphService
    from core.services.ku.ku_interaction_service import KuInteractionService
    from core.services.ku.ku_practice_service import KuPracticeService
    from core.services.ku.ku_search_service import KuSearchService
    from core.services.ku.ku_semantic_service import KuSemanticService
    from core.services.ku_intelligence_service import KuIntelligenceService

    # Step 1: Create relationship service (needed by intelligence)
    relationships = UnifiedRelationshipService(
        backend=backend,
        config=KU_CONFIG,
        graph_intel=graph_intelligence_service,
    )

    # Step 2: Create intelligence BEFORE core (circular dependency)
    # ADR-030: Analytics services have zero AI dependencies
    intelligence = KuIntelligenceService(
        backend=backend,
        graph_intelligence_service=graph_intelligence_service,
        relationship_service=relationships,
        user_service=user_service,
    )

    # Step 3: Create core (requires intelligence)
    core = KuCoreService(
        repo=backend,
        content_repo=content_repo,
        intelligence=intelligence,
        chunking=chunking_service,
        event_bus=event_bus,
    )

    # Step 4: Create search (with optional vector search - January 2026 GenAI)
    search = KuSearchService(
        backend=backend,
        content_repo=content_repo,
        intelligence=intelligence,
        query_builder=query_builder,
        vector_search_service=vector_search_service,  # Optional - graceful degradation
        embeddings_service=embeddings_service,  # Optional - graceful degradation
    )

    # Step 5: Create graph
    graph = KuGraphService(
        repo=backend,
        neo4j_adapter=neo4j_adapter,
        graph_intel=graph_intelligence_service,
    )

    # Step 6: Create semantic
    semantic = KuSemanticService(
        repo=backend,
        neo4j_adapter=neo4j_adapter,
        intelligence=intelligence,
    )

    # Step 7: Create practice (event-driven)
    practice = KuPracticeService(backend=backend, event_bus=event_bus)

    # Step 8: Create interaction (event-driven)
    interaction = KuInteractionService(backend=backend, event_bus=event_bus)

    # Step 9: Create adaptive curriculum service
    adaptive = KuAdaptiveService(ku_backend=backend, user_service=user_service)

    return KuSubServices(
        core=core,
        search=search,
        graph=graph,
        semantic=semantic,
        practice=practice,
        interaction=interaction,
        relationships=relationships,
        intelligence=intelligence,
        adaptive=adaptive,
    )


def create_lp_sub_services(
    backend: Any,
    executor: Any,
    ls_service: "LsService",
    graph_intelligence_service: Any,
    event_bus: "EventBusOperations | None" = None,
    progress_backend: Any | None = None,
    user_service: Any | None = None,
) -> LpSubServices:
    """
    Factory function to create all 5 LpService sub-services.

    Handles cross-domain dependency: LpCoreService requires ls_service.

    Creation Order:
    1. LpSearchService (backend)
    2. UnifiedRelationshipService (backend, config, graph_intel)
    3. LpCoreService (backend, ls_service, event_bus)
    4. LpProgressService (executor, event_bus)
    5. LpIntelligenceService (backend, graph_intel, progress_backend, event_bus, user_service, executor)

    Args:
        backend: BackendOperations for LP entities (REQUIRED — created by composition root)
        executor: QueryExecutor for raw Cypher (REQUIRED — created by composition root)
        ls_service: LsService - REQUIRED for path-step operations
        graph_intelligence_service: GraphIntelligenceService - REQUIRED
        event_bus: Event bus for publishing domain events (optional)
        progress_backend: UserProgress backend for learning state (optional)
        user_service: UserService for UserContext access (optional)

    Returns:
        LpSubServices dataclass with all 5 sub-services + backend
    """
    # Lazy imports (core-only — no adapter imports)
    from core.services.lp.lp_core_service import LpCoreService
    from core.services.lp.lp_progress_service import LpProgressService
    from core.services.lp.lp_search_service import LpSearchService
    from core.services.lp_intelligence_service import LpIntelligenceService

    # Step 1: Create search (simple, no dependencies)
    search = LpSearchService(backend=backend)

    # Step 2: Create relationships
    relationships = UnifiedRelationshipService(
        backend=backend,
        config=LP_CONFIG,
        graph_intel=graph_intelligence_service,
    )

    # Step 3: Create core (requires ls_service)
    core = LpCoreService(
        backend=backend,
        ls_service=ls_service,
        event_bus=event_bus,
    )

    # Step 4: Create progress
    progress = LpProgressService(executor=executor, event_bus=event_bus)

    # Step 5: Create intelligence
    # ADR-030: Analytics services have zero AI dependencies
    intelligence = LpIntelligenceService(
        backend=backend,
        graph_intelligence_service=graph_intelligence_service,
        progress_backend=progress_backend,
        learning_backend=backend,
        event_bus=event_bus,
        user_service=user_service,
        executor=executor,
    )

    return LpSubServices(
        core=core,
        search=search,
        relationships=relationships,
        intelligence=intelligence,
        progress=progress,
        backend=backend,
    )
