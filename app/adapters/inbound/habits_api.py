"""Habits API routes.

Provides HTMX-compatible endpoints for habit status updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from adapters.inbound.activity_status_api_factory import (
    ActivityStatusApiConfig,
    create_activity_status_api_routes,
)
from ui.activities.habits_views import HabitCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.habits_service import HabitsService
    from core.utils.result_simplified import Result


def create_habits_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    habits_service: HabitsService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Habits API routes."""

    async def update(uid: str, new_status: str) -> Result[Any]:
        # self.core is loosely typed on the facade; cast narrows for mypy.
        return cast(
            "Result[Any]",
            await habits_service.core.update(uid, {"status": new_status}),
        )

    return create_activity_status_api_routes(
        rt,
        ActivityStatusApiConfig(
            domain_name="habits",
            singular="habit",
            service=habits_service,
            update_status=update,
            card_fn=HabitCard,
        ),
    )
