"""Goals API routes.

Provides HTMX-compatible endpoints for goal status updates.

The transition dispatch (activate / complete / archive / cancel with their
per-state side effects) lives in ``GoalsService.set_status``; this route is
a transport shim.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.activity_status_api_factory import (
    ActivityStatusApiConfig,
    create_activity_status_api_routes,
)
from ui.activities.goals_views import GoalCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.goals_service import GoalsService


def create_goals_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    goals_service: GoalsService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Goals API routes."""
    return create_activity_status_api_routes(
        rt,
        ActivityStatusApiConfig(
            domain_name="goals",
            singular="goal",
            service=goals_service,
            update_status=goals_service.set_status,
            card_fn=GoalCard,
        ),
    )
