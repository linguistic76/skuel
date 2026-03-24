"""AI service wiring — conditional on INTELLIGENCE_TIER=FULL."""

from typing import Any

from core.utils.logging import get_logger

logger = get_logger("skuel.bootstrap")


def _wire_ai_services(
    llm_service: Any,
    embeddings_service: Any,
    activity_services: dict[str, Any],
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

    # NOTE: MocAIService removed (January 2026) - MOC is now KU-based

    # Create AI services for Activity Domains (6)
    tasks_ai = TasksAIService(
        backend=activity_services["tasks"].core.backend,
        llm_service=llm_service,
        embeddings_service=embeddings_service,
    )
    goals_ai = GoalsAIService(
        backend=activity_services["goals"].core.backend,
        llm_service=llm_service,
        embeddings_service=embeddings_service,
    )
    habits_ai = HabitsAIService(
        backend=activity_services["habits"].core.backend,
        llm_service=llm_service,
        embeddings_service=embeddings_service,
    )
    events_ai = EventsAIService(
        backend=activity_services["events"].core.backend,
        llm_service=llm_service,
        embeddings_service=embeddings_service,
    )
    choices_ai = ChoicesAIService(
        backend=activity_services["choices"].core.backend,
        llm_service=llm_service,
        embeddings_service=embeddings_service,
    )
    principles_ai = PrinciplesAIService(
        backend=activity_services["principles"].core.backend,
        llm_service=llm_service,
        embeddings_service=embeddings_service,
    )

    # Wire AI services into Activity Domain facades (post-construction)
    activity_services["tasks"].ai = tasks_ai
    activity_services["goals"].ai = goals_ai
    activity_services["habits"].ai = habits_ai
    activity_services["events"].ai = events_ai
    activity_services["choices"].ai = choices_ai
    activity_services["principles"].ai = principles_ai

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
        "✅ AI services created and wired (12 services: 6 Activity + 4 Curriculum + 2 cross-cutting)"
    )
    return askesis_ai, context_aware_ai
