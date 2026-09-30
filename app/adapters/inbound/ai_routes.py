"""
AI Routes - Optional AI-Powered Features (Config-Driven)
=========================================================

The one HTTP door of the AI tier (ADR-024: Two-Tier Intelligence Design; ADR-043:
tier toggle). AI services are OPTIONAL - the app functions fully without them;
when a domain's ``.ai`` is unset its routes answer 503 with an explicit message.

Pattern: each route is declared as an AIRouteSpec; signature template factories
generate the ``POST``-only, CSRF-protected handlers in a registration loop.
``_ai_route`` runs the gates (auth, availability, tier, ownership, quota), calls
the AI method and answers through the boundary's ``Result`` → HTTP mapping.

Every route spends LLM or embeddings money, so it is a mutation in cost if not
in state: ``POST`` only, with ``@csrf_protected``. ``GET`` and ``HEAD`` answer
405 and spend nothing. ``/api/ai/status`` is a read and stays ``GET``.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse, Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import result_to_response
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from adapters.inbound.rate_limit import LLM_QUOTA_MESSAGE, llm_quota_allowed
from adapters.inbound.result_helpers import require_found
from adapters.inbound.route_factories.route_helpers import verify_entity_ownership
from core.models.enums import ContentScope
from core.services.base_ai_service import BaseAIService
from core.services.choices.choices_ai_service import ChoicesAIService
from core.services.events.events_ai_service import EventsAIService
from core.services.goals.goals_ai_service import GoalsAIService
from core.services.habits.habits_ai_service import HabitsAIService
from core.services.intelligence_tier_service import get_user_intelligence_tier
from core.services.lp.lp_ai_service import LpAIService
from core.services.principles.principles_ai_service import PrinciplesAIService
from core.services.ps.ps_ai_service import PsAIService
from core.services.tasks.tasks_ai_service import TasksAIService
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

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
    domain_label: str  # human label for error messages: "Tasks", "Path Steps"
    url_domain: str  # URL segment: "tasks", "path-steps"
    action: str  # URL action segment: "similar", "insight"
    method_name: str  # AI service method: "find_similar_tasks"
    signature: str  # "uid" | "uid_limit" | "uid_level"
    func_name: str  # unique function name for FastHTML
    wrap_key: str | None = None  # if set, wrap result as {wrap_key: value}
    default_limit: int = 5  # default for the uid_limit signature
    # Authorization contract for this route's entity. USER_OWNED (the safe default)
    # makes _ai_route verify the caller owns the entity uid before invoking the AI
    # service; SHARED (public-read curriculum: ps/lp) skips the ownership gate. The
    # default is fail-closed: a new route is owner-gated until explicitly marked SHARED.
    scope: ContentScope = ContentScope.USER_OWNED


# The class behind each ``domain_attr``'s ``.ai`` slot. ``create_ai_routes`` resolves
# every spec's ``method_name`` against it at registration, so a spec that names
# nothing fails at boot in both tiers — never as a 500 after a quota unit is spent.
AI_SERVICE_CLASSES: dict[str, type[BaseAIService[Any, Any]]] = {  # boundary: heterogeneous
    "tasks": TasksAIService,
    "goals": GoalsAIService,
    "habits": HabitsAIService,
    "events": EventsAIService,
    "choices": ChoicesAIService,
    "principles": PrinciplesAIService,
    "ps": PsAIService,
    "lp": LpAIService,
}

# fmt: off
AI_ROUTE_SPECS: list[AIRouteSpec] = [
    # Tasks (4)
    AIRouteSpec("tasks", "Tasks", "tasks", "similar", "find_similar_tasks", "uid_limit", "tasks_ai_similar", "similar_tasks"),
    AIRouteSpec("tasks", "Tasks", "tasks", "insight", "generate_task_insight", "uid", "tasks_ai_insight", "insight"),
    AIRouteSpec("tasks", "Tasks", "tasks", "breakdown", "generate_task_breakdown", "uid", "tasks_ai_breakdown", "subtasks"),
    AIRouteSpec("tasks", "Tasks", "tasks", "priority-suggestion", "suggest_priority", "uid", "tasks_ai_priority_suggestion"),
    # Goals (5)
    AIRouteSpec("goals", "Goals", "goals", "similar", "find_similar_goals", "uid_limit", "goals_ai_similar", "similar_goals"),
    AIRouteSpec("goals", "Goals", "goals", "insight", "generate_goal_insight", "uid", "goals_ai_insight", "insight"),
    AIRouteSpec("goals", "Goals", "goals", "milestones", "generate_milestones", "uid", "goals_ai_milestones", "milestones"),
    AIRouteSpec("goals", "Goals", "goals", "smart-refinement", "suggest_smart_refinement", "uid", "goals_ai_smart_refinement"),
    AIRouteSpec("goals", "Goals", "goals", "strategy", "suggest_achievement_strategy", "uid", "goals_ai_strategy"),
    # Habits (5)
    AIRouteSpec("habits", "Habits", "habits", "similar", "find_similar_habits", "uid_limit", "habits_ai_similar", "similar_habits"),
    AIRouteSpec("habits", "Habits", "habits", "streak-insight", "generate_streak_insight", "uid", "habits_ai_streak_insight", "insight"),
    AIRouteSpec("habits", "Habits", "habits", "habit-stack", "suggest_habit_stack", "uid", "habits_ai_habit_stack"),
    AIRouteSpec("habits", "Habits", "habits", "optimize-loop", "optimize_habit_loop", "uid", "habits_ai_optimize_loop"),
    AIRouteSpec("habits", "Habits", "habits", "identity", "suggest_identity_reinforcement", "uid", "habits_ai_identity"),
    # Events (4)
    AIRouteSpec("events", "Events", "events", "similar", "find_similar_events", "uid_limit", "events_ai_similar", "similar_events"),
    AIRouteSpec("events", "Events", "events", "insight", "generate_event_insight", "uid", "events_ai_insight", "insight"),
    AIRouteSpec("events", "Events", "events", "preparation", "generate_preparation_checklist", "uid", "events_ai_preparation", "checklist"),
    AIRouteSpec("events", "Events", "events", "reflection", "suggest_reflection_prompts", "uid", "events_ai_reflection", "prompts"),
    # Choices (4)
    AIRouteSpec("choices", "Choices", "choices", "similar", "find_similar_choices", "uid_limit", "choices_ai_similar", "similar_choices"),
    AIRouteSpec("choices", "Choices", "choices", "insight", "generate_choice_insight", "uid", "choices_ai_insight", "insight"),
    AIRouteSpec("choices", "Choices", "choices", "framework", "suggest_decision_framework", "uid", "choices_ai_framework"),
    AIRouteSpec("choices", "Choices", "choices", "alternatives", "generate_alternatives", "uid", "choices_ai_alternatives", "alternatives"),
    # Principles (4)
    AIRouteSpec("principles", "Principles", "principles", "similar", "find_similar_principles", "uid_limit", "principles_ai_similar", "similar_principles"),
    AIRouteSpec("principles", "Principles", "principles", "insight", "generate_principle_insight", "uid", "principles_ai_insight", "insight"),
    AIRouteSpec("principles", "Principles", "principles", "deepen", "deepen_principle", "uid", "principles_ai_deepen"),
    AIRouteSpec("principles", "Principles", "principles", "practices", "suggest_practices", "uid", "principles_ai_practices", "practices"),
    # Path Steps (4) — SHARED public-read curriculum, no ownership gate
    AIRouteSpec("ps", "Path Steps", "path-steps", "similar", "find_similar_steps", "uid_limit", "ps_ai_similar", "similar_steps", scope=ContentScope.SHARED),
    AIRouteSpec("ps", "Path Steps", "path-steps", "insight", "generate_step_insight", "uid", "ps_ai_insight", "insight", scope=ContentScope.SHARED),
    AIRouteSpec("ps", "Path Steps", "path-steps", "explain", "explain_step", "uid_level", "ps_ai_explain", "explanation", scope=ContentScope.SHARED),
    AIRouteSpec("ps", "Path Steps", "path-steps", "practice", "suggest_practice_activities", "uid", "ps_ai_practice", "activities", scope=ContentScope.SHARED),
    # Learning Paths (4) — SHARED public-read curriculum, no ownership gate
    AIRouteSpec("lp", "Learning Paths", "learning-paths", "similar", "find_similar_paths", "uid_limit", "lp_ai_similar", "similar_paths", scope=ContentScope.SHARED),
    AIRouteSpec("lp", "Learning Paths", "learning-paths", "insight", "generate_path_insight", "uid", "lp_ai_insight", "insight", scope=ContentScope.SHARED),
    AIRouteSpec("lp", "Learning Paths", "learning-paths", "overview", "generate_path_overview", "uid", "lp_ai_overview", scope=ContentScope.SHARED),
    AIRouteSpec("lp", "Learning Paths", "learning-paths", "strategy", "suggest_completion_strategy", "uid", "lp_ai_strategy", scope=ContentScope.SHARED),
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
# Shared handler
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
    request: Request,
    services: Services,
    domain_attr: str,
    domain_label: str,
    method_name: str,
    args: tuple[Any, ...],
    scope: ContentScope = ContentScope.USER_OWNED,
    *,
    entity_uid: str,
    wrap_key: str | None = None,
) -> Response:
    """Shared handler for all AI routes.

    Handles auth, AI availability check (system-level 503 guard, ADR-043),
    per-user intelligence tier gate (ADR-043: REGISTERED users get CORE →
    403 if system is FULL), ownership verification (USER_OWNED scope), the
    per-user daily LLM quota, the method call and the response.

    The guard order is intentional: system-tier 503 fires first (cheapest),
    per-user 403 second (one DB fetch), ownership 404 third (one DB fetch),
    quota last — a request denied by any earlier gate never burns a quota
    unit, and a unit is only recorded when the AI call actually runs.

    The AI method's ``Result`` is answered through ``result_to_response``: a
    success is JSON whatever the value's type (a dict, a list, a string), a
    failure carries the boundary's status for its category and the client-safe
    error dict — never the internal error text.

    Args:
        request: Starlette request
        services: Service container
        domain_attr: Attribute name on services (e.g. "tasks", "ps")
        domain_label: Human-readable domain name for error messages
        method_name: AI service method to call
        args: Positional args to pass to the method
        scope: Authorization contract for the entity. USER_OWNED triggers the
            ownership gate; SHARED (public-read curriculum) skips it.
        entity_uid: The entity UID the route operates on — every signature carries
            one, so the USER_OWNED ownership gate always has an entity to check
        wrap_key: If set, the body is {wrap_key: value}; otherwise the value itself
    """
    user_uid = require_authenticated_user(request)
    facade = getattr(services, domain_attr)
    if not facade.ai:
        return _ai_unavailable_response(domain_label)
    # Per-user tier gate (ADR-043): within a FULL-tier system, REGISTERED users
    # are capped at CORE and may not consume AI routes.
    if services.intelligence_tier is not None:
        user_service = services.user
        if user_service is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Could not verify user access tier"},
            )
        user = require_found(await user_service.get_user(user_uid), "User", user_uid)
        if user.is_error:
            return JSONResponse(
                status_code=503,
                content={"error": "Could not verify user access tier"},
            )
        effective_tier = get_user_intelligence_tier(services.intelligence_tier, user.value.role)
        if not effective_tier.ai_enabled:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "AI features require a paid subscription",
                    "message": "Upgrade to MEMBER to unlock AI features",
                    "tier_required": "full",
                },
            )
    # Ownership gate: never expose one user's private entity (or spend LLM budget on
    # it) through an AI route. 404 (not 403) so we don't confirm the uid's existence.
    if scope == ContentScope.USER_OWNED:
        ownership_error = await verify_entity_ownership(facade, entity_uid, user_uid, domain_label)
        if ownership_error:
            return JSONResponse(
                status_code=404,
                content={"error": f"{domain_label} entity not found"},
            )
    # Per-user daily LLM quota: every call below spends LLM/embeddings money.
    # Check-and-record here, immediately before the spend. 403 (not 429) to
    # match the Result error system's FORBIDDEN category used by the other
    # quota chokepoints — the message, not the status, distinguishes it from
    # the subscription denial above.
    if not llm_quota_allowed(user_uid):
        return JSONResponse(
            status_code=403,
            content={"error": "Daily AI quota exceeded", "message": LLM_QUOTA_MESSAGE},
        )
    result: Result[Any] = await getattr(facade.ai, method_name)(*args)  # boundary: per-spec T
    if result.is_ok and wrap_key:
        result = Result.ok({wrap_key: result.value})
    return result_to_response(result)


# ---------------------------------------------------------------------------
# Signature template factories — one per parameter pattern
# ---------------------------------------------------------------------------


def _register(
    rt: RouteDecorator, path: str, spec: AIRouteSpec, handler: Callable[..., Awaitable[Response]]
) -> None:
    """Register ``handler`` as the spec's ``POST``-only, CSRF-protected route.

    The function name is set before registration because FastHTML names the
    route after the function it is handed.
    """
    handler.__name__ = spec.func_name
    handler.__qualname__ = spec.func_name
    rt(path, methods=["POST"])(csrf_protected(handler))


def _make_uid_route(rt: RouteDecorator, path: str, services: Services, spec: AIRouteSpec) -> None:
    """Generate route with (request, uid: str) signature."""

    async def handler(request: Request, uid: str) -> Response:
        return await _ai_route(
            request,
            services,
            spec.domain_attr,
            spec.domain_label,
            spec.method_name,
            (uid,),
            scope=spec.scope,
            entity_uid=uid,
            wrap_key=spec.wrap_key,
        )

    _register(rt, path, spec, handler)


def _make_uid_limit_route(
    rt: RouteDecorator, path: str, services: Services, spec: AIRouteSpec
) -> None:
    """Generate route with (request, uid: str, limit: int = N) signature."""
    default_limit = spec.default_limit

    async def handler(request: Request, uid: str, limit: int = default_limit) -> Response:
        return await _ai_route(
            request,
            services,
            spec.domain_attr,
            spec.domain_label,
            spec.method_name,
            (uid, limit),
            scope=spec.scope,
            entity_uid=uid,
            wrap_key=spec.wrap_key,
        )

    _register(rt, path, spec, handler)


def _make_uid_level_route(
    rt: RouteDecorator, path: str, services: Services, spec: AIRouteSpec
) -> None:
    """Generate route with (request, uid: str, level: str = 'intermediate') signature."""

    async def handler(request: Request, uid: str, level: str = "intermediate") -> Response:
        return await _ai_route(
            request,
            services,
            spec.domain_attr,
            spec.domain_label,
            spec.method_name,
            (uid, level),
            scope=spec.scope,
            entity_uid=uid,
            wrap_key=spec.wrap_key,
        )

    _register(rt, path, spec, handler)


_SIGNATURE_FACTORIES = {
    "uid": _make_uid_route,
    "uid_limit": _make_uid_limit_route,
    "uid_level": _make_uid_level_route,
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def unresolved_ai_route_specs(specs: list[AIRouteSpec]) -> list[str]:
    """Name every spec that cannot be registered.

    A spec is unresolved when its ``domain_attr`` has no AI class, its
    ``method_name`` is not a method of that class, or its ``signature`` has no
    factory. Empty for a registrable list; ``create_ai_routes`` refuses any other.
    """
    unresolved: list[str] = []
    for spec in specs:
        route = f"/api/{spec.url_domain}/ai/{spec.action}"
        ai_class = AI_SERVICE_CLASSES.get(spec.domain_attr)
        if ai_class is None:
            unresolved.append(f"{route}: no AI class for domain {spec.domain_attr!r}")
        elif not callable(getattr(ai_class, spec.method_name, None)):
            unresolved.append(f"{route}: {ai_class.__name__} has no method {spec.method_name!r}")
        if spec.signature not in _SIGNATURE_FACTORIES:
            unresolved.append(f"{route}: unknown signature {spec.signature!r}")
    return unresolved


def create_ai_routes(app: FastHTMLApp, rt: RouteDecorator, services: Services) -> None:
    """Create routes for AI-powered domain features.

    Every spec's ``method_name`` must resolve on its domain's AI class before any
    route is registered; an unresolved spec raises here, at boot, in both tiers.
    All routes check if the domain's .ai service is available and answer 503
    Service Unavailable if AI is not configured.
    """
    unresolved = unresolved_ai_route_specs(AI_ROUTE_SPECS)
    if unresolved:
        raise ValueError(f"Unregistrable AI route specs: {unresolved}")

    for spec in AI_ROUTE_SPECS:
        path = f"/api/{spec.url_domain}/ai/{spec.action}"
        _SIGNATURE_FACTORIES[spec.signature](rt, path, services, spec)

    # AI status endpoint — a read that spends nothing, so it stays GET
    @rt("/api/ai/status", methods=["GET"])
    def ai_status(request: Request) -> dict[str, Any]:
        """Check which AI services are available."""
        require_authenticated_user(request)
        return {
            "ai_available": {
                status_key: getattr(services, domain_attr).ai is not None
                for domain_attr, status_key in _AI_STATUS_DOMAINS.items()
            }
        }

    logger.info(f"AI routes registered ({len(AI_ROUTE_SPECS) + 1} endpoints)")


__all__ = [
    "AI_ROUTE_SPECS",
    "AI_SERVICE_CLASSES",
    "AIRouteSpec",
    "create_ai_routes",
    "unresolved_ai_route_specs",
]
