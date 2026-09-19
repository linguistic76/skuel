"""Tasks+ sidebar badges — the ``GET /api/sidebar/badges`` HTMX endpoint.

The Tasks+ sidebar (``SidebarPage(badges=True)``) requests this once its
desktop ``<nav>`` is on screen and OOB-swaps one count + health badge per
Activity Domain row. The whole user context is built for it, so only the
Tasks+ sidebar asks and nothing is emitted that no row would swap in.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, Span

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.activities.badges import CountBadge, HealthIndicator
from ui.activities.domain_stats_config import DOMAIN_STATS_CONFIG
from ui.activities.nav import ACTIVITY_SIDEBAR_ITEMS

if TYPE_CHECKING:
    from services_bootstrap import Services

logger = get_logger("skuel.routes.sidebar_badges")


def setup_sidebar_badges_routes(rt: Any, services: Services) -> None:
    """Register the Tasks+ sidebar badges endpoint."""

    if services.user is None:
        raise RuntimeError("UserService is required for the sidebar badges route")
    user_service = services.user

    @rt("/api/sidebar/badges")
    async def sidebar_badges(request: Request) -> Any:
        """HTMX OOB-swap endpoint: the Tasks+ sidebar's count + health badges.

        One fragment per Tasks+ row that has a stats config — exactly
        ``ACTIVITY_SIDEBAR_ITEMS ∩ DOMAIN_STATS_CONFIG`` — each an OOB
        ``sidebar-badge-{slug}`` span replacing the slot the sidebar rendered.
        A failed context read degrades to an empty fragment: badges are an
        enhancement, never the page.
        """
        user_uid = require_authenticated_user(request)

        context_result = await user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            return Div()
        context = context_result.value

        fragments: list[Any] = []
        for item in ACTIVITY_SIDEBAR_ITEMS:
            config = DOMAIN_STATS_CONFIG.get(item.slug)
            if config is None:
                continue
            count = config.count_fn(context)
            active = config.active_fn(context)
            status_args = config.status_args_fn(context)
            status = config.status_fn(*status_args)

            fragments.append(
                Span(
                    CountBadge(count, active),
                    HealthIndicator(status),
                    id=f"sidebar-badge-{item.slug}",
                    hx_swap_oob="true",
                    cls="flex items-center gap-1",
                )
            )

        return Div(*fragments)

    logger.info("✅ Sidebar badges route registered (/api/sidebar/badges)")


__all__ = ["setup_sidebar_badges_routes"]
