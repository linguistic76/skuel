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

Pattern: Check if facade.ai is available, return 503 if not.
"""

from starlette.responses import JSONResponse

from core.auth import require_authenticated_user
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.ai")


def _ai_unavailable_response(domain: str) -> JSONResponse:
    """Return explicit 503 when AI service is unavailable."""
    return JSONResponse(
        status_code=503,
        content={
            "error": "AI service unavailable",
            "message": f"{domain} AI features require LLM/embeddings services",
            "domain": domain,
        },
    )


def create_ai_routes(app, rt, services):
    """
    Create routes for AI-powered domain features.

    All routes check if the domain's .ai service is available.
    Returns 503 Service Unavailable if AI is not configured.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container

    Returns:
        List of registered route functions
    """
    routes = []

    # ==========================================================================
    # TASKS AI ROUTES
    # ==========================================================================

    @rt("/api/tasks/ai/similar")
    async def tasks_ai_similar(request, uid: str, limit: int = 5):
        """Find semantically similar tasks."""
        require_authenticated_user(request)
        if not services.tasks.ai:
            return _ai_unavailable_response("Tasks")
        result = await services.tasks.ai.find_similar_tasks(uid, limit)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"similar_tasks": result.value}

    routes.append(tasks_ai_similar)

    @rt("/api/tasks/ai/insight")
    async def tasks_ai_insight(request, uid: str):
        """Generate AI insight about a task."""
        require_authenticated_user(request)
        if not services.tasks.ai:
            return _ai_unavailable_response("Tasks")
        result = await services.tasks.ai.generate_task_insight(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"insight": result.value}

    routes.append(tasks_ai_insight)

    @rt("/api/tasks/ai/knowledge-generation")
    async def tasks_ai_knowledge_generation(request, uid: str):
        """Identify knowledge generation opportunities from a task."""
        require_authenticated_user(request)
        if not services.tasks.ai:
            return _ai_unavailable_response("Tasks")
        result = await services.tasks.ai.identify_knowledge_generation(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(tasks_ai_knowledge_generation)

    # ==========================================================================
    # GOALS AI ROUTES
    # ==========================================================================

    @rt("/api/goals/ai/similar")
    async def goals_ai_similar(request, uid: str, limit: int = 5):
        """Find semantically similar goals."""
        require_authenticated_user(request)
        if not services.goals.ai:
            return _ai_unavailable_response("Goals")
        result = await services.goals.ai.find_similar_goals(uid, limit)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"similar_goals": result.value}

    routes.append(goals_ai_similar)

    @rt("/api/goals/ai/insight")
    async def goals_ai_insight(request, uid: str):
        """Generate AI insight about a goal."""
        require_authenticated_user(request)
        if not services.goals.ai:
            return _ai_unavailable_response("Goals")
        result = await services.goals.ai.generate_goal_insight(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"insight": result.value}

    routes.append(goals_ai_insight)

    @rt("/api/goals/ai/milestones")
    async def goals_ai_milestones(request, uid: str):
        """Generate suggested milestones for a goal."""
        require_authenticated_user(request)
        if not services.goals.ai:
            return _ai_unavailable_response("Goals")
        result = await services.goals.ai.generate_milestones(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(goals_ai_milestones)

    @rt("/api/goals/ai/smart-refinement")
    async def goals_ai_smart_refinement(request, uid: str):
        """Suggest SMART refinements for a goal."""
        require_authenticated_user(request)
        if not services.goals.ai:
            return _ai_unavailable_response("Goals")
        result = await services.goals.ai.suggest_smart_refinement(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(goals_ai_smart_refinement)

    # ==========================================================================
    # HABITS AI ROUTES
    # ==========================================================================

    @rt("/api/habits/ai/similar")
    async def habits_ai_similar(request, uid: str, limit: int = 5):
        """Find semantically similar habits."""
        require_authenticated_user(request)
        if not services.habits.ai:
            return _ai_unavailable_response("Habits")
        result = await services.habits.ai.find_similar_habits(uid, limit)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"similar_habits": result.value}

    routes.append(habits_ai_similar)

    @rt("/api/habits/ai/streak-insight")
    async def habits_ai_streak_insight(request, uid: str):
        """Generate AI insight about habit streak patterns."""
        require_authenticated_user(request)
        if not services.habits.ai:
            return _ai_unavailable_response("Habits")
        result = await services.habits.ai.generate_streak_insight(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"insight": result.value}

    routes.append(habits_ai_streak_insight)

    @rt("/api/habits/ai/habit-stack")
    async def habits_ai_habit_stack(request, uid: str):
        """Suggest habit stacking opportunities."""
        require_authenticated_user(request)
        if not services.habits.ai:
            return _ai_unavailable_response("Habits")
        result = await services.habits.ai.suggest_habit_stack(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(habits_ai_habit_stack)

    @rt("/api/habits/ai/optimize-loop")
    async def habits_ai_optimize_loop(request, uid: str):
        """Optimize the cue-routine-reward loop for a habit."""
        require_authenticated_user(request)
        if not services.habits.ai:
            return _ai_unavailable_response("Habits")
        result = await services.habits.ai.optimize_habit_loop(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(habits_ai_optimize_loop)

    # ==========================================================================
    # EVENTS AI ROUTES
    # ==========================================================================

    @rt("/api/events/ai/similar")
    async def events_ai_similar(request, uid: str, limit: int = 5):
        """Find semantically similar events."""
        require_authenticated_user(request)
        if not services.events.ai:
            return _ai_unavailable_response("Events")
        result = await services.events.ai.find_similar_events(uid, limit)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"similar_events": result.value}

    routes.append(events_ai_similar)

    @rt("/api/events/ai/insight")
    async def events_ai_insight(request, uid: str):
        """Generate AI insight about an event."""
        require_authenticated_user(request)
        if not services.events.ai:
            return _ai_unavailable_response("Events")
        result = await services.events.ai.generate_event_insight(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"insight": result.value}

    routes.append(events_ai_insight)

    @rt("/api/events/ai/preparation")
    async def events_ai_preparation(request, uid: str):
        """Generate preparation checklist for an event."""
        require_authenticated_user(request)
        if not services.events.ai:
            return _ai_unavailable_response("Events")
        result = await services.events.ai.generate_preparation_checklist(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(events_ai_preparation)

    @rt("/api/events/ai/reflection")
    async def events_ai_reflection(request, uid: str):
        """Generate reflection prompts for an event."""
        require_authenticated_user(request)
        if not services.events.ai:
            return _ai_unavailable_response("Events")
        result = await services.events.ai.suggest_reflection_prompts(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(events_ai_reflection)

    # ==========================================================================
    # CHOICES AI ROUTES
    # ==========================================================================

    @rt("/api/choices/ai/similar")
    async def choices_ai_similar(request, uid: str, limit: int = 5):
        """Find semantically similar choices."""
        require_authenticated_user(request)
        if not services.choices.ai:
            return _ai_unavailable_response("Choices")
        result = await services.choices.ai.find_similar_choices(uid, limit)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"similar_choices": result.value}

    routes.append(choices_ai_similar)

    @rt("/api/choices/ai/insight")
    async def choices_ai_insight(request, uid: str):
        """Generate AI insight about a choice."""
        require_authenticated_user(request)
        if not services.choices.ai:
            return _ai_unavailable_response("Choices")
        result = await services.choices.ai.generate_choice_insight(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"insight": result.value}

    routes.append(choices_ai_insight)

    @rt("/api/choices/ai/framework")
    async def choices_ai_framework(request, uid: str):
        """Suggest a decision-making framework for a choice."""
        require_authenticated_user(request)
        if not services.choices.ai:
            return _ai_unavailable_response("Choices")
        result = await services.choices.ai.suggest_decision_framework(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(choices_ai_framework)

    @rt("/api/choices/ai/alternatives")
    async def choices_ai_alternatives(request, uid: str):
        """Generate alternative options for a choice."""
        require_authenticated_user(request)
        if not services.choices.ai:
            return _ai_unavailable_response("Choices")
        result = await services.choices.ai.generate_alternatives(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(choices_ai_alternatives)

    # ==========================================================================
    # PRINCIPLES AI ROUTES
    # ==========================================================================

    @rt("/api/principles/ai/similar")
    async def principles_ai_similar(request, uid: str, limit: int = 5):
        """Find semantically similar principles."""
        require_authenticated_user(request)
        if not services.principles.ai:
            return _ai_unavailable_response("Principles")
        result = await services.principles.ai.find_similar_principles(uid, limit)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"similar_principles": result.value}

    routes.append(principles_ai_similar)

    @rt("/api/principles/ai/insight")
    async def principles_ai_insight(request, uid: str):
        """Generate AI insight about a principle."""
        require_authenticated_user(request)
        if not services.principles.ai:
            return _ai_unavailable_response("Principles")
        result = await services.principles.ai.generate_principle_insight(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"insight": result.value}

    routes.append(principles_ai_insight)

    @rt("/api/principles/ai/deepen")
    async def principles_ai_deepen(request, uid: str):
        """Deepen understanding of a principle."""
        require_authenticated_user(request)
        if not services.principles.ai:
            return _ai_unavailable_response("Principles")
        result = await services.principles.ai.deepen_principle(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(principles_ai_deepen)

    @rt("/api/principles/ai/practices")
    async def principles_ai_practices(request, uid: str):
        """Suggest practices to embody a principle."""
        require_authenticated_user(request)
        if not services.principles.ai:
            return _ai_unavailable_response("Principles")
        result = await services.principles.ai.suggest_practices(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(principles_ai_practices)

    # ==========================================================================
    # KNOWLEDGE (KU) AI ROUTES
    # ==========================================================================

    @rt("/api/knowledge/ai/related")
    async def knowledge_ai_related(request, uid: str, limit: int = 5):
        """Find semantically related knowledge units."""
        require_authenticated_user(request)
        if not services.ku.ai:
            return _ai_unavailable_response("Knowledge")
        result = await services.ku.ai.find_related_knowledge(uid, limit)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"related_knowledge": result.value}

    routes.append(knowledge_ai_related)

    @rt("/api/knowledge/ai/search")
    async def knowledge_ai_search(request, query: str, limit: int = 10):
        """Semantic search for knowledge units."""
        require_authenticated_user(request)
        if not services.ku.ai:
            return _ai_unavailable_response("Knowledge")
        result = await services.ku.ai.semantic_search(query, limit)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"results": result.value}

    routes.append(knowledge_ai_search)

    @rt("/api/knowledge/ai/summary")
    async def knowledge_ai_summary(request, uid: str):
        """Generate AI summary of a knowledge unit."""
        require_authenticated_user(request)
        if not services.ku.ai:
            return _ai_unavailable_response("Knowledge")
        result = await services.ku.ai.generate_summary(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"summary": result.value}

    routes.append(knowledge_ai_summary)

    @rt("/api/knowledge/ai/explain")
    async def knowledge_ai_explain(request, uid: str, level: str = "intermediate"):
        """Explain a knowledge unit at a specified level."""
        require_authenticated_user(request)
        if not services.ku.ai:
            return _ai_unavailable_response("Knowledge")
        result = await services.ku.ai.explain_at_level(uid, level)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(knowledge_ai_explain)

    @rt("/api/knowledge/ai/applications")
    async def knowledge_ai_applications(request, uid: str):
        """Suggest practical applications of knowledge."""
        require_authenticated_user(request)
        if not services.ku.ai:
            return _ai_unavailable_response("Knowledge")
        result = await services.ku.ai.suggest_applications(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(knowledge_ai_applications)

    # ==========================================================================
    # LEARNING STEPS (LS) AI ROUTES
    # ==========================================================================

    @rt("/api/learning-steps/ai/similar")
    async def ls_ai_similar(request, uid: str, limit: int = 5):
        """Find semantically similar learning steps."""
        require_authenticated_user(request)
        if not services.learning_steps.ai:
            return _ai_unavailable_response("Learning Steps")
        result = await services.learning_steps.ai.find_similar_steps(uid, limit)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"similar_steps": result.value}

    routes.append(ls_ai_similar)

    @rt("/api/learning-steps/ai/insight")
    async def ls_ai_insight(request, uid: str):
        """Generate AI insight about a learning step."""
        require_authenticated_user(request)
        if not services.learning_steps.ai:
            return _ai_unavailable_response("Learning Steps")
        result = await services.learning_steps.ai.generate_step_insight(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"insight": result.value}

    routes.append(ls_ai_insight)

    @rt("/api/learning-steps/ai/explain")
    async def ls_ai_explain(request, uid: str, level: str = "intermediate"):
        """Explain a learning step at a specified level."""
        require_authenticated_user(request)
        if not services.learning_steps.ai:
            return _ai_unavailable_response("Learning Steps")
        result = await services.learning_steps.ai.explain_step(uid, level)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(ls_ai_explain)

    @rt("/api/learning-steps/ai/practice")
    async def ls_ai_practice(request, uid: str):
        """Suggest practice activities for a learning step."""
        require_authenticated_user(request)
        if not services.learning_steps.ai:
            return _ai_unavailable_response("Learning Steps")
        result = await services.learning_steps.ai.suggest_practice_activities(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(ls_ai_practice)

    # ==========================================================================
    # LEARNING PATHS (LP) AI ROUTES
    # ==========================================================================

    @rt("/api/learning-paths/ai/similar")
    async def lp_ai_similar(request, uid: str, limit: int = 5):
        """Find semantically similar learning paths."""
        require_authenticated_user(request)
        if not services.learning_paths.ai:
            return _ai_unavailable_response("Learning Paths")
        result = await services.learning_paths.ai.find_similar_paths(uid, limit)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"similar_paths": result.value}

    routes.append(lp_ai_similar)

    @rt("/api/learning-paths/ai/insight")
    async def lp_ai_insight(request, uid: str):
        """Generate AI insight about a learning path."""
        require_authenticated_user(request)
        if not services.learning_paths.ai:
            return _ai_unavailable_response("Learning Paths")
        result = await services.learning_paths.ai.generate_path_insight(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"insight": result.value}

    routes.append(lp_ai_insight)

    @rt("/api/learning-paths/ai/overview")
    async def lp_ai_overview(request, uid: str):
        """Generate an engaging overview of a learning path."""
        require_authenticated_user(request)
        if not services.learning_paths.ai:
            return _ai_unavailable_response("Learning Paths")
        result = await services.learning_paths.ai.generate_path_overview(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(lp_ai_overview)

    @rt("/api/learning-paths/ai/strategy")
    async def lp_ai_strategy(request, uid: str):
        """Suggest a completion strategy for a learning path."""
        require_authenticated_user(request)
        if not services.learning_paths.ai:
            return _ai_unavailable_response("Learning Paths")
        result = await services.learning_paths.ai.suggest_completion_strategy(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(lp_ai_strategy)

    # ==========================================================================
    # MAPS OF CONTENT (MOC) AI ROUTES
    # ==========================================================================

    @rt("/api/moc/ai/similar")
    async def moc_ai_similar(request, uid: str, limit: int = 5):
        """Find semantically similar maps of content."""
        require_authenticated_user(request)
        if not services.moc.ai:
            return _ai_unavailable_response("Maps of Content")
        result = await services.moc.ai.find_similar_mocs(uid, limit)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"similar_mocs": result.value}

    routes.append(moc_ai_similar)

    @rt("/api/moc/ai/insight")
    async def moc_ai_insight(request, uid: str):
        """Generate AI insight about a map of content."""
        require_authenticated_user(request)
        if not services.moc.ai:
            return _ai_unavailable_response("Maps of Content")
        result = await services.moc.ai.generate_moc_insight(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return {"insight": result.value}

    routes.append(moc_ai_insight)

    @rt("/api/moc/ai/navigation", methods=["POST"])
    async def moc_ai_navigation(request, uid: str, user_goal: str):
        """Suggest a navigation path through the MOC based on user's goal."""
        require_authenticated_user(request)
        if not services.moc.ai:
            return _ai_unavailable_response("Maps of Content")
        result = await services.moc.ai.suggest_navigation_path(uid, user_goal)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(moc_ai_navigation)

    @rt("/api/moc/ai/gaps")
    async def moc_ai_gaps(request, uid: str):
        """Identify content gaps in a map of content."""
        require_authenticated_user(request)
        if not services.moc.ai:
            return _ai_unavailable_response("Maps of Content")
        result = await services.moc.ai.identify_content_gaps(uid)
        if result.is_error:
            return JSONResponse(status_code=400, content={"error": str(result.error)})
        return result.value

    routes.append(moc_ai_gaps)

    # ==========================================================================
    # AI STATUS ENDPOINT
    # ==========================================================================

    @rt("/api/ai/status")
    async def ai_status(request):
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
                "knowledge": services.ku.ai is not None,
                "learning_steps": services.learning_steps.ai is not None,
                "learning_paths": services.learning_paths.ai is not None,
                "moc": services.moc.ai is not None,
            }
        }

    routes.append(ai_status)

    logger.info(f"✅ AI routes registered ({len(routes)} endpoints)")
    logger.info("   - Pattern: Check .ai availability, return 503 if unavailable")

    return routes


__all__ = ["create_ai_routes"]
