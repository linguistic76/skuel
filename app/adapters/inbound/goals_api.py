"""Goals API routes.

Provides HTMX-compatible endpoints for goal status updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.activities.goals_views import GoalCard
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import (
        FastHTMLApp,
        RouteDecorator,
        RouteList,
    )
    from core.services.goals_service import GoalsService

logger = get_logger("skuel.routes.goals_api")


def create_goals_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    goals_service: GoalsService,
) -> RouteList:
    """Register Goals API routes."""
    routes: list[Any] = []

    @rt("/api/goals/{uid}/status", methods=["POST"])
    async def update_goal_status(request: Request, uid: str) -> Any:
        """Update goal status (HTMX endpoint). Returns updated GoalCard."""
        user_uid = require_authenticated_user(request)

        # Verify ownership
        goal_result = await goals_service.get_goal(uid)
        if goal_result.is_error:
            return render_error_banner("Goal not found")
        goal = goal_result.value
        if goal.user_uid != user_uid:
            return render_error_banner("Goal not found")

        # Get new status from form data
        form = await request.form()
        new_status = form.get("status")

        if not new_status:
            return render_error_banner("Missing status value")

        # Map status to service methods
        if new_status == "active":
            result = await goals_service.activate_goal(uid)
        elif new_status == "completed":
            result = await goals_service.complete_goal(uid)
        elif new_status == "archived":
            result = await goals_service.archive_goal(uid)
        else:
            return render_error_banner(f"Invalid status: {new_status}")

        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        # Re-fetch the updated goal to render the card
        updated_result = await goals_service.get_goal(uid)
        if updated_result.is_error:
            return render_error_banner("Failed to reload goal")

        return GoalCard(updated_result.value)

    routes.extend([update_goal_status])
    return routes
