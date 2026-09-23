"""AI service wiring — conditional on INTELLIGENCE_TIER=FULL."""

from typing import Any

from core.utils.logging import get_logger

logger = get_logger("skuel.bootstrap")


def _wire_ai_services(
    llm_service: Any,
    embeddings_service: Any,
    _activity_services: dict[str, Any],
    learning_services: dict[str, Any],
) -> None:
    """Create and wire AI services into domain facades (ADR-030: Two-Tier Intelligence).

    Every facade's ``.ai`` stays None if LLM/embeddings are unavailable.
    """
    if not (llm_service and embeddings_service):
        logger.info("⚠️ AI services skipped (LLM or embeddings not available)")
        return

    from core.services.choices.choices_ai_service import ChoicesAIService
    from core.services.events.events_ai_service import EventsAIService
    from core.services.goals.goals_ai_service import GoalsAIService
    from core.services.habits.habits_ai_service import HabitsAIService
    from core.services.lp.lp_ai_service import LpAIService
    from core.services.principles.principles_ai_service import PrinciplesAIService
    from core.services.ps.ps_ai_service import PsAIService
    from core.services.tasks.tasks_ai_service import TasksAIService

    # Create AI services for Activity Domains (6)
    for domain_key in ("tasks", "events", "habits", "goals", "choices", "principles"):
        ai_cls = {
            "tasks": TasksAIService,
            "events": EventsAIService,
            "habits": HabitsAIService,
            "goals": GoalsAIService,
            "choices": ChoicesAIService,
            "principles": PrinciplesAIService,
        }[domain_key]
        facade = _activity_services[domain_key]
        facade.ai = ai_cls(
            backend=facade.core.backend,
            llm_service=llm_service,
            embeddings_service=embeddings_service,
        )

    # Create AI services for Curriculum Domains (2)
    ps_ai = PsAIService(
        backend=learning_services["ps"].core.backend,
        llm_service=llm_service,
        embeddings_service=embeddings_service,
    )
    lp_ai = LpAIService(
        backend=learning_services["learning_paths"].core.backend,
        llm_service=llm_service,
        embeddings_service=embeddings_service,
    )
    # Wire AI services into Curriculum Domain facades (post-construction)
    learning_services["ps"].ai = ps_ai
    learning_services["learning_paths"].ai = lp_ai

    logger.info("✅ AI services created and wired (8 services: 6 Activity + 2 Curriculum)")
