"""Tasks API routes.

Provides HTMX-compatible endpoints for task status updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.activities.tasks_views import TaskCard
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import (
        FastHTMLApp,
        RouteDecorator,
    )
    from core.services.tasks_service import TasksService

logger = get_logger("skuel.routes.tasks_api")


def create_tasks_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Tasks API routes."""
    routes: list[Any] = []

    @rt("/api/tasks/{uid}/status", methods=["POST"])
    async def update_task_status(request: Request, uid: str) -> Any:
        """Update task status (HTMX endpoint). Returns updated TaskCard."""
        user_uid = require_authenticated_user(request)

        # Verify ownership by fetching the task first
        task_result = await tasks_service.get_task(uid)
        if task_result.is_error:
            return render_error_banner("Task not found")
        task = task_result.value
        if task.user_uid != user_uid:
            return render_error_banner("Task not found")

        # Get new status from form data or JSON
        form = await request.form()
        new_status = form.get("status")

        if not new_status:
            return render_error_banner("Missing status value")

        # Update the task
        result = await tasks_service.update_task(uid, {"status": new_status})
        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        return TaskCard(result.value)

    routes.extend([update_task_status])
    return routes
