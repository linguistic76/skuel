"""Generic Activity Domain cross-domain link + knowledge-pattern API factory.

Two same-shape route families that were copy-pasted across the 6 Activity
Domain ``*_api.py`` modules:

Cross-domain links — ``POST /api/{domain}/{action}``:
    parse body → verify ownership of the source entity → for a user-owned
    link target (goal/principle), verify ownership of it too → call the
    domain link method → ``{"linked": bool}``. Only the request model, the
    ownership fields, and the service call vary — captured in
    ``CrossDomainLinkSpec``.

    The far end of EVERY link is admitted where the edge is written: the
    domain link method goes through ``UnifiedRelationshipService``, which
    refuses a far end that names nothing, is another user's, or is not the
    kind the link takes (a knowledge link takes a Ku) — all three as not
    found. A spec with no ``target`` is therefore not an unchecked link.

Knowledge patterns — ``GET /api/{domain}/knowledge-patterns``:
    the identical handler + 8-field ``LearningPattern`` serialization dict
    that was duplicated 6x, now emitted once per domain from
    ``create_knowledge_patterns_api_route``.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md,
     /docs/patterns/OWNERSHIP_VERIFICATION.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.route_factories.route_helpers import (
    parse_int_param_strict,
    verify_entity_ownership,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic import BaseModel

    from adapters.inbound.fasthtml_types import RouteDecorator
    from core.models.type_hints import UserUID
    from core.services.knowledge.knowledge_pattern_analyzer import LearningPattern


class LinkedPayload(TypedDict):
    """``POST /api/{domain}/{action}`` — whether the link edge was written."""

    linked: bool


class LearningPatternPayload(TypedDict):
    """One ``LearningPattern``, as ``GET /api/{domain}/knowledge-patterns`` serializes it."""

    pattern_type: str
    knowledge_uids: list[str]
    entity_uids: list[str]
    confidence: float
    timeframe_days: int
    frequency: int
    growth_indicator: float
    metadata: dict[str, Any]  # boundary: mirrors LearningPattern.metadata, per-pattern detail


class KnowledgePatternsPayload(TypedDict):
    """``GET /api/{domain}/knowledge-patterns`` — the patterns detected over the window."""

    patterns: list[LearningPatternPayload]
    count: int
    timeframe_days: int


@dataclass(frozen=True)
class LinkTargetSpec:
    """Route-level ownership check for a user-owned link target (goal/principle).

    Omit for a SHARED target (Ku): no facade owns it to ask. The service the
    link method writes through admits the far end either way — its kind and
    its owner — so an omitted target is still a checked one.
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
        target: Route-level ownership check for a user-owned target. The service
            admits the far end of every link whether or not this is set.
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
) -> None:
    """Register ``POST /api/{domain}/{action}`` link routes for one domain."""
    for spec in specs:
        _register_link_route(rt, domain_name, singular, service, spec)


def _register_link_route(
    rt: RouteDecorator,
    domain_name: str,
    singular: str,
    service: Any,
    spec: CrossDomainLinkSpec[Any],
) -> None:
    async def link(request: Request) -> Result[LinkedPayload]:
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
    rt(f"/api/{domain_name}/{spec.action}", methods=["POST"])(
        csrf_protected(boundary_handler()(link))
    )


def create_knowledge_patterns_api_route(
    rt: RouteDecorator,
    domain_name: str,
    analyze_learning_patterns: Callable[[UserUID, int], Awaitable[Result[list[LearningPattern]]]],
) -> None:
    """Register ``GET /api/{domain}/knowledge-patterns`` for one domain."""

    async def knowledge_patterns(request: Request) -> Result[KnowledgePatternsPayload]:
        user_uid = require_authenticated_user(request)
        timeframe_read = parse_int_param_strict(
            request.query_params.get("timeframe_days"), "timeframe_days", 1, default=30, cap=365
        )
        if timeframe_read.is_error:
            return Result.fail(timeframe_read)
        timeframe_days = timeframe_read.value
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
    rt(f"/api/{domain_name}/knowledge-patterns", methods=["GET"])(
        boundary_handler()(knowledge_patterns)
    )


def _serialize_learning_pattern(p: LearningPattern) -> LearningPatternPayload:
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
