"""Principles API routes.

Provides HTMX-compatible endpoints for principle status updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.route_factories import (
    ActivityStatusApiConfig,
    create_activity_status_api_routes,
)
from ui.activities.principles_views import PrincipleCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.models.principle.principle import Principle
    from core.services.principles_service import PrinciplesService
    from core.utils.result_simplified import Result


def create_principles_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    principles_service: PrinciplesService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Principles API routes."""

    async def update(uid: str, new_status: str) -> Result[Principle]:
        return await principles_service.core.update(uid, {"status": new_status})

    return create_activity_status_api_routes(
        rt,
        ActivityStatusApiConfig(
            domain_name="principles",
            singular="principle",
            service=principles_service,
            update_status=update,
            card_fn=PrincipleCard,
        ),
    )
