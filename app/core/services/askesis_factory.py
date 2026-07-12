"""
Askesis service composition — assembles AskesisService from bootstrap-level dependencies.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md (Askesis cross-cutting system)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.services.askesis_citation_service import AskesisCitationService
from core.services.askesis_service import AskesisDeps, AskesisService

if TYPE_CHECKING:
    from core.ports.askesis_protocols import AskesisCoreOperations
    from core.ports.zpd_protocols import ZPDOperations
    from core.services.canon import CanonRetrievalService
    from core.services.user.intelligence import UserContextIntelligenceFactory


def create_askesis_service(
    *,
    intelligence_factory: UserContextIntelligenceFactory,
    learning_services: dict[str, Any],
    activity_services: dict[str, Any],
    user_service: Any,
    askesis_core_service: AskesisCoreOperations,
    zpd_service: ZPDOperations,
    ps_engagement_service: Any,
    citation_service: AskesisCitationService,
    canon_service: CanonRetrievalService | None = None,
) -> AskesisService:
    """Build AskesisService from bootstrap-level service dicts.

    All dependencies are required — Askesis is only created when
    INTELLIGENCE_TIER=FULL. KeyError on missing deps is intentional.

    Args:
        intelligence_factory: UserContextIntelligenceFactory (required).
        learning_services: Dict from _create_learning_services() — keys: graph_intelligence,
            llm_service, embeddings_service, path_steps.
        activity_services: Dict from _create_activity_services() — keys: tasks, goals,
            habits, events.
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
        graph_intel=learning_services["graph_intelligence"],
        user_service=user_service,
        askesis_core_service=askesis_core_service,
        llm_service=learning_services["llm_service"],
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
        ku_service=learning_services.get("atomic_ku_service"),
        lp_service=learning_services.get("learning_paths"),
        principles_service=activity_services.get("principles"),
        # Backends for ContextRetriever graph queries (migrated from inline Cypher)
        ku_backend=getattr(learning_services.get("atomic_ku_service"), "backend", None),
        ps_backend=getattr(learning_services.get("ps"), "repo", None),
    )
    return AskesisService(deps)
