"""
AI Routes - Optional AI-Powered Features
=========================================

Routes for AI-powered domain features (ADR-030: Two-Tier Intelligence Design).

AI services are OPTIONAL - the app functions fully without them.
When AI is unavailable, routes return 503 Service Unavailable with explicit message.

This follows SKUEL's fail-fast philosophy:
- Be explicit about what's not available
- Return clear error responses rather than silent failures
- No hiding problems or pretending things work

Pattern: Each route is declared as a config tuple; _ai_route handles auth,
availability check, error propagation, and response wrapping.
"""

from typing import Any

from starlette.responses import JSONResponse

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.ai")


def _ai_unavailable_response(domain_label: str) -> JSONResponse:
    """Return explicit 503 when AI service is unavailable."""
    return JSONResponse(
        status_code=503,
        content={
            "error": "AI service unavailable",
            "message": f"{domain_label} AI features require LLM/embeddings services",
            "domain": domain_label,
        },
    )


async def _ai_route(
    request: Any,
    services: Any,
    domain_attr: str,
    domain_label: str,
    method_name: str,
    args: tuple[Any, ...],
    wrap_key: str | None = None,
) -> dict[str, Any] | JSONResponse:
    """Shared handler for all AI routes.

    Handles auth, AI availability check, method call, error propagation,
    and optional response wrapping.

    Args:
        request: Starlette request
        services: Service container
        domain_attr: Attribute name on services (e.g. "tasks", "article")
        domain_label: Human-readable domain name for error messages
        method_name: AI service method to call
        args: Positional args to pass to the method
        wrap_key: If set, wrap result.value as {wrap_key: value}; otherwise return raw
    """
    require_authenticated_user(request)
    facade = getattr(services, domain_attr)
    if not facade.ai:
        return _ai_unavailable_response(domain_label)
    result = await getattr(facade.ai, method_name)(*args)
    if result.is_error:
        return JSONResponse(status_code=400, content={"error": str(result.error)})
    if wrap_key:
        return {wrap_key: result.value}
    value: dict[str, Any] = result.value
    return value


def create_ai_routes(app: Any, rt: Any, services: Any) -> list[Any]:
    """Create routes for AI-powered domain features.

    All routes check if the domain's .ai service is available.
    Returns 503 Service Unavailable if AI is not configured.
    """
    route_count = 0

    # ------------------------------------------------------------------
    # TASKS AI ROUTES
    # ------------------------------------------------------------------

    @rt("/api/tasks/ai/similar")
    async def tasks_ai_similar(request: Any, uid: str, limit: int = 5) -> Any:
        """Find semantically similar tasks."""
        return await _ai_route(
            request,
            services,
            "tasks",
            "Tasks",
            "find_similar_tasks",
            (uid, limit),
            wrap_key="similar_tasks",
        )

    @rt("/api/tasks/ai/insight")
    async def tasks_ai_insight(request: Any, uid: str) -> Any:
        """Generate AI insight about a task."""
        return await _ai_route(
            request, services, "tasks", "Tasks", "generate_task_insight", (uid,), wrap_key="insight"
        )

    @rt("/api/tasks/ai/knowledge-generation")
    async def tasks_ai_knowledge_generation(request: Any, uid: str) -> Any:
        """Identify knowledge generation opportunities from a task."""
        return await _ai_route(
            request, services, "tasks", "Tasks", "identify_knowledge_generation", (uid,)
        )

    # ------------------------------------------------------------------
    # GOALS AI ROUTES
    # ------------------------------------------------------------------

    @rt("/api/goals/ai/similar")
    async def goals_ai_similar(request: Any, uid: str, limit: int = 5) -> Any:
        """Find semantically similar goals."""
        return await _ai_route(
            request,
            services,
            "goals",
            "Goals",
            "find_similar_goals",
            (uid, limit),
            wrap_key="similar_goals",
        )

    @rt("/api/goals/ai/insight")
    async def goals_ai_insight(request: Any, uid: str) -> Any:
        """Generate AI insight about a goal."""
        return await _ai_route(
            request, services, "goals", "Goals", "generate_goal_insight", (uid,), wrap_key="insight"
        )

    @rt("/api/goals/ai/milestones")
    async def goals_ai_milestones(request: Any, uid: str) -> Any:
        """Generate suggested milestones for a goal."""
        return await _ai_route(request, services, "goals", "Goals", "generate_milestones", (uid,))

    @rt("/api/goals/ai/smart-refinement")
    async def goals_ai_smart_refinement(request: Any, uid: str) -> Any:
        """Suggest SMART refinements for a goal."""
        return await _ai_route(
            request, services, "goals", "Goals", "suggest_smart_refinement", (uid,)
        )

    # ------------------------------------------------------------------
    # HABITS AI ROUTES
    # ------------------------------------------------------------------

    @rt("/api/habits/ai/similar")
    async def habits_ai_similar(request: Any, uid: str, limit: int = 5) -> Any:
        """Find semantically similar habits."""
        return await _ai_route(
            request,
            services,
            "habits",
            "Habits",
            "find_similar_habits",
            (uid, limit),
            wrap_key="similar_habits",
        )

    @rt("/api/habits/ai/streak-insight")
    async def habits_ai_streak_insight(request: Any, uid: str) -> Any:
        """Generate AI insight about habit streak patterns."""
        return await _ai_route(
            request,
            services,
            "habits",
            "Habits",
            "generate_streak_insight",
            (uid,),
            wrap_key="insight",
        )

    @rt("/api/habits/ai/habit-stack")
    async def habits_ai_habit_stack(request: Any, uid: str) -> Any:
        """Suggest habit stacking opportunities."""
        return await _ai_route(request, services, "habits", "Habits", "suggest_habit_stack", (uid,))

    @rt("/api/habits/ai/optimize-loop")
    async def habits_ai_optimize_loop(request: Any, uid: str) -> Any:
        """Optimize the cue-routine-reward loop for a habit."""
        return await _ai_route(request, services, "habits", "Habits", "optimize_habit_loop", (uid,))

    # ------------------------------------------------------------------
    # EVENTS AI ROUTES
    # ------------------------------------------------------------------

    @rt("/api/events/ai/similar")
    async def events_ai_similar(request: Any, uid: str, limit: int = 5) -> Any:
        """Find semantically similar events."""
        return await _ai_route(
            request,
            services,
            "events",
            "Events",
            "find_similar_events",
            (uid, limit),
            wrap_key="similar_events",
        )

    @rt("/api/events/ai/insight")
    async def events_ai_insight(request: Any, uid: str) -> Any:
        """Generate AI insight about an event."""
        return await _ai_route(
            request,
            services,
            "events",
            "Events",
            "generate_event_insight",
            (uid,),
            wrap_key="insight",
        )

    @rt("/api/events/ai/preparation")
    async def events_ai_preparation(request: Any, uid: str) -> Any:
        """Generate preparation checklist for an event."""
        return await _ai_route(
            request, services, "events", "Events", "generate_preparation_checklist", (uid,)
        )

    @rt("/api/events/ai/reflection")
    async def events_ai_reflection(request: Any, uid: str) -> Any:
        """Generate reflection prompts for an event."""
        return await _ai_route(
            request, services, "events", "Events", "suggest_reflection_prompts", (uid,)
        )

    # ------------------------------------------------------------------
    # CHOICES AI ROUTES
    # ------------------------------------------------------------------

    @rt("/api/choices/ai/similar")
    async def choices_ai_similar(request: Any, uid: str, limit: int = 5) -> Any:
        """Find semantically similar choices."""
        return await _ai_route(
            request,
            services,
            "choices",
            "Choices",
            "find_similar_choices",
            (uid, limit),
            wrap_key="similar_choices",
        )

    @rt("/api/choices/ai/insight")
    async def choices_ai_insight(request: Any, uid: str) -> Any:
        """Generate AI insight about a choice."""
        return await _ai_route(
            request,
            services,
            "choices",
            "Choices",
            "generate_choice_insight",
            (uid,),
            wrap_key="insight",
        )

    @rt("/api/choices/ai/framework")
    async def choices_ai_framework(request: Any, uid: str) -> Any:
        """Suggest a decision-making framework for a choice."""
        return await _ai_route(
            request, services, "choices", "Choices", "suggest_decision_framework", (uid,)
        )

    @rt("/api/choices/ai/alternatives")
    async def choices_ai_alternatives(request: Any, uid: str) -> Any:
        """Generate alternative options for a choice."""
        return await _ai_route(
            request, services, "choices", "Choices", "generate_alternatives", (uid,)
        )

    # ------------------------------------------------------------------
    # PRINCIPLES AI ROUTES
    # ------------------------------------------------------------------

    @rt("/api/principles/ai/similar")
    async def principles_ai_similar(request: Any, uid: str, limit: int = 5) -> Any:
        """Find semantically similar principles."""
        return await _ai_route(
            request,
            services,
            "principles",
            "Principles",
            "find_similar_principles",
            (uid, limit),
            wrap_key="similar_principles",
        )

    @rt("/api/principles/ai/insight")
    async def principles_ai_insight(request: Any, uid: str) -> Any:
        """Generate AI insight about a principle."""
        return await _ai_route(
            request,
            services,
            "principles",
            "Principles",
            "generate_principle_insight",
            (uid,),
            wrap_key="insight",
        )

    @rt("/api/principles/ai/deepen")
    async def principles_ai_deepen(request: Any, uid: str) -> Any:
        """Deepen understanding of a principle."""
        return await _ai_route(
            request, services, "principles", "Principles", "deepen_principle", (uid,)
        )

    @rt("/api/principles/ai/practices")
    async def principles_ai_practices(request: Any, uid: str) -> Any:
        """Suggest practices to embody a principle."""
        return await _ai_route(
            request, services, "principles", "Principles", "suggest_practices", (uid,)
        )

    # ------------------------------------------------------------------
    # KNOWLEDGE (ARTICLE) AI ROUTES
    # ------------------------------------------------------------------

    @rt("/api/knowledge/ai/related")
    async def knowledge_ai_related(request: Any, uid: str, limit: int = 5) -> Any:
        """Find semantically related knowledge units."""
        return await _ai_route(
            request,
            services,
            "article",
            "Knowledge",
            "find_related_articles",
            (uid, limit),
            wrap_key="related_knowledge",
        )

    @rt("/api/knowledge/ai/search")
    async def knowledge_ai_search(request: Any, query: str, limit: int = 10) -> Any:
        """Semantic search for knowledge units."""
        return await _ai_route(
            request,
            services,
            "article",
            "Knowledge",
            "semantic_search",
            (query, limit),
            wrap_key="results",
        )

    @rt("/api/knowledge/ai/summary")
    async def knowledge_ai_summary(request: Any, uid: str) -> Any:
        """Generate AI summary of a knowledge unit."""
        return await _ai_route(
            request,
            services,
            "article",
            "Knowledge",
            "generate_summary",
            (uid,),
            wrap_key="summary",
        )

    @rt("/api/knowledge/ai/explain")
    async def knowledge_ai_explain(request: Any, uid: str, level: str = "intermediate") -> Any:
        """Explain a knowledge unit at a specified level."""
        return await _ai_route(
            request, services, "article", "Knowledge", "explain_at_level", (uid, level)
        )

    @rt("/api/knowledge/ai/applications")
    async def knowledge_ai_applications(request: Any, uid: str) -> Any:
        """Suggest practical applications of knowledge."""
        return await _ai_route(
            request, services, "article", "Knowledge", "suggest_applications", (uid,)
        )

    # ------------------------------------------------------------------
    # LEARNING STEPS (LS) AI ROUTES
    # ------------------------------------------------------------------

    @rt("/api/learning-steps/ai/similar")
    async def ls_ai_similar(request: Any, uid: str, limit: int = 5) -> Any:
        """Find semantically similar learning steps."""
        return await _ai_route(
            request,
            services,
            "ls",
            "Learning Steps",
            "find_similar_steps",
            (uid, limit),
            wrap_key="similar_steps",
        )

    @rt("/api/learning-steps/ai/insight")
    async def ls_ai_insight(request: Any, uid: str) -> Any:
        """Generate AI insight about a learning step."""
        return await _ai_route(
            request,
            services,
            "ls",
            "Learning Steps",
            "generate_step_insight",
            (uid,),
            wrap_key="insight",
        )

    @rt("/api/learning-steps/ai/explain")
    async def ls_ai_explain(request: Any, uid: str, level: str = "intermediate") -> Any:
        """Explain a learning step at a specified level."""
        return await _ai_route(
            request, services, "ls", "Learning Steps", "explain_step", (uid, level)
        )

    @rt("/api/learning-steps/ai/practice")
    async def ls_ai_practice(request: Any, uid: str) -> Any:
        """Suggest practice activities for a learning step."""
        return await _ai_route(
            request, services, "ls", "Learning Steps", "suggest_practice_activities", (uid,)
        )

    # ------------------------------------------------------------------
    # LEARNING PATHS (LP) AI ROUTES
    # ------------------------------------------------------------------

    @rt("/api/learning-paths/ai/similar")
    async def lp_ai_similar(request: Any, uid: str, limit: int = 5) -> Any:
        """Find semantically similar learning paths."""
        return await _ai_route(
            request,
            services,
            "lp",
            "Learning Paths",
            "find_similar_paths",
            (uid, limit),
            wrap_key="similar_paths",
        )

    @rt("/api/learning-paths/ai/insight")
    async def lp_ai_insight(request: Any, uid: str) -> Any:
        """Generate AI insight about a learning path."""
        return await _ai_route(
            request,
            services,
            "lp",
            "Learning Paths",
            "generate_path_insight",
            (uid,),
            wrap_key="insight",
        )

    @rt("/api/learning-paths/ai/overview")
    async def lp_ai_overview(request: Any, uid: str) -> Any:
        """Generate an engaging overview of a learning path."""
        return await _ai_route(
            request, services, "lp", "Learning Paths", "generate_path_overview", (uid,)
        )

    @rt("/api/learning-paths/ai/strategy")
    async def lp_ai_strategy(request: Any, uid: str) -> Any:
        """Suggest a completion strategy for a learning path."""
        return await _ai_route(
            request, services, "lp", "Learning Paths", "suggest_completion_strategy", (uid,)
        )

    # ------------------------------------------------------------------
    # AI STATUS ENDPOINT
    # ------------------------------------------------------------------

    @rt("/api/ai/status")
    async def ai_status(request: Any) -> dict[str, Any]:
        """Check which AI services are available."""
        require_authenticated_user(request)
        return {
            "ai_available": {
                "tasks": services.tasks.ai is not None,
                "goals": services.goals.ai is not None,
                "habits": services.habits.ai is not None,
                "events": services.events.ai is not None,
                "choices": services.choices.ai is not None,
                "principles": services.principles.ai is not None,
                "knowledge": services.article.ai is not None,
                "learning_steps": services.ls.ai is not None,
                "learning_paths": services.lp.ai is not None,
            }
        }

    # Count routes for logging (decorators register immediately)
    route_count = 31  # 30 AI routes + 1 status
    logger.info(f"AI routes registered ({route_count} endpoints)")

    # Return empty list — @rt() registers routes immediately
    return []


__all__ = ["create_ai_routes"]
