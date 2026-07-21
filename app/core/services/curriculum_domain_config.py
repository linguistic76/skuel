"""
Curriculum Domain Configuration Registry
=========================================

Centralizes configuration and factory functions for the 3 Curriculum Domain facades
(Ku, Ps, Lp). The generic ``create_curriculum_sub_services`` factory is used only by
Ku; Ps and Lp have dedicated factories (``create_ps_sub_services``,
``create_lp_sub_services``) due to non-standard sub-service wiring.

``CURRICULUM_DOMAIN_CONFIGS`` — 1 entry (Ku only):
Each entry provides core/search/intelligence module strings + relationship config,
consumed by ``create_curriculum_sub_services`` for dynamic instantiation.

Usage (Ku):
    from core.services.curriculum_domain_config import (
        CURRICULUM_DOMAIN_CONFIGS,
        create_curriculum_sub_services,
    )

    common = create_curriculum_sub_services(
        domain="ku",
        backend=backend,
        graph_intel=graph_intel,
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
    from core.ports import EventBusOperations, QueryBuilderOperations
    from core.services.lp.lp_core_service import LpCoreService
    from core.services.lp.lp_intelligence_service import LpIntelligenceService
    from core.services.lp.lp_progress_service import LpProgressService
    from core.services.lp.lp_search_service import LpSearchService
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


# Registry for Curriculum Domains that use the generic create_curriculum_sub_services factory.
# Only Ku uses the generic factory — Ps and Lp have dedicated factories
# (create_ps_sub_services, create_lp_sub_services) with non-standard wiring.
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
        Only Ku uses this factory. Ps and Lp have dedicated factories
        (create_ps_sub_services, create_lp_sub_services) due to non-standard wiring.
    """
    import importlib

    config = CURRICULUM_DOMAIN_CONFIGS[domain]

    # Create relationships service FIRST (needed by intelligence)
    relationships: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
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
        graph_intel=graph_intel,
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
    _chunking_service: Any | None,
    graph_intel: Any,
    _query_builder: "QueryBuilderOperations | None",
    event_bus: "EventBusOperations | None",
    _executor: Any | None = None,
    user_service: Any | None = None,
    _vector_search_service: Any | None = None,
    _embeddings_service: Any | None = None,
    ps_intelligence_backend: Any | None = None,
) -> "PsSubServices":
    """Factory function to create all 12 PsService sub-services.

    Creation Order:
    1. UnifiedRelationshipService (backend, config, graph_intel)
    2. PsIntelligenceService (backend, graph_intel, relationships, user_service)
    3. PsCoreService (backend, event_bus)
    4. PsSearchService (backend, intelligence, query_builder, vector_search, embeddings)
    5. PsGraphService (repo, graph_intel)
    6. PsSemanticService (repo, intelligence)
    7. PsPracticeService (backend, event_bus)
    8. PsMasteryService (backend, event_bus)
    9. PsAdaptiveService (backend, user_service)
    10. PsApplicationDiscoveryService (repo)
    11. PsContextService (repo)
    12. PsOrganizationService (ps_core, backend)
    """
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

    # Step 1: Create relationship service (needed by intelligence)
    relationships: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=backend,
        config=PS_CONFIG,
        graph_intel=graph_intel,
    )

    # Step 2: Create intelligence BEFORE core (circular dependency)
    intelligence = PsIntelligenceService(
        backend=backend,
        graph_intel=graph_intel,
        relationship_service=relationships,
        intelligence_backend=ps_intelligence_backend,
    )

    # Step 3: Create core
    core = PsCoreService(backend=backend, event_bus=event_bus)

    # Step 4: Create search
    search = PsSearchService(backend=backend)

    # Step 5: Create graph
    graph = PsGraphService(repo=backend, graph_intel=graph_intel)

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

    # Step 12: Organization service — uses core for PathStep lookups
    organization = PsOrganizationService(ps_core=core, backend=backend)

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


@dataclass
class PsSubServices:
    """Container for all PsService sub-services created by the factory."""

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
class LpSubServices:
    """Container for all LpService sub-services created by the factory."""

    core: "LpCoreService"
    search: "LpSearchService"
    relationships: "UnifiedRelationshipService"
    intelligence: "LpIntelligenceService"
    progress: "LpProgressService"


def create_lp_sub_services(
    backend: Any,
    ps_service: "PsService",
    graph_intel: Any,
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
    4. LpProgressService (backend, event_bus)
    5. LpIntelligenceService (backend, graph_intel, progress_backend, event_bus, user_service)

    Args:
        backend: BackendOperations for LP entities (REQUIRED — created by composition root)
        ps_service: PsService - REQUIRED for path-step operations
        graph_intel: GraphIntelligenceService - REQUIRED
        event_bus: Event bus for publishing domain events (optional)
        progress_backend: UserProgress backend for learning state (optional)
        user_service: UserService for UserContext access (optional)

    Returns:
        LpSubServices dataclass with all 5 sub-services + backend
    """
    # Lazy imports (core-only — no adapter imports)
    from core.services.lp.lp_core_service import LpCoreService
    from core.services.lp.lp_intelligence_service import LpIntelligenceService
    from core.services.lp.lp_progress_service import LpProgressService
    from core.services.lp.lp_search_service import LpSearchService

    # Step 1: Create search (simple, no dependencies)
    search = LpSearchService(backend=backend)

    # Step 2: Create relationships
    relationships: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=backend,
        config=LP_CONFIG,
        graph_intel=graph_intel,
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
    # ADR-030: Analytics services have zero AI dependencies.
    # relationship_service is REQUIRED for the inherited mechanism-B get_with_context
    # (registry-sourced graph context); matches Ku/Ps wiring.
    # ps_service.intelligence provides per-step practice reads for identify_practice_gaps
    # — reusing the PS practice measure rather than forking it (One Path Forward).
    intelligence = LpIntelligenceService(
        backend=backend,
        graph_intel=graph_intel,
        relationship_service=relationships,
        progress_backend=progress_backend,
        event_bus=event_bus,
        user_service=user_service,
        ps_intelligence=ps_service.intelligence,
    )

    return LpSubServices(
        core=core,
        search=search,
        relationships=relationships,
        intelligence=intelligence,
        progress=progress,
    )
