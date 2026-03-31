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
    from core.services.curriculum_domain_config import (
        CURRICULUM_DOMAIN_CONFIGS,
        create_curriculum_sub_services,
    )

    # In facade __init__:
    common = create_curriculum_sub_services(
        domain="ps",
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
    PS_CONFIG,
)
from core.services.relationships import UnifiedRelationshipService

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.ports import EventBusOperations, LessonOperations, QueryBuilderOperations
    from core.services.lesson.lesson_adaptive_service import LessonAdaptiveService
    from core.services.lesson.lesson_application_discovery_service import (
        LessonApplicationDiscoveryService,
    )
    from core.services.lesson.lesson_context_service import LessonContextService
    from core.services.lesson.lesson_core_service import LessonCoreService
    from core.services.lesson.lesson_graph_service import LessonGraphService
    from core.services.lesson.lesson_mastery_service import LessonMasteryService
    from core.services.lesson.lesson_practice_service import LessonPracticeService
    from core.services.lesson.lesson_search_service import LessonSearchService
    from core.services.lesson.lesson_semantic_service import LessonSemanticService
    from core.services.lesson_intelligence_service import LessonIntelligenceService
    from core.services.lp.lp_core_service import LpCoreService
    from core.services.lp.lp_progress_service import LpProgressService
    from core.services.lp.lp_search_service import LpSearchService
    from core.services.lp_intelligence_service import LpIntelligenceService
    from core.services.ps.ps_adaptive_service import PsAdaptiveService
    from core.services.ps.ps_application_discovery_service import PsApplicationDiscoveryService
    from core.services.ps.ps_context_service import PsContextService
    from core.services.ps.ps_core_service import PsCoreService
    from core.services.ps.ps_graph_service import PsGraphService
    from core.services.ps.ps_intelligence_service import PsIntelligenceService
    from core.services.ps.ps_mastery_service import PsMasteryService
    from core.services.ps.ps_organization_service import PsOrganizationService
    from core.services.ps.ps_practice_service import PsPracticeService
    from core.services.ps.ps_search_service import PsSearchService
    from core.services.ps.ps_semantic_service import PsSemanticService
    from core.services.ps_service import PsService

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
        intelligence_module="core.services.ku.ku_intelligence_service",
        intelligence_class="KuIntelligenceService",
        relationship_config=KU_CONFIG,
        domain_name="ku",
        entity_label="Ku",
    ),
    "ps": CurriculumDomainConfig(
        core_module="core.services.ps.ps_core_service",
        core_class="PsCoreService",
        search_module="core.services.ps.ps_search_service",
        search_class="PsSearchService",
        intelligence_module="core.services.ps.ps_intelligence_service",
        intelligence_class="PsIntelligenceService",
        relationship_config=PS_CONFIG,
        domain_name="ps",
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
        self.intelligence = common.intelligence # MyPy knows this is LpIntelligenceService
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
        domain: Domain name ("ku", "ps", "lp")
        backend: Domain backend operations (UniversalNeo4jBackend[T])
        graph_intel: GraphIntelligenceService for analytics (REQUIRED for consistency)
        event_bus: Event bus for domain events (optional)

    Returns:
        CurriculumCommonSubServices dataclass with core, search, relationships, intelligence.
        Callers should annotate with specific intelligence type for type safety:

            common: CurriculumCommonSubServices[PsIntelligenceService] = create_curriculum_sub_services(...)

    Example:
        common: CurriculumCommonSubServices[PsIntelligenceService] = create_curriculum_sub_services(
            "ps", backend, graph_intel, event_bus
        )
        self.core = common.core
        self.search = common.search
        self.relationships = common.relationships
        self.intelligence = common.intelligence # Typed as PsIntelligenceService

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


def create_ps_sub_services(
    backend: Any,
    content_repo: Any | None,
    chunking_service: Any | None,
    graph_intelligence_service: Any,
    query_builder: "QueryBuilderOperations | None",
    event_bus: "EventBusOperations | None",
    executor: Any | None = None,
    user_service: Any | None = None,
    vector_search_service: Any | None = None,
    embeddings_service: Any | None = None,
) -> "PsSubServices":
    """Factory function to create all 12 PsService sub-services.

    Mirrors create_lesson_sub_services() — PsService absorbs all Lesson capabilities.

    Creation Order:
    1. UnifiedRelationshipService (backend, config, graph_intel)
    2. PsIntelligenceService (backend, graph_intel, relationships, user_service)
    3. PsCoreService (backend, event_bus)
    4. PsSearchService (backend, content_repo, intelligence, query_builder, vector_search, embeddings)
    5. PsGraphService (repo, graph_intel)
    6. PsSemanticService (repo, intelligence)
    7. PsPracticeService (backend, event_bus)
    8. PsMasteryService (backend, event_bus)
    9. PsAdaptiveService (backend, user_service)
    10. PsApplicationDiscoveryService (repo)
    11. PsContextService (repo)
    12. PsOrganizationService (created by facade — needs service reference)
    """
    from core.services.ps.ps_adaptive_service import PsAdaptiveService
    from core.services.ps.ps_application_discovery_service import PsApplicationDiscoveryService
    from core.services.ps.ps_context_service import PsContextService
    from core.services.ps.ps_core_service import PsCoreService
    from core.services.ps.ps_graph_service import PsGraphService
    from core.services.ps.ps_mastery_service import PsMasteryService
    from core.services.ps.ps_organization_service import PsOrganizationService
    from core.services.ps.ps_practice_service import PsPracticeService
    from core.services.ps.ps_search_service import PsSearchService
    from core.services.ps.ps_semantic_service import PsSemanticService
    from core.services.ps.ps_intelligence_service import PsIntelligenceService

    # Step 1: Create relationship service (needed by intelligence)
    relationships = UnifiedRelationshipService(
        backend=backend,
        config=PS_CONFIG,
        graph_intel=graph_intelligence_service,
    )

    # Step 2: Create intelligence BEFORE core (circular dependency)
    intelligence = PsIntelligenceService(
        backend=backend,
        graph_intelligence_service=graph_intelligence_service,
        relationship_service=relationships,
        user_service=user_service,
    )

    # Step 3: Create core
    core = PsCoreService(backend=backend, event_bus=event_bus)

    # Step 4: Create search (with optional vector search)
    search = PsSearchService(
        backend=backend,
        content_repo=content_repo,
        intelligence=intelligence,
        query_builder=query_builder,
        vector_search_service=vector_search_service,
        embeddings_service=embeddings_service,
    )

    # Step 5: Create graph
    graph = PsGraphService(repo=backend, graph_intel=graph_intelligence_service)

    # Step 6: Create semantic
    semantic = PsSemanticService(repo=backend, intelligence=intelligence)

    # Step 7: Create practice (event-driven)
    practice = PsPracticeService(backend=backend, event_bus=event_bus)

    # Step 8: Create mastery (pedagogical tracking)
    mastery = PsMasteryService(backend=backend, event_bus=event_bus)

    # Step 9: Create adaptive
    adaptive = PsAdaptiveService(backend=backend, user_service=user_service)

    # Step 10: Create application discovery
    application_discovery = PsApplicationDiscoveryService(repo=backend)

    # Step 11: Create context service
    context_service = PsContextService(repo=backend)

    # Step 12: Organization — placeholder, needs facade reference (set by facade post-init)
    organization = PsOrganizationService(ps_service=None, backend=backend)  # type: ignore[arg-type]

    return PsSubServices(
        core=core,
        search=search,
        graph=graph,
        semantic=semantic,
        practice=practice,
        mastery=mastery,
        relationships=relationships,
        intelligence=intelligence,
        adaptive=adaptive,
        application_discovery=application_discovery,
        context_service=context_service,
        organization=organization,
    )


# =============================================================================
# DOMAIN-SPECIFIC FACTORIES (LEGACY — retained for backward compat until Phase 4+)
# =============================================================================


@dataclass
class PsSubServices:
    """Container for all PsService sub-services created by the factory.

    PsService absorbs all LessonService capabilities (Phase 3 merge).
    """

    core: "PsCoreService"
    search: "PsSearchService"
    graph: "PsGraphService"
    semantic: "PsSemanticService"
    practice: "PsPracticeService"
    mastery: "PsMasteryService"
    relationships: "UnifiedRelationshipService"
    intelligence: "PsIntelligenceService"
    adaptive: "PsAdaptiveService"
    application_discovery: "PsApplicationDiscoveryService"
    context_service: "PsContextService"
    organization: "PsOrganizationService"


@dataclass
class LessonSubServices:
    """Container for all LessonService sub-services created by the factory."""

    core: "LessonCoreService"
    search: "LessonSearchService"
    graph: "LessonGraphService"
    semantic: "LessonSemanticService"
    practice: "LessonPracticeService"
    mastery: "LessonMasteryService"
    relationships: "UnifiedRelationshipService"
    intelligence: "LessonIntelligenceService"
    adaptive: "LessonAdaptiveService"
    application_discovery: "LessonApplicationDiscoveryService"
    context_service: "LessonContextService"


@dataclass
class LpSubServices:
    """Container for all LpService sub-services created by the factory."""

    core: "LpCoreService"
    search: "LpSearchService"
    relationships: "UnifiedRelationshipService"
    intelligence: "LpIntelligenceService"
    progress: "LpProgressService"
    backend: Any  # BackendOperations[Ku] — protocol-typed to avoid adapter import


def create_lesson_sub_services(
    backend: "LessonOperations",
    content_repo: Any | None,
    chunking_service: Any | None,
    graph_intelligence_service: Any,
    query_builder: "QueryBuilderOperations | None",
    event_bus: "EventBusOperations | None",
    _driver: "AsyncDriver | None",
    user_service: Any | None = None,
    vector_search_service: Any | None = None,
    embeddings_service: Any | None = None,
    _ku_backend: Any | None = None,
) -> LessonSubServices:
    """
    Factory function to create all 11 LessonService sub-services.

    Handles the circular dependency: Intelligence must be created
    BEFORE Core (Core depends on intelligence for content analysis).

    Creation Order:
    1. UnifiedRelationshipService (backend, config, graph_intel)
    2. LessonIntelligenceService (backend, graph_intel, relationships, embeddings, llm)
    3. LessonCoreService (repo, content_repo, intelligence, chunking, event_bus)
    4. LessonSearchService (backend, content_repo, intelligence, query_builder, vector_search, embeddings)
    5. LessonGraphService (repo, graph_intel)
    6. LessonSemanticService (repo, intelligence)
    7. LessonPracticeService (backend, event_bus)
    8. LessonMasteryService (backend, event_bus)
    9. LessonAdaptiveService (backend, user_service)
    10. LessonApplicationDiscoveryService (repo)
    11. LessonContextService (repo)

    Args:
        backend: LessonOperations backend - REQUIRED
        content_repo: Content storage backend (optional)
        chunking_service: Chunking service for RAG (optional)
        graph_intelligence_service: GraphIntelligenceService - REQUIRED
        query_builder: QueryBuilder service for optimized queries (optional)
        event_bus: Event bus for publishing domain events (optional)
        driver: Neo4j async driver for event-driven operations (optional)
        user_service: UserService for UserContext access (January 2026 - KU-Activity Integration)
        vector_search_service: Optional Neo4jVectorSearchService for semantic search (January 2026 - GenAI)
        embeddings_service: Optional HuggingFaceEmbeddingsService for embedding generation (January 2026 - GenAI)

    Returns:
        LessonSubServices dataclass with all 11 sub-services
    """
    # Lazy imports to avoid circular dependencies
    from core.services.lesson.lesson_adaptive_service import LessonAdaptiveService
    from core.services.lesson.lesson_application_discovery_service import (
        LessonApplicationDiscoveryService,
    )
    from core.services.lesson.lesson_context_service import LessonContextService
    from core.services.lesson.lesson_core_service import LessonCoreService
    from core.services.lesson.lesson_graph_service import LessonGraphService
    from core.services.lesson.lesson_mastery_service import LessonMasteryService
    from core.services.lesson.lesson_practice_service import LessonPracticeService
    from core.services.lesson.lesson_search_service import LessonSearchService
    from core.services.lesson.lesson_semantic_service import LessonSemanticService
    from core.services.lesson_intelligence_service import LessonIntelligenceService

    # Step 1: Create relationship service (needed by intelligence)
    relationships = UnifiedRelationshipService(
        backend=backend,
        config=PS_CONFIG,  # LESSON_CONFIG merged into PS_CONFIG
        graph_intel=graph_intelligence_service,
    )

    # Step 2: Create intelligence BEFORE core (circular dependency)
    # ADR-030: Analytics services have zero AI dependencies
    intelligence = LessonIntelligenceService(
        backend=backend,
        graph_intelligence_service=graph_intelligence_service,
        relationship_service=relationships,
        user_service=user_service,
    )

    # Step 3: Create core (requires intelligence)
    core = LessonCoreService(
        repo=backend,
        content_repo=content_repo,
        intelligence=intelligence,
        chunking=chunking_service,
        event_bus=event_bus,
    )

    # Step 4: Create search (with optional vector search - January 2026 GenAI)
    search = LessonSearchService(
        backend=backend,
        content_repo=content_repo,
        intelligence=intelligence,
        query_builder=query_builder,
        vector_search_service=vector_search_service,  # Optional - graceful degradation
        embeddings_service=embeddings_service,  # Optional - graceful degradation
    )

    # Step 5: Create graph
    graph = LessonGraphService(
        repo=backend,
        graph_intel=graph_intelligence_service,
    )

    # Step 6: Create semantic
    semantic = LessonSemanticService(
        repo=backend,
        intelligence=intelligence,
    )

    # Step 7: Create practice (event-driven)
    practice = LessonPracticeService(backend=backend, event_bus=event_bus)

    # Step 8: Create mastery (pedagogical tracking)
    mastery = LessonMasteryService(backend=backend, event_bus=event_bus)

    # Step 9: Create adaptive curriculum service
    adaptive = LessonAdaptiveService(backend=backend, user_service=user_service)

    # Step 10: Create application discovery (reverse relationship queries)
    application_discovery = LessonApplicationDiscoveryService(repo=backend)

    # Step 11: Create context service (context-first knowledge recommendations)
    context_service = LessonContextService(repo=backend)

    return LessonSubServices(
        core=core,
        search=search,
        graph=graph,
        semantic=semantic,
        practice=practice,
        mastery=mastery,
        relationships=relationships,
        intelligence=intelligence,
        adaptive=adaptive,
        application_discovery=application_discovery,
        context_service=context_service,
    )


def create_lp_sub_services(
    backend: Any,
    executor: Any,
    ps_service: "PsService",
    graph_intelligence_service: Any,
    event_bus: "EventBusOperations | None" = None,
    progress_backend: Any | None = None,
    user_service: Any | None = None,
) -> LpSubServices:
    """
    Factory function to create all 5 LpService sub-services.

    Handles cross-domain dependency: LpCoreService requires ps_service.

    Creation Order:
    1. LpSearchService (backend)
    2. UnifiedRelationshipService (backend, config, graph_intel)
    3. LpCoreService (backend, ps_service, event_bus)
    4. LpProgressService (executor, event_bus)
    5. LpIntelligenceService (backend, graph_intel, progress_backend, event_bus, user_service, executor)

    Args:
        backend: BackendOperations for LP entities (REQUIRED — created by composition root)
        executor: QueryExecutor for raw Cypher (REQUIRED — created by composition root)
        ps_service: PsService - REQUIRED for path-step operations
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

    # Step 3: Create core (requires ps_service)
    core = LpCoreService(
        backend=backend,
        ps_service=ps_service,
        event_bus=event_bus,
    )

    # Step 4: Create progress
    progress = LpProgressService(backend=backend, event_bus=event_bus)

    # Step 5: Create intelligence
    # ADR-030: Analytics services have zero AI dependencies
    intelligence = LpIntelligenceService(
        backend=backend,
        graph_intelligence_service=graph_intelligence_service,
        progress_backend=progress_backend,
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
