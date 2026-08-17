"""
Curriculum Domain Sub-Service Factories
=======================================

Factory functions for the 3 Curriculum Domain facades (Ku, Ps, Lp). Each facade has
its own factory — ``create_curriculum_sub_services`` (Ku), ``create_ps_sub_services``,
``create_lp_sub_services`` — because their sub-service wiring genuinely differs.

All three import their service classes directly. There is no module-name registry and
no dynamic lookup: the classes each factory builds are fixed and statically known, so
naming them is both shorter and checkable. See ``activity_domain_config`` for the
registry-driven counterpart, which has six domains to vary over and therefore earns one.

Usage (Ku):
    from core.services.curriculum_domain_config import create_curriculum_sub_services

    common = create_curriculum_sub_services(
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
from core.services.ku.ku_core_service import KuCoreService
from core.services.ku.ku_intelligence_service import KuIntelligenceService
from core.services.ku.ku_search_service import KuSearchService
from core.services.relationships import UnifiedRelationshipService

if TYPE_CHECKING:
    from core.ports import EventBusOperations
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
T_Intelligence = TypeVar("T_Intelligence")  # Intelligence service type


@dataclass
class CurriculumCommonSubServices(Generic[T_Intelligence]):
    """
    Container for the 4 common sub-services created by the factory.

    Generic over T_Intelligence to preserve the concrete intelligence service type.
    The factory returns it already parameterized; facades annotate the assignment to
    state the contract at the seam:

        common: CurriculumCommonSubServices[KuIntelligenceService] = create_curriculum_sub_services(...)
        self.intelligence = common.intelligence # MyPy knows this is KuIntelligenceService
    """

    core: Any
    search: Any
    relationships: UnifiedRelationshipService
    intelligence: T_Intelligence


def create_curriculum_sub_services(
    backend: Any,
    graph_intel: Any,
    event_bus: Any = None,
) -> CurriculumCommonSubServices[KuIntelligenceService]:
    """
    Factory function to create Ku's 4 common sub-services.

    This mirrors the Activity domain factory pattern (create_common_sub_services).
    It eliminates repetitive initialization code and ensures consistent wiring.

    Args:
        backend: Ku backend operations (UniversalNeo4jBackend[Ku])
        graph_intel: GraphIntelligenceService for analytics (REQUIRED for consistency)
        event_bus: Event bus for domain events (optional)

    Returns:
        CurriculumCommonSubServices dataclass with core, search, relationships, intelligence.

    Note:
        Ku only. Ps and Lp have dedicated factories (create_ps_sub_services,
        create_lp_sub_services) because their wiring differs.
    """
    # Create relationships service FIRST (needed by intelligence)
    relationships: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=backend,
        config=KU_CONFIG,
        graph_intel=graph_intel,
    )

    intelligence = KuIntelligenceService(
        backend=backend,
        graph_intel=graph_intel,
        relationship_service=relationships,
    )

    core = KuCoreService(backend=backend, event_bus=event_bus)

    search = KuSearchService(backend=backend)

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
    4. PsSearchService (backend)
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
