"""Choices API routes.

Provides HTMX-compatible endpoints for choice status updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.route_factories import (
    ActivityStatusApiConfig,
    create_activity_status_api_routes,
)
from ui.activities.choices_views import ChoiceCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.models.choice.choice import Choice
    from core.services.choices_service import ChoicesService
    from core.utils.result_simplified import Result


def create_choices_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    choices_service: ChoicesService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Choices API routes."""

    async def update(uid: str, new_status: str) -> Result[Choice]:
        return await choices_service.core.update(uid, {"status": new_status})

    return create_activity_status_api_routes(
        rt,
        ActivityStatusApiConfig(
            domain_name="choices",
            singular="choice",
            service=choices_service,
            update_status=update,
            card_fn=ChoiceCard,
        ),
    )
