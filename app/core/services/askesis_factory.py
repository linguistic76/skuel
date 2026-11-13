"""
Askesis service composition — assembles AskesisService from bootstrap-level dependencies.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md (Askesis cross-cutting system)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.services.askesis_citation_service import AskesisCitationService
from core.services.askesis_service import AskesisDeps, AskesisService

if TYPE_CHECKING:
    from core.ports.askesis_protocols import AskesisCoreOperations
    from core.ports.zpd_protocols import ZPDOperations
    from core.services.activity_services import ActivityServices
    from core.services.canon import CanonRetrievalService
    from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
    from core.services.learning_services import LearningServices
    from core.services.llm_service import LLMService
    from core.services.ps_engagement.ps_engagement_service import PsEngagementService
    from core.services.user.intelligence import UserContextIntelligenceFactory
    from core.services.user_service import UserService


def create_askesis_service(
    *,
    intelligence_factory: UserContextIntelligenceFactory,
    learning_services: LearningServices,
    graph_intelligence: GraphIntelligenceService,
    llm_service: LLMService | None,
    activity_services: ActivityServices,
    user_service: UserService,
    askesis_core_service: AskesisCoreOperations,
    zpd_service: ZPDOperations,
    ps_engagement_service: PsEngagementService,
    citation_service: AskesisCitationService,
    canon_service: CanonRetrievalService | None = None,
) -> AskesisService:
    """Build AskesisService from the composition root's services.

    Askesis is created in the FULL intelligence tier only.

    Args:
        intelligence_factory: UserContextIntelligenceFactory (required).
        learning_services: The curriculum services — the embeddings service, the three
            curriculum facades and the Ku and PathStep backends they hold are read.
        graph_intelligence: GraphIntelligenceService.
        llm_service: LLMService — built in the FULL tier, where Askesis is created.
        activity_services: The six Activity facades — tasks, goals, habits, events and
            principles are read.
        user_service: UserOperations instance.
        askesis_core_service: AskesisCoreService — CRUD ops for Askesis instances.
        zpd_service: ZPDService — required for guided pipeline (ZPD readiness assessment).
            LP enrollment gate ensures curriculum data exists.
        ps_engagement_service: PsEngagementService — required for engagement-aware
            bundle loading (ADR-059). Always wired in FULL tier.
        citation_service: AskesisCitationService — formats graph citations for responses.
        canon_service: CanonRetrievalService — PS-scoped readings grounding for the
            guided pipeline (ADR-077). None when embeddings are absent; the pipeline
            degrades canon-free.
    """
    deps = AskesisDeps(
        intelligence_factory=intelligence_factory,
        graph_intel=graph_intelligence,
        user_service=user_service,
        askesis_core_service=askesis_core_service,
        llm_service=llm_service,
        embeddings_service=learning_services["embeddings_service"],
        knowledge_service=learning_services["ps"],
        tasks_service=activity_services["tasks"],
        goals_service=activity_services["goals"],
        habits_service=activity_services["habits"],
        events_service=activity_services["events"],
        zpd_service=zpd_service,
        ps_engagement_service=ps_engagement_service,
        citation_service=citation_service,
        canon_service=canon_service,
        # PS bundle dependencies for ContextRetriever
        ku_service=learning_services["atomic_ku_service"],
        lp_service=learning_services["learning_paths"],
        principles_service=activity_services["principles"],
        # Backends for ContextRetriever graph queries (migrated from inline Cypher)
        ku_backend=learning_services["atomic_ku_service"].backend,
        ps_backend=learning_services["ps"].repo,
    )
    return AskesisService(deps)
