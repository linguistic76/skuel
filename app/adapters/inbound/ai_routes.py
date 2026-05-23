"""
AI Routes - Optional AI-Powered Features (Config-Driven)
=========================================================

Routes for AI-powered domain features (ADR-030: Two-Tier Intelligence Design).

AI services are OPTIONAL - the app functions fully without them.
When AI is unavailable, routes return 503 Service Unavailable with explicit message.

Pattern: Each route is declared as an AIRouteSpec; signature template factories
generate the @rt()-decorated handlers in a registration loop. _ai_route handles
auth, availability check, error propagation, and response wrapping.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from services_bootstrap import Services

logger = get_logger("skuel.routes.ai")


# ---------------------------------------------------------------------------
# Route specification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AIRouteSpec:
    """Specification for a single AI route endpoint."""

    domain_attr: str  # services attribute: "tasks", "ps", "lp"
    domain_label: str  # human label for error messages: "Tasks", "Knowledge"
    url_domain: str  # URL segment: "tasks", "knowledge", "path-steps"
    action: str  # URL action segment: "similar", "insight"
    method_name: str  # AI service method: "find_similar_tasks"
    signature: str  # "uid" | "uid_limit" | "query_limit" | "uid_level"
    func_name: str  # unique function name for FastHTML
    wrap_key: str | None = None  # if set, wrap result as {wrap_key: value}
    default_limit: int = 5  # default for uid_limit/query_limit signatures


# fmt: off
AI_ROUTE_SPECS: list[AIRouteSpec] = [
    # Tasks (3)
    AIRouteSpec("tasks", "Tasks", "tasks", "similar", "find_similar_tasks", "uid_limit", "tasks_ai_similar", "similar_tasks"),
    AIRouteSpec("tasks", "Tasks", "tasks", "insight", "generate_task_insight", "uid", "tasks_ai_insight", "insight"),
    AIRouteSpec("tasks", "Tasks", "tasks", "knowledge-generation", "identify_knowledge_generation", "uid", "tasks_ai_knowledge_generation"),
    # Goals (4)
    AIRouteSpec("goals", "Goals", "goals", "similar", "find_similar_goals", "uid_limit", "goals_ai_similar", "similar_goals"),
    AIRouteSpec("goals", "Goals", "goals", "insight", "generate_goal_insight", "uid", "goals_ai_insight", "insight"),
    AIRouteSpec("goals", "Goals", "goals", "milestones", "generate_milestones", "uid", "goals_ai_milestones"),
    AIRouteSpec("goals", "Goals", "goals", "smart-refinement", "suggest_smart_refinement", "uid", "goals_ai_smart_refinement"),
    # Habits (4)
    AIRouteSpec("habits", "Habits", "habits", "similar", "find_similar_habits", "uid_limit", "habits_ai_similar", "similar_habits"),
    AIRouteSpec("habits", "Habits", "habits", "streak-insight", "generate_streak_insight", "uid", "habits_ai_streak_insight", "insight"),
    AIRouteSpec("habits", "Habits", "habits", "habit-stack", "suggest_habit_stack", "uid", "habits_ai_habit_stack"),
    AIRouteSpec("habits", "Habits", "habits", "optimize-loop", "optimize_habit_loop", "uid", "habits_ai_optimize_loop"),
    # Events (4)
    AIRouteSpec("events", "Events", "events", "similar", "find_similar_events", "uid_limit", "events_ai_similar", "similar_events"),
    AIRouteSpec("events", "Events", "events", "insight", "generate_event_insight", "uid", "events_ai_insight", "insight"),
    AIRouteSpec("events", "Events", "events", "preparation", "generate_preparation_checklist", "uid", "events_ai_preparation"),
    AIRouteSpec("events", "Events", "events", "reflection", "suggest_reflection_prompts", "uid", "events_ai_reflection"),
    # Choices (4)
    AIRouteSpec("choices", "Choices", "choices", "similar", "find_similar_choices", "uid_limit", "choices_ai_similar", "similar_choices"),
    AIRouteSpec("choices", "Choices", "choices", "insight", "generate_choice_insight", "uid", "choices_ai_insight", "insight"),
    AIRouteSpec("choices", "Choices", "choices", "framework", "suggest_decision_framework", "uid", "choices_ai_framework"),
    AIRouteSpec("choices", "Choices", "choices", "alternatives", "generate_alternatives", "uid", "choices_ai_alternatives"),
    # Principles (4)
    AIRouteSpec("principles", "Principles", "principles", "similar", "find_similar_principles", "uid_limit", "principles_ai_similar", "similar_principles"),
    AIRouteSpec("principles", "Principles", "principles", "insight", "generate_principle_insight", "uid", "principles_ai_insight", "insight"),
    AIRouteSpec("principles", "Principles", "principles", "deepen", "deepen_principle", "uid", "principles_ai_deepen"),
    AIRouteSpec("principles", "Principles", "principles", "practices", "suggest_practices", "uid", "principles_ai_practices"),
    # Knowledge / PathStep (5)
    AIRouteSpec("ps", "Knowledge", "knowledge", "related", "find_related_steps", "uid_limit", "knowledge_ai_related", "related_knowledge"),
    AIRouteSpec("ps", "Knowledge", "knowledge", "search", "semantic_search", "query_limit", "knowledge_ai_search", "results", default_limit=10),
    AIRouteSpec("ps", "Knowledge", "knowledge", "summary", "generate_summary", "uid", "knowledge_ai_summary", "summary"),
    AIRouteSpec("ps", "Knowledge", "knowledge", "explain", "explain_at_level", "uid_level", "knowledge_ai_explain"),
    AIRouteSpec("ps", "Knowledge", "knowledge", "applications", "suggest_applications", "uid", "knowledge_ai_applications"),
    # Learning Steps (4)
    AIRouteSpec("ps", "Path Steps", "path-steps", "similar", "find_similar_steps", "uid_limit", "ps_ai_similar", "similar_steps"),
    AIRouteSpec("ps", "Path Steps", "path-steps", "insight", "generate_step_insight", "uid", "ps_ai_insight", "insight"),
    AIRouteSpec("ps", "Path Steps", "path-steps", "explain", "explain_step", "uid_level", "ps_ai_explain"),
    AIRouteSpec("ps", "Path Steps", "path-steps", "practice", "suggest_practice_activities", "uid", "ps_ai_practice"),
    # Learning Paths (4)
    AIRouteSpec("lp", "Learning Paths", "learning-paths", "similar", "find_similar_paths", "uid_limit", "lp_ai_similar", "similar_paths"),
    AIRouteSpec("lp", "Learning Paths", "learning-paths", "insight", "generate_path_insight", "uid", "lp_ai_insight", "insight"),
    AIRouteSpec("lp", "Learning Paths", "learning-paths", "overview", "generate_path_overview", "uid", "lp_ai_overview"),
    AIRouteSpec("lp", "Learning Paths", "learning-paths", "strategy", "suggest_completion_strategy", "uid", "lp_ai_strategy"),
]
# fmt: on

# Domain -> status key for /api/ai/status endpoint
_AI_STATUS_DOMAINS: dict[str, str] = {
    "tasks": "tasks",
    "goals": "goals",
    "habits": "habits",
    "events": "events",
    "choices": "choices",
    "principles": "principles",
    "ps": "path_steps",
    "lp": "learning_paths",
}


# ---------------------------------------------------------------------------
# Shared handler (unchanged)
# ---------------------------------------------------------------------------


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
        domain_attr: Attribute name on services (e.g. "tasks", "ps")
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


# ---------------------------------------------------------------------------
# Signature template factories — one per parameter pattern
# ---------------------------------------------------------------------------


def _make_uid_route(rt: Any, path: str, services: Any, spec: AIRouteSpec) -> None:
    """Generate route with (request, uid: str) signature."""

    @rt(path)
    async def handler(request: Request, uid: str) -> Any:
        return await _ai_route(
            request,
            services,
            spec.domain_attr,
            spec.domain_label,
            spec.method_name,
            (uid,),
            wrap_key=spec.wrap_key,
        )

    handler.__name__ = spec.func_name
    handler.__qualname__ = spec.func_name


def _make_uid_limit_route(rt: Any, path: str, services: Any, spec: AIRouteSpec) -> None:
    """Generate route with (request, uid: str, limit: int = N) signature."""
    default_limit = spec.default_limit

    @rt(path)
    async def handler(request: Request, uid: str, limit: int = default_limit) -> Any:
        return await _ai_route(
            request,
            services,
            spec.domain_attr,
            spec.domain_label,
            spec.method_name,
            (uid, limit),
            wrap_key=spec.wrap_key,
        )

    handler.__name__ = spec.func_name
    handler.__qualname__ = spec.func_name


def _make_query_limit_route(rt: Any, path: str, services: Any, spec: AIRouteSpec) -> None:
    """Generate route with (request, query: str, limit: int = N) signature."""
    default_limit = spec.default_limit

    @rt(path)
    async def handler(request: Request, query: str, limit: int = default_limit) -> Any:
        return await _ai_route(
            request,
            services,
            spec.domain_attr,
            spec.domain_label,
            spec.method_name,
            (query, limit),
            wrap_key=spec.wrap_key,
        )

    handler.__name__ = spec.func_name
    handler.__qualname__ = spec.func_name


def _make_uid_level_route(rt: Any, path: str, services: Any, spec: AIRouteSpec) -> None:
    """Generate route with (request, uid: str, level: str = 'intermediate') signature."""

    @rt(path)
    async def handler(request: Request, uid: str, level: str = "intermediate") -> Any:
        return await _ai_route(
            request,
            services,
            spec.domain_attr,
            spec.domain_label,
            spec.method_name,
            (uid, level),
            wrap_key=spec.wrap_key,
        )

    handler.__name__ = spec.func_name
    handler.__qualname__ = spec.func_name


_SIGNATURE_FACTORIES = {
    "uid": _make_uid_route,
    "uid_limit": _make_uid_limit_route,
    "query_limit": _make_query_limit_route,
    "uid_level": _make_uid_level_route,
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def create_ai_routes(app: FastHTMLApp, rt: RouteDecorator, services: "Services | None") -> None:
    """Create routes for AI-powered domain features.

    All routes check if the domain's .ai service is available.
    Returns 503 Service Unavailable if AI is not configured.
    """
    for spec in AI_ROUTE_SPECS:
        path = f"/api/{spec.url_domain}/ai/{spec.action}"
        _SIGNATURE_FACTORIES[spec.signature](rt, path, services, spec)

    # AI status endpoint — derived from _AI_STATUS_DOMAINS
    @rt("/api/ai/status")
    async def ai_status(request: Request) -> dict[str, Any]:
        """Check which AI services are available."""
        require_authenticated_user(request)
        return {
            "ai_available": {
                status_key: getattr(services, domain_attr).ai is not None
                for domain_attr, status_key in _AI_STATUS_DOMAINS.items()
            }
        }

    logger.info(f"AI routes registered ({len(AI_ROUTE_SPECS) + 1} endpoints)")


__all__ = ["create_ai_routes"]
