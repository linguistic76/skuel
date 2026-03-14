"""Activities UI Routes — Redirects to /profile + HTMX preview endpoints.

The activities overview is now part of the /profile page.

Routes:
- GET /activities — 301 redirect to /profile
- GET /activities/{domain} — 302 redirect to /{domain} (preserves bookmarks)
- GET /api/activities/{slug}/preview — HTMX fragment for domain card item lists
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request
from starlette.responses import RedirectResponse

if TYPE_CHECKING:
    from services_bootstrap import Services

from adapters.inbound.auth import require_authenticated_user
from core.models.enums import Priority
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.activities.landing import render_activity_card_preview

logger = get_logger("skuel.routes.activities")

_PREVIEW_PRIORITY_ORDER = {
    Priority.CRITICAL: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}

_PREVIEW_VALID_SLUGS = frozenset({"tasks", "goals", "habits", "events", "choices", "principles"})

_TERMINAL_STATUSES = frozenset(["completed", "failed", "cancelled", "archived"])

_VALID_ACTIVITY_DOMAINS = frozenset({"tasks", "events", "goals", "habits", "principles", "choices"})


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

    @rt("/activities")
    async def activities_landing(request: Request) -> Any:
        """Redirect to /profile — activities overview lives there now."""
        return RedirectResponse("/profile", status_code=301)

    @rt("/activities/{domain}")
    async def activities_domain(request: Request, domain: str) -> Any:
        """Redirect /activities/{domain} to /{domain} — preserves bookmarks."""
        if domain in _VALID_ACTIVITY_DOMAINS:
            return RedirectResponse(f"/{domain}", status_code=302)
        return RedirectResponse("/profile", status_code=302)

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

            return P("Service not available", cls="text-sm text-muted-foreground py-2")

        method = getattr(service, method_name)
        result: Result[list[Any]] = await method(user_uid)

        if result.is_error:
            from fasthtml.common import P

            logger.warning(
                "Failed to load activity card preview",
                extra={"slug": slug, "user_uid": user_uid, "error": str(result.error)},
            )
            return P("Unable to load items", cls="text-sm text-muted-foreground py-2")

        active_items = [
            item
            for item in result.value
            if str(getattr(item, "status", "active")).lower() not in _TERMINAL_STATUSES
        ]

        sorted_items = sorted(active_items, key=_preview_priority_sort_key)
        preview_items = sorted_items[:5]

        return render_activity_card_preview(preview_items, slug)

    logger.info(
        "Activities routes registered (/activities -> /profile redirect, /api/activities/{slug}/preview)"
    )
