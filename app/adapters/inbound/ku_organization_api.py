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

from adapters.inbound.auth import require_admin
from adapters.inbound.boundary import boundary_handler
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import KuOperations


def create_ku_organization_api_routes(
    app: Any, rt: Any, ku_service: "KuOperations", user_service: Any = None
) -> list[Any]:
    """
    Create KU organization API routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        ku_service: KU service with organization methods
        user_service: User service for admin role verification
    """

    def get_user_service():
        return user_service

    # ========================================================================
    # IDENTITY OPERATIONS
    # ========================================================================

    @rt("/api/ku/{uid}/is-organizer")
    @boundary_handler()
    async def is_organizer_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Check if a Ku has organized children."""
        result = await ku_service.is_organizer(uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok({"ku_uid": uid, "is_organizer": result.value})

    @rt("/api/ku/{uid}/organization")
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

    @rt("/api/ku/organize", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler(success_status=201)
    async def organize_route(request, current_user) -> Result[dict[str, Any]]:
        """Organize a Ku under another Ku (create ORGANIZES relationship)."""
        body = await request.json()
        parent_uid = body.get("parent_uid")
        child_uid = body.get("child_uid")
        order = body.get("order", 0)

        if not parent_uid or not child_uid:
            return Result.fail(
                Errors.validation(
                    message="parent_uid and child_uid are required", field="request_body"
                )
            )

        result = await ku_service.organize(parent_uid, child_uid, order)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok(
            {"success": result.value, "parent_uid": parent_uid, "child_uid": child_uid}
        )

    @rt("/api/ku/unorganize", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def unorganize_route(request, current_user) -> Result[dict[str, Any]]:
        """Remove organization relationship between Kus."""
        body = await request.json()
        parent_uid = body.get("parent_uid")
        child_uid = body.get("child_uid")

        if not parent_uid or not child_uid:
            return Result.fail(
                Errors.validation(
                    message="parent_uid and child_uid are required", field="request_body"
                )
            )

        result = await ku_service.unorganize(parent_uid, child_uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok({"success": result.value})

    @rt("/api/ku/reorder", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def reorder_route(request, current_user) -> Result[dict[str, Any]]:
        """Change the order of a child Ku within its parent."""
        body = await request.json()
        parent_uid = body.get("parent_uid")
        child_uid = body.get("child_uid")
        new_order = body.get("new_order")

        if not parent_uid or not child_uid or new_order is None:
            return Result.fail(
                Errors.validation(
                    message="parent_uid, child_uid, and new_order are required",
                    field="request_body",
                )
            )

        result = await ku_service.reorder(parent_uid, child_uid, new_order)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok({"success": result.value})

    # ========================================================================
    # DISCOVERY OPERATIONS
    # ========================================================================

    @rt("/api/ku/{uid}/organizers")
    @boundary_handler()
    async def find_organizers_route(request: Request, uid: str) -> Result[list[Any]]:
        """Find all parent Kus that organize the given Ku."""
        return await ku_service.find_organizers(uid)

    @rt("/api/ku/root-organizers")
    @boundary_handler()
    async def list_root_organizers_route(request: Request) -> Result[list[Any]]:
        """List Kus that organize others but are not themselves organized (root organizers)."""
        params = dict(request.query_params)
        limit = int(params.get("limit", 50))
        return await ku_service.list_root_organizers(limit)

    @rt("/api/ku/{uid}/organized-children")
    @boundary_handler()
    async def get_organized_children_route(request: Request, uid: str) -> Result[list[Any]]:
        """Get direct children of a Ku organized by ORGANIZES relationship."""
        return await ku_service.get_organized_children(uid)

    return []  # Routes registered via @rt() decorators
