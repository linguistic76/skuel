"""Generic Activity Domain hierarchy API route factory.

All 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles)
expose the same ownership-verified hierarchy endpoints:

    GET  /api/{domain}/children        — JSON: direct children of a parent (?uid=)
    GET  /api/{domain}/{uid}/children  — FT fragment: TreeNodeList for HTMX lazy loading
    GET  /api/{domain}/parent          — JSON: immediate parent (?uid=), None if root
    GET  /api/{domain}/hierarchy       — JSON: ancestors/current/siblings/children/depth
    POST /api/{domain}/add-child       — create the parent-child relationship
    POST /api/{domain}/remove-child    — remove the parent-child relationship

The JSON and HTMX ``children`` variants render from ONE ownership-checked,
owner-filtered fetch (``_fetch_owned_children``) — one implementation, two
representations (One Path Forward). Only the domain wiring varies per domain:
the service methods and the relationship-create call (Tasks/Goals/Habits
carry ``progress_weight``; Events/Choices/Principles ignore it), captured in
``ActivityHierarchyApiConfig``.

The LP tree fragment stays on ``HierarchyRouteFactory`` — LearningPaths are
SHARED content with a step-based child model, not user-owned entities.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md,
     /docs/patterns/OWNERSHIP_VERIFICATION.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

from fasthtml.common import Div, Span

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.route_factories.route_helpers import verify_entity_ownership
from core.models.entity_requests import (
    AddHierarchyChildRequest,
    RemoveHierarchyChildRequest,
)
from core.models.user_owned_entity import UserOwnedEntity
from core.utils.result_simplified import ErrorCategory, Errors, Result
from ui.patterns.tree_view import TreeNodeList

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from adapters.inbound.fasthtml_types import RouteDecorator
    from core.models.type_hints import UserUID


# Module-level TypeVar (not PEP 695 function-scoped params): FastHTML evaluates
# handler annotations at runtime against module globals, so the type variable in
# Result[list[T]] / Result[Optional[T]] must be resolvable here (UP046/UP047 are
# project-ignored, matching base_service.py).
T = TypeVar("T", bound=UserOwnedEntity)


@dataclass(frozen=True)
class ActivityHierarchyApiConfig(Generic[T]):
    """Configuration for one Activity Domain's hierarchy endpoints.

    The type parameter ``T`` ties the fetch callables to the domain model, so
    a tasks config produces ``Result[list[Task]]`` handlers.

    Attributes:
        domain_name: URL path segment (plural), e.g. ``"tasks"``.
        singular: Singular form for error messages/fragments, e.g. ``"task"``.
        service: Facade with ``verify_ownership(uid, user_uid)`` (all Activity
            Domain facades inherit it from ``BaseService``).
        get_children: Coroutine ``(parent_uid) -> Result[list[T]]``, e.g. the
            bound ``get_subtasks``.
        get_parent: Coroutine ``(child_uid) -> Result[T | None]``.
        get_hierarchy: Coroutine ``(uid) -> Result[dict]`` with
            ``ancestors``/``current``/``siblings``/``children`` entity lists.
        add_child_relationship: Coroutine ``(AddHierarchyChildRequest) ->
            Result[bool]``. A small named adapter per domain decides whether
            ``progress_weight`` reaches the service.
        remove_child_relationship: Coroutine ``(parent_uid, child_uid) ->
            Result[bool]``, e.g. the bound ``remove_subtask_relationship``.
    """

    domain_name: str
    singular: str
    service: Any
    get_children: Callable[[str], Awaitable[Result[list[T]]]]
    get_parent: Callable[[str], Awaitable[Result[T | None]]]
    get_hierarchy: Callable[[str], Awaitable[Result[dict[str, Any]]]]
    add_child_relationship: Callable[[AddHierarchyChildRequest], Awaitable[Result[bool]]]
    remove_child_relationship: Callable[[str, str], Awaitable[Result[bool]]]


def create_activity_hierarchy_api_routes(
    rt: RouteDecorator,
    config: ActivityHierarchyApiConfig[T],
) -> list[Any]:
    """Register the shared hierarchy route block for one Activity Domain."""
    return [
        _register_children_json_route(rt, config),
        _register_children_fragment_route(rt, config),
        _register_parent_route(rt, config),
        _register_hierarchy_route(rt, config),
        _register_add_child_route(rt, config),
        _register_remove_child_route(rt, config),
    ]


async def _fetch_owned_children(
    config: ActivityHierarchyApiConfig[T],
    uid: str,
    user_uid: UserUID,
) -> Result[list[T]]:
    """Ownership-checked fetch of a parent's direct children, filtered to the owner.

    THE single children read path — both the JSON and the HTMX fragment
    variants render from this one ownership check + fetch.
    """
    ownership_error = await verify_entity_ownership(config.service, uid, user_uid, config.singular)
    if ownership_error:
        return ownership_error
    result = await config.get_children(uid)
    if result.is_error:
        return Result.fail(result)
    return Result.ok([child for child in result.value if child.user_uid == user_uid])


def _register_children_json_route(rt: RouteDecorator, config: ActivityHierarchyApiConfig[T]) -> Any:
    async def children(request: Request) -> Result[list[T]]:
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        return await _fetch_owned_children(config, uid, user_uid)

    children.__name__ = f"{config.singular}_children"
    children.__doc__ = f"Direct children of a parent {config.singular} (JSON)."
    return rt(f"/api/{config.domain_name}/children", methods=["GET"])(boundary_handler()(children))


def _register_children_fragment_route(
    rt: RouteDecorator, config: ActivityHierarchyApiConfig[T]
) -> Any:
    children_endpoint = f"/api/{config.domain_name}/{{uid}}/children"

    async def children_fragment(request: Request, uid: str, parent_depth: int = 0) -> Any:
        """Children as a TreeNodeList fragment for HTMX lazy loading.

        ``parent_depth`` is the depth of the parent node (children render at
        parent_depth + 1); -1 loads roots at depth 0.
        """
        user_uid = require_authenticated_user(request)
        result = await _fetch_owned_children(config, uid, user_uid)
        if result.is_error:
            error = result.expect_error()
            message = (
                "Not found or access denied"
                if error.category is ErrorCategory.NOT_FOUND
                else f"Error loading children: {error.display_message}"
            )
            return Div(Span(message, cls="text-error text-sm"), cls="px-2 py-1")

        nodes: list[dict[str, Any]] = []
        for child in result.value:
            grandchildren = await config.get_children(child.uid)
            has_children = not grandchildren.is_error and any(
                g.user_uid == user_uid for g in grandchildren.value
            )
            nodes.append({"uid": child.uid, "title": child.title, "has_children": has_children})

        return TreeNodeList(
            nodes=nodes,
            entity_type=config.singular,
            children_endpoint=children_endpoint,
            parent_depth=parent_depth,
        )

    children_fragment.__name__ = f"{config.singular}_children_fragment"
    return rt(children_endpoint, methods=["GET"])(children_fragment)


def _register_parent_route(rt: RouteDecorator, config: ActivityHierarchyApiConfig[T]) -> Any:
    async def parent(request: Request) -> Result[Optional[T]]:  # noqa: UP045
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(
            config.service, uid, user_uid, config.singular
        )
        if ownership_error:
            return ownership_error
        result = await config.get_parent(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is not None and result.value.user_uid != user_uid:
            return Result.ok(None)
        return result

    parent.__name__ = f"{config.singular}_parent"
    parent.__doc__ = f"Immediate parent of a child {config.singular} (None if root-level)."
    return rt(f"/api/{config.domain_name}/parent", methods=["GET"])(boundary_handler()(parent))


def _register_hierarchy_route(rt: RouteDecorator, config: ActivityHierarchyApiConfig[T]) -> Any:
    async def hierarchy(request: Request) -> Result[dict[str, Any]]:
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(
            config.service, uid, user_uid, config.singular
        )
        if ownership_error:
            return ownership_error
        result = await config.get_hierarchy(uid)
        if result.is_error:
            return Result.fail(result)
        h = result.value
        ancestors = [e for e in h["ancestors"] if e.user_uid == user_uid]
        return Result.ok(
            {
                "ancestors": ancestors,
                "current": h["current"],
                "siblings": [e for e in h["siblings"] if e.user_uid == user_uid],
                "children": [e for e in h["children"] if e.user_uid == user_uid],
                "depth": len(ancestors),
            }
        )

    hierarchy.__name__ = f"{config.singular}_hierarchy"
    hierarchy.__doc__ = "Full hierarchy context: ancestors, current, siblings, children, depth."
    return rt(f"/api/{config.domain_name}/hierarchy", methods=["GET"])(
        boundary_handler()(hierarchy)
    )


def _register_add_child_route(rt: RouteDecorator, config: ActivityHierarchyApiConfig[T]) -> Any:
    async def add_child(request: Request) -> Result[dict[str, Any]]:
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, AddHierarchyChildRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        if req.parent_uid == req.child_uid:
            return Result.fail(
                Errors.validation("parent_uid and child_uid must differ", field="child_uid")
            )
        for uid in (req.parent_uid, req.child_uid):
            ownership_error = await verify_entity_ownership(
                config.service, uid, user_uid, config.singular
            )
            if ownership_error:
                return ownership_error
        existing_parent = await config.get_parent(req.child_uid)
        if existing_parent.is_error:
            return Result.fail(existing_parent)
        if existing_parent.value is not None:
            return Result.fail(
                Errors.validation(
                    f"{config.singular} already has a parent — remove it first",
                    field="child_uid",
                )
            )
        result = await config.add_child_relationship(req)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"added": result.value})

    add_child.__name__ = f"{config.singular}_add_child"
    add_child.__doc__ = f"Add a parent-child relationship between two {config.domain_name}."
    return rt(f"/api/{config.domain_name}/add-child", methods=["POST"])(
        csrf_protected(boundary_handler()(add_child))
    )


def _register_remove_child_route(rt: RouteDecorator, config: ActivityHierarchyApiConfig[T]) -> Any:
    async def remove_child(request: Request) -> Result[dict[str, Any]]:
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, RemoveHierarchyChildRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        for uid in (req.parent_uid, req.child_uid):
            ownership_error = await verify_entity_ownership(
                config.service, uid, user_uid, config.singular
            )
            if ownership_error:
                return ownership_error
        result = await config.remove_child_relationship(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"removed": result.value})

    remove_child.__name__ = f"{config.singular}_remove_child"
    remove_child.__doc__ = (
        f"Remove a parent-child relationship (does not delete the {config.singular} nodes)."
    )
    return rt(f"/api/{config.domain_name}/remove-child", methods=["POST"])(
        csrf_protected(boundary_handler()(remove_child))
    )


__all__ = [
    "ActivityHierarchyApiConfig",
    "create_activity_hierarchy_api_routes",
]
