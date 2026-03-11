"""Activities UI Routes — Landing page + domain views with sidebar.

Routes:
- GET /activities — Landing page with domain card grid (no sidebar)
- GET /activities/{domain} — Domain view with Activity sidebar
- GET /api/activities/{slug}/preview — HTMX fragment for domain card item lists
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, Request

if TYPE_CHECKING:
    from services_bootstrap import Services

from adapters.inbound.auth import require_authenticated_user
from core.models.enums import Priority
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.activities.landing import ActivitiesLandingView, render_activity_card_preview
from ui.activities.layout import create_activities_page
from ui.layouts.base_page import BasePage
from ui.profile.activity_views import (
    ChoicesDomainView,
    EventsDomainView,
    GoalsDomainView,
    HabitsDomainView,
    PrinciplesDomainView,
    TasksDomainView,
)

logger = get_logger("skuel.routes.activities")

_PREVIEW_PRIORITY_ORDER = {
    Priority.CRITICAL: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}

_PREVIEW_VALID_SLUGS = frozenset({"tasks", "goals", "habits", "events", "choices", "principles"})

_TERMINAL_STATUSES = frozenset(["completed", "failed", "cancelled", "archived"])

_DOMAIN_VIEWS = {
    "tasks": TasksDomainView,
    "events": EventsDomainView,
    "goals": GoalsDomainView,
    "habits": HabitsDomainView,
    "principles": PrinciplesDomainView,
    "choices": ChoicesDomainView,
}

_VALID_DOMAINS = frozenset(_DOMAIN_VIEWS.keys())


def _preview_priority_sort_key(item: Any) -> int:
    """Sort key for domain card preview items by priority (CRITICAL first)."""
    raw = getattr(item, "priority", Priority.LOW)
    if not isinstance(raw, Priority):
        try:
            raw = Priority(str(raw).lower())
        except ValueError:
            raw = Priority.LOW
    return _PREVIEW_PRIORITY_ORDER.get(raw, 4)


def setup_activities_routes(rt: Any, services: "Services") -> None:
    """Register /activities routes.

    Args:
        rt: FastHTML route decorator
        services: Services container
    """
    if services.user_service is None:
        raise RuntimeError("UserService is required for activities routes")
    user_service = services.user_service

    @rt("/activities")
    async def activities_landing(request: Request) -> Any:
        """Activities landing page — card grid, no sidebar."""
        user_uid = require_authenticated_user(request)

        context_result = await user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            from fasthtml.common import H1, P

            return await BasePage(
                Div(
                    H1("Error", cls="text-3xl font-bold text-error mb-4"),
                    P("Failed to load user context.", cls="text-lg text-base-content/70"),
                    cls="flex flex-col items-center justify-center min-h-[400px] p-8",
                ),
                title="Activities",
                request=request,
                active_page="activities",
            )

        content = ActivitiesLandingView(context_result.value)
        return await BasePage(
            content,
            title="Activities",
            request=request,
            active_page="activities",
        )

    @rt("/activities/{domain}")
    async def activities_domain(request: Request, domain: str) -> Any:
        """Individual activity domain view with sidebar."""
        if domain not in _VALID_DOMAINS:
            from starlette.responses import RedirectResponse

            return RedirectResponse("/activities", status_code=302)

        user_uid = require_authenticated_user(request)

        context_result = await user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            from fasthtml.common import H1, P

            return await BasePage(
                Div(
                    H1("Error", cls="text-3xl font-bold text-error mb-4"),
                    P("Failed to load user context.", cls="text-lg text-base-content/70"),
                    cls="flex flex-col items-center justify-center min-h-[400px] p-8",
                ),
                title="Activities",
                request=request,
                active_page="activities",
            )

        context = context_result.value
        focus_uid = request.query_params.get("focus")
        view_fn = _DOMAIN_VIEWS[domain]
        domain_content = view_fn(context, focus_uid)

        return await create_activities_page(
            content=domain_content,
            active_domain=domain,
            request=request,
            title=f"{domain.title()} - Activities",
        )

    @rt("/api/activities/{slug}/preview")
    async def activity_card_preview(request: Request, slug: str) -> Any:
        """HTMX fragment: top 5 active items for a domain card, sorted by priority."""
        if slug not in _PREVIEW_VALID_SLUGS:
            from fasthtml.common import P

            return P("Unknown domain", cls="text-error text-sm")

        user_uid = require_authenticated_user(request)

        service_map = {
            "tasks": ("tasks", "get_user_tasks"),
            "goals": ("goals", "get_user_goals"),
            "habits": ("habits", "get_user_habits"),
            "events": ("events", "get_user_events"),
            "choices": ("choices", "get_user_choices"),
            "principles": ("principles", "get_user_principles"),
        }

        service_attr, method_name = service_map[slug]
        service = getattr(services, service_attr, None)
        if service is None:
            from fasthtml.common import P

            return P("Service not available", cls="text-sm text-base-content/50 py-2")

        method = getattr(service, method_name)
        result: Result[list[Any]] = await method(user_uid)

        if result.is_error:
            from fasthtml.common import P

            logger.warning(
                "Failed to load activity card preview",
                extra={"slug": slug, "user_uid": user_uid, "error": str(result.error)},
            )
            return P("Unable to load items", cls="text-sm text-base-content/50 py-2")

        active_items = [
            item
            for item in result.value
            if str(getattr(item, "status", "active")).lower() not in _TERMINAL_STATUSES
        ]

        sorted_items = sorted(active_items, key=_preview_priority_sort_key)
        preview_items = sorted_items[:5]

        return render_activity_card_preview(preview_items, slug)

    logger.info("Activities routes registered (/activities, /activities/{domain}, /api/activities/{slug}/preview)")
