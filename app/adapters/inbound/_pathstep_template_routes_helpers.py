"""
Helpers for the 6 PathStep Activity Template route files (Phase 5).
====================================================================

Each per-template route file is mostly a one-line ``DomainRouteConfig``;
the small amount of shared shape (PS-attachment endpoints + the SHARED-scope
+ TEACHER-role CRUD config) lives here so the per-template file stays at
~15 lines.

The api_factory built by :func:`make_pathstep_template_api_factory` registers
three endpoints under ``/api/{domain}``:

    POST /attach?ps_uid=...&template_uid=...     → MERGE the HAS_*_TEMPLATE edge
    POST /detach?ps_uid=...&template_uid=...     → DELETE the edge
    GET  /list-by-ps?ps_uid=...                  → templates attached to a PS

CRUD (create/get/update/delete/list) is registered separately by
:class:`CRUDRouteFactory` via :class:`CRUDRouteConfig`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from adapters.inbound.auth import (
    make_service_getter,
    require_authenticated_user,
    require_teacher,
)
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import (
    CRUDRouteConfig,
    DomainRouteConfig,
)
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import BaseModel

logger = get_logger(__name__)


def make_pathstep_template_api_factory(
    domain_name: str,
) -> Callable[..., list[Any]]:
    """Build the api_factory for a per-template route file.

    The factory registers three endpoints scoped to ``/api/{domain_name}``.
    Routes are gated by TEACHER role (admins satisfy teacher via role
    hierarchy in ``has_permission``). The primary service must expose
    ``attach_to_pathstep``, ``detach_from_pathstep``, and
    ``list_for_pathstep`` — all six template services do via
    :class:`_BaseTemplateService`.
    """

    def api_factory(
        app: FastHTMLApp,
        rt: RouteDecorator,
        primary_service: Any,
        user_service: Any = None,
        **_kwargs: Any,
    ) -> list[Any]:
        get_user_service = make_service_getter(user_service)

        @rt(f"/api/{domain_name}/attach", methods=["POST"])
        @csrf_protected
        @require_teacher(get_user_service)
        @boundary_handler()
        async def attach_template(
            request: Any,
            ps_uid: str,
            template_uid: str,
            current_user: Any = None,
        ) -> Result[bool]:
            """Attach a template to a PathStep via the HAS_*_TEMPLATE edge."""
            return cast(
                "Result[bool]",
                await primary_service.attach_to_pathstep(ps_uid, template_uid),
            )

        @rt(f"/api/{domain_name}/detach", methods=["POST"])
        @csrf_protected
        @require_teacher(get_user_service)
        @boundary_handler()
        async def detach_template(
            request: Any,
            ps_uid: str,
            template_uid: str,
            current_user: Any = None,
        ) -> Result[bool]:
            """Detach a template from a PathStep."""
            return cast(
                "Result[bool]",
                await primary_service.detach_from_pathstep(ps_uid, template_uid),
            )

        @rt(f"/api/{domain_name}/list-by-ps", methods=["GET"])
        @boundary_handler()
        async def list_templates_by_ps(
            request: Any,
            ps_uid: str,
        ) -> Result[list[dict[str, Any]]]:
            """List templates attached to a given PathStep.

            Read-only: open to any authenticated user (no TEACHER gate) — the PS
            and its templates are SHARED curriculum content. But enumeration
            still requires a session: reject anonymous callers with 401 so the
            attachment graph isn't readable without login. ``boundary_handler``
            re-raises the ``HTTPException`` raised here.
            """
            require_authenticated_user(request)
            return cast(
                "Result[list[dict[str, Any]]]",
                await primary_service.list_for_pathstep(ps_uid),
            )

        return [attach_template, detach_template, list_templates_by_ps]

    return api_factory


def make_pathstep_template_route_config(
    *,
    domain_name: str,
    primary_service_attr: str,
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    uid_prefix: str,
) -> DomainRouteConfig:
    """Pre-populate the SHARED+TEACHER conventions for a template route file.

    All 6 Activity Template route files share these knobs:
    - scope=SHARED (curriculum content, not user content)
    - require_role=TEACHER (admins satisfy teacher)
    - api_factory=PS-attachment endpoints
    - user_service_attr="user_service" (role check needs UserService)
    """
    return DomainRouteConfig(
        domain_name=domain_name,
        primary_service_attr=primary_service_attr,
        api_factory=make_pathstep_template_api_factory(domain_name),
        ui_factory=None,
        api_related_services={"user_service": "user"},
        crud=CRUDRouteConfig(
            create_schema=create_schema,
            update_schema=update_schema,
            uid_prefix=uid_prefix,
            scope=ContentScope.SHARED,
            require_role=UserRole.TEACHER,
            user_service_attr="user_service",
        ),
    )
