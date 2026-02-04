"""
SEL API Routes
==============

JSON API and HTMX fragment routes for SEL (Social Emotional Learning) domain.

API Routes:
- GET /api/sel/journey - Get SEL journey JSON (authenticated)
- GET /api/sel/curriculum/{category} - Get personalized curriculum JSON (authenticated)

HTMX Routes:
- GET /api/sel/journey-html - Render SEL journey HTML fragment
- GET /api/sel/curriculum-html/{category} - Render curriculum grid HTML fragment
"""

from typing import Any

from fasthtml.common import P, Request

from core.auth import require_authenticated_user
from core.errors import NotFoundError
from core.models.ku.ku import Ku
from core.models.sel.sel_progress import SELJourney
from core.models.shared_enums import SELCategory
from core.ui.daisy_components import Div
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.sel.api")


def create_sel_api_routes(
    app: Any,
    rt: Any,
    adaptive_sel_service: Any,
) -> list[Any]:
    """
    Create SEL API routes.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        adaptive_sel_service: AdaptiveSEL service facade

    Returns:
        List of registered route functions
    """

    # ========================================================================
    # JSON API ROUTES
    # ========================================================================

    @rt("/api/sel/journey")
    @boundary_handler()
    async def get_sel_journey_api(request: Request) -> Result[SELJourney]:
        """
        API: Get authenticated user's complete SEL journey.
        Requires authentication.

        Returns:
            Result[SELJourney]: Journey with progress in all categories
        """
        if not adaptive_sel_service:
            return Result.fail(
                Errors.system("AdaptiveSELService not available", service="AdaptiveSELService")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        result: Result[SELJourney] = await adaptive_sel_service.get_sel_journey(user_uid)
        return result

    @rt("/api/sel/curriculum/{category}")
    @boundary_handler()
    async def get_personalized_curriculum_api(
        request: Request, category: str, limit: int = 10
    ) -> Result[list[Ku]]:
        """
        API: Get personalized curriculum for authenticated user in SEL category.
        Requires authentication.

        Args:
            category: SEL category (e.g., "self_awareness")
            limit: Maximum number of KUs to return

        Returns:
            Result[List[Ku]]: Personalized curriculum
        """
        if not adaptive_sel_service:
            return Result.fail(
                Errors.system("AdaptiveSELService not available", service="AdaptiveSELService")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        # Parse category
        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Result.fail(NotFoundError(f"Invalid SEL category: {category}"))

        result: Result[list[Ku]] = await adaptive_sel_service.get_personalized_curriculum(
            user_uid=user_uid, sel_category=sel_category, limit=limit
        )
        return result

    # ========================================================================
    # HTMX FRAGMENT ROUTES
    # ========================================================================

    @rt("/api/sel/journey-html")
    async def get_sel_journey_html(request: Request) -> Any:
        """HTMX: Render SEL journey as HTML fragment"""
        user_uid = require_authenticated_user(request)

        if not adaptive_sel_service:
            return Div(
                P(
                    "SEL service unavailable. Please try again later.",
                    cls="text-error text-center py-8",
                ),
                cls="alert alert-error",
            )

        result = await adaptive_sel_service.get_sel_journey(user_uid)

        if result.is_error:
            return Div(
                P(
                    "Unable to load your SEL journey. Please try again.",
                    cls="text-error text-center py-8",
                ),
                cls="alert alert-error",
            )

        journey = result.value

        # Lazy import to prevent circular dependencies
        from adapters.inbound.sel_components import SELJourneyOverview

        return SELJourneyOverview(journey)

    @rt("/api/sel/curriculum-html/{category}")
    async def get_curriculum_html(request: Request, category: str, limit: int = 10) -> Any:
        """HTMX: Render personalized curriculum as HTML fragment"""
        user_uid = require_authenticated_user(request)

        if not adaptive_sel_service:
            return Div(
                P("SEL service unavailable. Please try again later.", cls="text-error"),
                cls="alert alert-error",
            )

        # Parse category
        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Div(
                P(f"Invalid category: {category}", cls="text-error"), cls="alert alert-error"
            )

        result = await adaptive_sel_service.get_personalized_curriculum(
            user_uid=user_uid, sel_category=sel_category, limit=limit
        )

        if result.is_error:
            return Div(
                P("Unable to load curriculum. Please try again.", cls="text-error"),
                cls="alert alert-error",
            )

        curriculum = result.value

        if not curriculum:
            # Lazy import
            from ui.patterns.empty_state import EmptyState

            return EmptyState(
                title="No curriculum available yet",
                description="Complete prerequisite knowledge units to unlock content in this area.",
                icon="📚",
            )

        # Lazy import to prevent circular dependencies
        from adapters.inbound.sel_components import AdaptiveKUCard

        return Div(
            *[AdaptiveKUCard(ku) for ku in curriculum],
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        )

    logger.info("SEL API routes registered (4 endpoints)")

    return [
        get_sel_journey_api,
        get_personalized_curriculum_api,
        get_sel_journey_html,
        get_curriculum_html,
    ]


__all__ = ["create_sel_api_routes"]
