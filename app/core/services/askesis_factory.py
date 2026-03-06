"""
Askesis service composition — assembles AskesisService from bootstrap-level dependencies.

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md (Askesis cross-cutting system)
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

    Args:
        intelligence_factory: Required UserContextIntelligenceFactory.
        learning_services: Dict from _create_learning_services() — keys: graph_intelligence,
            llm_service, embeddings_service, ku_service.
        activity_services: Dict from _create_activity_services() — keys: tasks, goals,
            habits, events.
        user_service: UserOperations instance.
        zpd_service: Optional ZPDService — enriches analyze_user_state() with ZPDAssessment.
            None when INTELLIGENCE_TIER=CORE or curriculum graph has < 3 KUs.
    """
    deps = AskesisDeps(
        intelligence_factory=intelligence_factory,
        graph_intelligence_service=learning_services.get("graph_intelligence"),
        user_service=user_service,
        llm_service=learning_services.get("llm_service"),
        embeddings_service=learning_services.get("embeddings_service"),
        knowledge_service=learning_services.get("article_service"),
        tasks_service=activity_services.get("tasks"),
        goals_service=activity_services.get("goals"),
        habits_service=activity_services.get("habits"),
        events_service=activity_services.get("events"),
        zpd_service=zpd_service,
    )
    return AskesisService(deps)
