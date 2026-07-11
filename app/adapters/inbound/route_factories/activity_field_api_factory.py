"""Generic Activity Domain single-field update API route factory.

All 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles)
expose the same HTMX inline-update endpoints, one per editable card field:

    POST /api/{domain}/{uid}/status    — form["status"]   → updated {Domain}Card
    POST /api/{domain}/{uid}/priority  — form["priority"] → updated {Domain}Card

Each field is a ``FieldUpdateSpec``: the URL segment / form-field name, the
coroutine that applies the change, and an optional value whitelist. Fields
whose transitions the service itself validates (status) omit the whitelist;
plain enum fields (priority) declare it so garbage never reaches the graph.

This generalizes the former status-only factory: auth, ownership verification,
form parsing, and card re-render are shared plumbing — only the field varies.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories.route_helpers import verify_entity_ownership
from core.models.enums import Priority
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import RouteDecorator
    from core.utils.result_simplified import Result

# Whitelist for FieldUpdateSpec(field="priority", ...) — all 6 domains share it.
PRIORITY_VALUES: frozenset[str] = frozenset(p.value for p in Priority)


@dataclass(frozen=True)
class FieldUpdateSpec[T]:
    """One inline-editable field on an Activity Domain card.

    Attributes:
        field: URL segment and form-field name, e.g. ``"status"``, ``"priority"``.
        apply: Coroutine ``(uid, new_value) -> Result[T]``. Domains whose field
            transitions have side effects (e.g. goals setting
            ``progress_percentage=100`` on completion) dispatch internally;
            simple fields delegate to the facade's typed-intent update.
        allowed_values: Optional whitelist checked before ``apply``. ``None``
            means the service validates (status transitions); enum-backed
            fields like priority pass their value set (``PRIORITY_VALUES``).
    """

    field: str
    apply: Callable[[str, str], Awaitable[Result[T]]]
    allowed_values: frozenset[str] | None = None


@dataclass(frozen=True)
class ActivityFieldApiConfig[T]:
    """Configuration for one Activity Domain's inline field-update endpoints.

    The type parameter ``T`` ties each spec's ``apply`` return value to
    ``card_fn``'s input, so a tasks config produces ``Result[Task]`` and the
    factory's ``card_fn(result.value)`` is checked against ``Task``.

    Attributes:
        domain_name: URL path segment, e.g. ``"tasks"``.
        singular: Singular form used in error messages, e.g. ``"task"``.
        service: Facade with a ``verify_ownership(uid, user_uid)`` method
            (all Activity Domain facades inherit it from ``BaseService``).
        card_fn: Card component receiving the updated entity, returns an FT.
        fields: The inline-editable fields to register, one route each.
    """

    domain_name: str
    singular: str
    service: Any
    card_fn: Callable[[T], FT]
    fields: tuple[FieldUpdateSpec[T], ...] = field(default_factory=tuple)


def create_activity_field_api_routes[T](
    rt: RouteDecorator,
    config: ActivityFieldApiConfig[T],
) -> list[Any]:
    """Register ``POST /api/{domain}/{uid}/{field}`` routes for one domain."""
    return [_register_field_route(rt, config, spec) for spec in config.fields]


def _register_field_route[T](
    rt: RouteDecorator,
    config: ActivityFieldApiConfig[T],
    spec: FieldUpdateSpec[T],
) -> Any:
    not_found = f"{config.singular.capitalize()} not found"

    async def update_field(request: Request, uid: str) -> Any:
        user_uid = require_authenticated_user(request)

        ownership_error = await verify_entity_ownership(
            config.service, uid, user_uid, config.domain_name
        )
        if ownership_error is not None:
            return render_error_banner(not_found)

        form = await request.form()
        raw_value = form.get(spec.field)
        if not raw_value:
            return render_error_banner(f"Missing {spec.field} value")

        new_value = str(raw_value)
        if spec.allowed_values is not None and new_value not in spec.allowed_values:
            return render_error_banner(f"Invalid {spec.field} value")

        result = await spec.apply(uid, new_value)
        if result.is_error:
            return render_error_banner(result.expect_error().display_message)

        return config.card_fn(result.value)

    # Distinct names per (domain, field) keep FastHTML route names unambiguous.
    update_field.__name__ = f"update_{config.domain_name}_{spec.field}"
    update_field.__doc__ = (
        f"Update {config.singular} {spec.field} (HTMX endpoint). Returns updated card."
    )
    route_path = f"/api/{config.domain_name}/{{uid}}/{spec.field}"
    return rt(route_path, methods=["POST"])(csrf_protected(update_field))


__all__ = [
    "PRIORITY_VALUES",
    "ActivityFieldApiConfig",
    "FieldUpdateSpec",
    "create_activity_field_api_routes",
]
