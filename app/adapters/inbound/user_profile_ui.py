"""
User Profile UI Routes - Profile Hub Page (MOC Pattern)
=======================================================

Routes for the user profile hub page and related endpoints.

Key Routes:
- GET /profile - Profile hub (4 tabs: Curriculum / Activities / Submissions / Reports)
- GET /profile/settings - 301 redirect to /settings
- GET /profile/shared - Shared With Me inbox (SHARES_WITH entities, type-aware cards)

Architecture:
- /profile is a 4-tab hub (Alpine tab bar, HTMX lazy-loaded previews; no sidebar)
- Uses BasePage(STANDARD) — the MOC pattern
- Uses UserContext (~250 fields) as the authoritative source for user state

See: /docs/design-principles/HUB_PAGES.md
"""

__version__ = "5.0"  # Hub page (MOC pattern) — no sidebar

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, Request

from core.config.settings import get_settings
from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from services_bootstrap import Services

from adapters.inbound.auth import require_authenticated_user
from core.services.user.unified_user_context import RichUserContext
from core.utils.logging import get_logger
from ui.activities.hub import render_domain_card_preview
from ui.layouts.base_page import BasePage
from ui.profile.domain_stats_config import (
    DOMAIN_STATS_CONFIG,
    knowledge_active,
    knowledge_count,
    knowledge_status,
    learning_paths_active,
    learning_paths_count,
    learning_paths_status,
    path_steps_active,
    path_steps_count,
    path_steps_status,
)

logger = get_logger("skuel.routes.user_profile")


# ============================================================================
# ERROR HANDLING HELPERS
# ============================================================================


async def error_page(
    message: str,
    status_code: int,
    user_display_name: str = "User",
    request: Request | None = None,
) -> Any:
    """
    Unified error page for profile routes.

    One path forward: Clear errors with no silent fallbacks.

    Args:
        message: Error message to display
        status_code: HTTP status code (404, 500, etc.)
        user_display_name: User's display name for page header
        request: Optional request for navbar auth detection

    Returns:
        Error page with consistent styling
    """
    from ui.patterns.error_banner import render_error_banner

    content = Div(
        render_error_banner(
            f"Error {status_code}",
            technical_details=message,
            show_details=get_settings().application.debug,
        ),
        cls="flex flex-col items-center justify-center min-h-[400px] p-8",
    )

    return await BasePage(
        content=content,
        title=f"Error {status_code}",
        request=request,
        active_page="profile",
    )


# ============================================================================
# ROUTE SETUP
# ============================================================================


def setup_user_profile_routes(rt: Any, services: "Services") -> None:
    """
    Setup user profile routes.

    Args:
        rt: FastHTML route decorator
        services: Services container with all backends
    """

    if services.user is None:
        raise RuntimeError("UserService is required for profile routes")
    user_service = services.user

    profile_orchestrator = services.profile_orchestrator
    if profile_orchestrator is None:
        raise RuntimeError("ProfileOrchestrator is required for profile routes")

    # ========================================================================
    # PROFILE HUB ROUTES
    # ========================================================================

    async def _get_context(
        user_uid: UserUID,
    ) -> RichUserContext:
        """
        Get rich UserContext — single call, includes user identity + role.

        Args:
            user_uid: Authenticated user's UID

        Returns:
            RichUserContext with ~250 fields including user_role, display_name, username

        Raises:
            ValueError: If context cannot be loaded
        """
        context_result = await user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            raise ValueError(f"Failed to load context for user: {user_uid}")
        return context_result.value

    @rt("/profile")
    async def profile_hub(request: Request) -> Any:
        """Profile hub — 4 tabs (Curriculum / Activities / Submissions / Reports).

        The active tab is selected by `?tab=` (curriculum | activities |
        submissions | reports), defaulting to "submissions" — the action tab
        (links to the /submissions pages).
        """
        require_authenticated_user(request)

        from ui.profile.hub import ProfileHubView, normalize_tab

        active_tab = normalize_tab(request.query_params.get("tab"))

        return await BasePage(
            content=ProfileHubView(active_tab=active_tab),
            title="Profile",
            request=request,
            active_page="profile",
        )

    @rt("/api/profile/{slug}/preview")
    async def domain_card_preview(request: Request, slug: str) -> Any:
        """
        HTMX fragment: top 3 active items for a domain block, sorted by priority.

        Called by the Activities tab accordion blocks on /profile via
        hx-trigger="intersect once". Returns a grid of up to 3 preview cards
        (title + priority badge) or an empty-state message.

        Requires authentication.
        """
        user_uid = require_authenticated_user(request)

        result = await profile_orchestrator.get_domain_preview_items(user_uid, slug)

        if result.is_error:
            from fasthtml.common import P as Para

            logger.warning(
                "Failed to load domain card preview",
                extra={"slug": slug, "user_uid": user_uid, "error": str(result.error)},
            )
            return Para("Unable to load items", cls="text-sm text-muted-foreground py-2")

        return render_domain_card_preview(result.value, slug)

    @rt("/api/sidebar/badges")
    async def sidebar_badges(request: Request) -> Any:
        """HTMX OOB-swap endpoint: async-loaded count + status badges for sidebar items.

        Returns Span elements with hx-swap-oob="true" that replace the
        `sidebar-badge-{slug}` placeholders rendered by `_default_item_renderer`.
        """
        from fasthtml.common import Span

        from ui.profile.badges import CountBadge, HealthIndicator

        user_uid = require_authenticated_user(request)

        try:
            context = await _get_context(user_uid)
        except ValueError:
            # Degrade silently — badges are enhancement, not critical
            return Div()

        fragments: list[Any] = []

        # Activity domain badges
        for slug, config in DOMAIN_STATS_CONFIG.items():
            count = config.count_fn(context)
            active = config.active_fn(context)
            status_args = config.status_args_fn(context)
            status = config.status_fn(*status_args)

            fragments.append(
                Span(
                    CountBadge(count, active),
                    HealthIndicator(status),
                    id=f"sidebar-badge-{slug}",
                    hx_swap_oob="true",
                    cls="flex items-center gap-1",
                )
            )

        # Curriculum badges
        curriculum_configs: list[tuple[str, int, int, str]] = [
            (
                "knowledge",
                knowledge_count(context),
                knowledge_active(context),
                knowledge_status(context),
            ),
            (
                "path-steps",
                path_steps_count(context),
                path_steps_active(context),
                path_steps_status(context),
            ),
            (
                "learning-paths",
                learning_paths_count(context),
                learning_paths_active(context),
                learning_paths_status(context),
            ),
        ]
        for slug, count, active, status in curriculum_configs:
            fragments.append(
                Span(
                    CountBadge(count, active),
                    HealthIndicator(status),
                    id=f"sidebar-badge-{slug}",
                    hx_swap_oob="true",
                    cls="flex items-center gap-1",
                )
            )

        return Div(*fragments)

    @rt("/profile/shared")
    async def profile_shared(request: Request) -> Any:
        """Shared With Me — entities shared with the current user via SHARES_WITH.

        Type-aware inbox: ADR-040 auto-shared feedback (EntryReports,
        RevisedExercises) and manually shared FormSubmissions render the same
        card shape. Group shares surface on /groups, not here.
        """
        user_uid = require_authenticated_user(request)

        from ui.profile.shared_view import SharedWithMeView

        shared_items: list[dict[str, Any]] = []
        items_result = await profile_orchestrator.get_shared_with_me_items(
            user_uid=user_uid,
            limit=50,
        )
        if not items_result.is_error:
            shared_items = items_result.value

        return await BasePage(
            content=SharedWithMeView(shared_items),
            title="Shared With Me",
            request=request,
            active_page="shared",
        )

    logger.info("✅ Profile routes registered (/profile, /profile/shared)")


__all__ = ["setup_user_profile_routes"]
