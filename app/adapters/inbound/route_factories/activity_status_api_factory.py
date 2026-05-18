"""Generic Activity Domain status-update API route factory.

All 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles)
expose the same HTMX status-update endpoint:

    POST /api/{domain}/{uid}/status  — form["status"] → updated {Domain}Card

The per-domain file previously hand-rolled ownership verification and the
status-update call. This factory collapses each to a config + one call,
mirroring the shape already used by ``activity_ui_factory``.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fasthtml.common import FT

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories.route_helpers import verify_entity_ownership
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from adapters.inbound.fasthtml_types import RouteDecorator
    from core.utils.result_simplified import Result


@dataclass(frozen=True)
class ActivityStatusApiConfig[T]:
    """Configuration for a single Activity Domain's status-update endpoint.

    The type parameter ``T`` ties ``update_status``'s return value to
    ``card_fn``'s input, so a tasks config produces ``Result[Task]`` and the
    factory's ``card_fn(result.value)`` is checked against ``Task``.

    Attributes:
        domain_name: URL path segment, e.g. ``"tasks"``.
        singular: Singular form used in error messages, e.g. ``"task"``.
        service: Facade with a ``verify_ownership(uid, user_uid)`` method
            (all Activity Domain facades inherit it from ``BaseService``).
        update_status: Coroutine ``(uid, new_status) -> Result[T]``. Domains
            whose status transitions have side effects (e.g. goals setting
            ``progress_percentage=100`` on completion) dispatch internally;
            simple domains delegate to ``core.update``.
        card_fn: Card component receiving the updated entity, returns an FT.
    """

    domain_name: str
    singular: str
    service: Any
    update_status: Callable[[str, str], Awaitable[Result[T]]]
    card_fn: Callable[[T], FT]


def create_activity_status_api_routes[T](
    rt: RouteDecorator,
    config: ActivityStatusApiConfig[T],
) -> list[Any]:
    """Register the ``POST /api/{domain}/{uid}/status`` route for one domain."""
    not_found = f"{config.singular.capitalize()} not found"

    @rt(f"/api/{config.domain_name}/{{uid}}/status", methods=["POST"])
    @csrf_protected
    async def update_status(request: Request, uid: str) -> Any:
        """Update entity status (HTMX endpoint). Returns updated card."""
        user_uid = require_authenticated_user(request)

        ownership_error = await verify_entity_ownership(
            config.service, uid, user_uid, config.domain_name
        )
        if ownership_error is not None:
            return render_error_banner(not_found)

        form = await request.form()
        new_status = form.get("status")
        if not new_status:
            return render_error_banner("Missing status value")

        result = await config.update_status(uid, str(new_status))
        if result.is_error:
            return render_error_banner(result.expect_error().display_message)

        return config.card_fn(result.value)

    return [update_status]


__all__ = ["ActivityStatusApiConfig", "create_activity_status_api_routes"]
