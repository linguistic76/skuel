"""
Askesis service composition — assembles AskesisService from bootstrap-level dependencies.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md (Askesis cross-cutting system)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.services.askesis_service import AskesisDeps, AskesisService

if TYPE_CHECKING:
    from core.ports.zpd_protocols import ZPDOperations
    from core.services.user.intelligence import UserContextIntelligenceFactory


def create_askesis_service(
    *,
    intelligence_factory: UserContextIntelligenceFactory,
    learning_services: dict[str, Any],
    activity_services: dict[str, Any],
    user_service: Any,
    zpd_service: ZPDOperations | None = None,
) -> AskesisService:
    """Build AskesisService from bootstrap-level service dicts.

    All dependencies are required — Askesis is only created when
    INTELLIGENCE_TIER=FULL. KeyError on missing deps is intentional.

    Args:
        intelligence_factory: UserContextIntelligenceFactory (required).
        learning_services: Dict from _create_learning_services() — keys: graph_intelligence,
            llm_service, embeddings_service, article_service.
        activity_services: Dict from _create_activity_services() — keys: tasks, goals,
            habits, events.
        user_service: UserOperations instance.
        zpd_service: Optional ZPDService — enriches analyze_user_state() with ZPDAssessment.
            None when curriculum graph has < 3 KUs (data condition, not degradation).
    """
    deps = AskesisDeps(
        intelligence_factory=intelligence_factory,
        graph_intelligence_service=learning_services["graph_intelligence"],
        user_service=user_service,
        llm_service=learning_services["llm_service"],
        embeddings_service=learning_services["embeddings_service"],
        knowledge_service=learning_services["article_service"],
        tasks_service=activity_services["tasks"],
        goals_service=activity_services["goals"],
        habits_service=activity_services["habits"],
        events_service=activity_services["events"],
        zpd_service=zpd_service,
    )
    return AskesisService(deps)
