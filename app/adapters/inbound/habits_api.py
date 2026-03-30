"""Habits API routes.

Provides HTMX-compatible endpoints for habit status updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.activities.habits_views import HabitCard
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import (
        FastHTMLApp,
        Request,
        RouteDecorator,
        RouteList,
    )
    from core.services.habits_service import HabitsService

logger = get_logger("skuel.routes.habits_api")


def create_habits_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    habits_service: HabitsService,
) -> RouteList:
    """Register Habits API routes."""
    routes: list[Any] = []

    @rt("/api/habits/{uid}/status", methods=["POST"])
    async def update_habit_status(request: Request, uid: str) -> Any:
        """Update habit status (HTMX endpoint). Returns updated HabitCard."""
        user_uid = require_authenticated_user(request)

        # Verify ownership
        habit_result = await habits_service.get_habit(uid)
        if habit_result.is_error:
            return render_error_banner("Habit not found")
        habit = habit_result.value
        if habit.user_uid != user_uid:
            return render_error_banner("Habit not found")

        # Get new status from form data
        form = await request.form()
        new_status = form.get("status")

        if not new_status:
            return render_error_banner("Missing status value")

        result = await habits_service.core.update(uid, {"status": new_status})
        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        return HabitCard(result.value)

    routes.extend([update_habit_status])
    return routes
