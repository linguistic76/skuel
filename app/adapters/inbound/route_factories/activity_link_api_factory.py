"""Generic Activity Domain cross-domain link + knowledge-pattern API factory.

Two same-shape route families that were copy-pasted across the 6 Activity
Domain ``*_api.py`` modules:

Cross-domain links — ``POST /api/{domain}/{action}``:
    parse body → verify ownership of the source entity → optionally verify
    ownership of a user-owned link target (goal/principle; Ku is SHARED
    content and needs no check) → call the domain link method →
    ``{"linked": bool}``. Only the request model, the ownership fields, and
    the service call vary — captured in ``CrossDomainLinkSpec``.

Knowledge patterns — ``GET /api/{domain}/knowledge-patterns``:
    the identical handler + 8-field ``LearningPattern`` serialization dict
    that was duplicated 6x, now emitted once per domain from
    ``create_knowledge_patterns_api_route``.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md,
     /docs/patterns/OWNERSHIP_VERIFICATION.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.route_factories.route_helpers import (
    parse_int_query_param,
    verify_entity_ownership,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic import BaseModel

    from adapters.inbound.fasthtml_types import RouteDecorator
    from core.models.type_hints import UserUID
    from core.services.knowledge.knowledge_pattern_analyzer import LearningPattern


@dataclass(frozen=True)
class LinkTargetSpec:
    """Ownership check for a user-owned link target (goal/principle).

    Omit for SHARED targets (Ku) — shared content is readable by everyone,
    so linking to it needs no target ownership check.
    """

    service: Any
    uid_field: str
    singular: str


@dataclass(frozen=True)
class CrossDomainLinkSpec[R: BaseModel]:
    """One ``POST /api/{domain}/{action}`` cross-domain link endpoint.

    Attributes:
        action: URL segment, e.g. ``"link-goal"``, ``"link-knowledge"``.
        request_model: Pydantic body model (``Link*To*Request``).
        owner_uid_field: Request attribute holding the source entity UID that
            must belong to the authenticated user.
        apply: Coroutine ``(parsed request) -> Result[bool]``. A small named
            adapter per domain unpacks the request into the service call.
        doc: Route docstring (shows the relationship type).
        target: Optional second ownership check for a user-owned target.
    """

    action: str
    request_model: type[R]
    owner_uid_field: str
    apply: Callable[[R], Awaitable[Result[bool]]]
    doc: str = ""
    target: LinkTargetSpec | None = None


def create_activity_link_api_routes(
    rt: RouteDecorator,
    *,
    domain_name: str,
    singular: str,
    service: Any,
    specs: tuple[CrossDomainLinkSpec[Any], ...],
) -> list[Any]:
    """Register ``POST /api/{domain}/{action}`` link routes for one domain."""
    return [_register_link_route(rt, domain_name, singular, service, spec) for spec in specs]


def _register_link_route(
    rt: RouteDecorator,
    domain_name: str,
    singular: str,
    service: Any,
    spec: CrossDomainLinkSpec[Any],
) -> Any:
    async def link(request: Request) -> Result[dict[str, Any]]:
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, spec.request_model)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            service, getattr(req, spec.owner_uid_field), user_uid, singular
        )
        if ownership_error:
            return ownership_error
        if spec.target is not None:
            target_error = await verify_entity_ownership(
                spec.target.service,
                getattr(req, spec.target.uid_field),
                user_uid,
                spec.target.singular,
            )
            if target_error:
                return target_error
        result = await spec.apply(req)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"linked": result.value})

    link.__name__ = f"{singular}_{spec.action.replace('-', '_')}"
    link.__doc__ = spec.doc or f"Link {singular} via {spec.action}."
    return rt(f"/api/{domain_name}/{spec.action}", methods=["POST"])(
        csrf_protected(boundary_handler()(link))
    )


def create_knowledge_patterns_api_route(
    rt: RouteDecorator,
    domain_name: str,
    analyze_learning_patterns: Callable[[UserUID, int], Awaitable[Result[list[Any]]]],
) -> Any:
    """Register ``GET /api/{domain}/knowledge-patterns`` for one domain."""

    async def knowledge_patterns(request: Request) -> Result[dict[str, Any]]:
        user_uid = require_authenticated_user(request)
        timeframe_days = parse_int_query_param(
            request.query_params, "timeframe_days", default=30, minimum=1, maximum=365
        )
        result = await analyze_learning_patterns(user_uid, timeframe_days)
        if result.is_error:
            return Result.fail(result)
        patterns = [_serialize_learning_pattern(p) for p in result.value]
        return Result.ok(
            {"patterns": patterns, "count": len(patterns), "timeframe_days": timeframe_days}
        )

    knowledge_patterns.__name__ = f"{domain_name}_knowledge_patterns"
    knowledge_patterns.__doc__ = (
        f"Detect knowledge-learning patterns across the authenticated user's {domain_name}."
    )
    return rt(f"/api/{domain_name}/knowledge-patterns", methods=["GET"])(
        boundary_handler()(knowledge_patterns)
    )


def _serialize_learning_pattern(p: LearningPattern) -> dict[str, Any]:
    return {
        "pattern_type": p.pattern_type.value,
        "knowledge_uids": p.knowledge_uids,
        "entity_uids": p.entity_uids,
        "confidence": p.confidence,
        "timeframe_days": p.timeframe_days,
        "frequency": p.frequency,
        "growth_indicator": p.growth_indicator,
        "metadata": p.metadata,
    }


__all__ = [
    "CrossDomainLinkSpec",
    "LinkTargetSpec",
    "create_activity_link_api_routes",
    "create_knowledge_patterns_api_route",
]
