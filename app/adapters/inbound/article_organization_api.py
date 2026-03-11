"""
KU Organization API — ORGANIZES Relationship REST Endpoints
============================================================

REST API for organizing Kus via ORGANIZES relationships.

Any Ku can organize other Kus — this is emergent identity, not a type discriminator.
Write operations (organize, unorganize, reorder) require ADMIN role.
Read operations are public.

Routes follow SKUEL's established patterns:
- Result[T] error handling throughout
- @boundary_handler() for automatic HTTP response conversion
- 201 Created for POST resource creation
- 200 OK for actions and updates
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request
from pydantic import ValidationError

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import parse_int_query_param
from core.models.article.article_request import ArticleOrganizeRequest, ArticleReorderRequest
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import ArticleOperations


def create_article_organization_api_routes(
    app: Any, rt: Any, ku_service: "ArticleOperations", user_service: Any = None
) -> list[Any]:
    """
    Create KU organization API routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        ku_service: KU service with organization methods
        user_service: User service for admin role verification
    """

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # IDENTITY OPERATIONS
    # ========================================================================

    @rt("/api/article/{uid}/is-organizer")
    @boundary_handler()
    async def is_organizer_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Check if a Ku has organized children."""
        result = await ku_service.is_organizer(uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok({"ku_uid": uid, "is_organizer": result.value})

    @rt("/api/article/{uid}/organization")
    @boundary_handler()
    async def get_organization_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get a Ku with its organized children hierarchy."""
        result = await ku_service.get_organization_view(uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok(result.value.to_dict() if result.value else None)

    # ========================================================================
    # ORGANIZATION OPERATIONS (ADMIN ONLY)
    # ========================================================================

    @rt("/api/article/organize", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler(success_status=201)
    async def organize_route(request, current_user) -> Result[dict[str, Any]]:
        """Organize a Ku under another Ku (create ORGANIZES relationship)."""
        body = await request.json()
        try:
            req = ArticleOrganizeRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))

        result = await ku_service.organize(req.parent_uid, req.child_uid, req.order)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok(
            {"success": result.value, "parent_uid": req.parent_uid, "child_uid": req.child_uid}
        )

    @rt("/api/article/unorganize", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def unorganize_route(request, current_user) -> Result[dict[str, Any]]:
        """Remove organization relationship between Kus."""
        body = await request.json()
        try:
            req = ArticleOrganizeRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))

        result = await ku_service.unorganize(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok({"success": result.value})

    @rt("/api/article/reorder", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def reorder_route(request, current_user) -> Result[dict[str, Any]]:
        """Change the order of a child Ku within its parent."""
        body = await request.json()
        try:
            req = ArticleReorderRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))

        result = await ku_service.reorder(req.parent_uid, req.child_uid, req.new_order)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok({"success": result.value})

    # ========================================================================
    # DISCOVERY OPERATIONS
    # ========================================================================

    @rt("/api/article/{uid}/organizers")
    @boundary_handler()
    async def find_organizers_route(request: Request, uid: str) -> Result[list[Any]]:
        """Find all parent Kus that organize the given Ku."""
        return await ku_service.find_organizers(uid)

    @rt("/api/article/root-organizers")
    @boundary_handler()
    async def list_root_organizers_route(request: Request) -> Result[list[Any]]:
        """List Kus that organize others but are not themselves organized (root organizers)."""
        params = dict(request.query_params)
        limit = parse_int_query_param(params, "limit", 50, minimum=1, maximum=500)
        return await ku_service.list_root_organizers(limit)

    @rt("/api/article/{uid}/organized-children")
    @boundary_handler()
    async def get_organized_children_route(request: Request, uid: str) -> Result[list[Any]]:
        """Get direct children of a Ku organized by ORGANIZES relationship."""
        return await ku_service.get_organized_children(uid)

    return []  # Routes registered via @rt() decorators
