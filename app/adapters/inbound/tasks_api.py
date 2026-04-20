"""Tasks API routes.

Provides HTMX-compatible endpoints for task status updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.activity_status_api_factory import (
    ActivityStatusApiConfig,
    create_activity_status_api_routes,
)
from ui.activities.tasks_views import TaskCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.tasks_service import TasksService
    from core.utils.result_simplified import Result


def create_tasks_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Tasks API routes."""

    async def update(uid: str, new_status: str) -> Result[Any]:
        return await tasks_service.update_task(uid, {"status": new_status})

    return create_activity_status_api_routes(
        rt,
        ActivityStatusApiConfig(
            domain_name="tasks",
            singular="task",
            service=tasks_service,
            update_status=update,
            card_fn=TaskCard,
        ),
    )
