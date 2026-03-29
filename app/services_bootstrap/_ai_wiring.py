"""AI service wiring — conditional on INTELLIGENCE_TIER=FULL."""

from typing import Any

from core.utils.logging import get_logger

logger = get_logger("skuel.bootstrap")


def _wire_ai_services(
    llm_service: Any,
    embeddings_service: Any,
    _activity_services: dict[str, Any],
    learning_services: dict[str, Any],
    user_service: Any,
    graph_intelligence: Any,
) -> tuple[Any, Any]:
    """Create and wire AI services into domain facades (ADR-030: Two-Tier Intelligence).

    Returns (askesis_ai, context_aware_ai). Both None if LLM/embeddings unavailable.
    """
    if not (llm_service and embeddings_service):
        logger.info("⚠️ AI services skipped (LLM or embeddings not available)")
        return None, None

    from core.services.askesis_ai_service import AskesisAIService
    from core.services.choices.choices_ai_service import ChoicesAIService
    from core.services.context_aware_ai_service import ContextAwareAIService
    from core.services.events.events_ai_service import EventsAIService
    from core.services.goals.goals_ai_service import GoalsAIService
    from core.services.habits.habits_ai_service import HabitsAIService
    from core.services.lesson.lesson_ai_service import LessonAIService
    from core.services.lp.lp_ai_service import LpAIService
    from core.services.ls.ls_ai_service import LsAIService
    from core.services.principles.principles_ai_service import PrinciplesAIService
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

    # Create AI services for Curriculum Domains (3)
    ku_ai = LessonAIService(
        backend=learning_services["lesson_service"].core.backend,
        llm_service=llm_service,
        embeddings_service=embeddings_service,
    )
    ls_ai = LsAIService(
        backend=learning_services["learning_steps"].core.backend,
        llm_service=llm_service,
        embeddings_service=embeddings_service,
    )
    lp_ai = LpAIService(
        backend=learning_services["learning_paths"].core.backend,
        llm_service=llm_service,
        embeddings_service=embeddings_service,
    )
    # Wire AI services into Curriculum Domain facades (post-construction)
    learning_services["lesson_service"].ai = ku_ai
    learning_services["learning_steps"].ai = ls_ai
    learning_services["learning_paths"].ai = lp_ai

    # Create cross-cutting AI services (2)
    askesis_ai = AskesisAIService(
        backend=user_service,  # Uses UserService for user state
        llm_service=llm_service,
        embeddings_service=embeddings_service,
        graph_intelligence_service=graph_intelligence,
    )
    context_aware_ai = ContextAwareAIService(
        backend=user_service,  # Uses UserContextOperations
        llm_service=llm_service,
        embeddings_service=embeddings_service,
        graph_intelligence_service=graph_intelligence,
    )

    logger.info(
        "✅ AI services created and wired (11 services: 6 Activity + 3 Curriculum + 2 cross-cutting)"
    )
    return askesis_ai, context_aware_ai
