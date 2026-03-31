"""
Lesson Organization API — ORGANIZES Relationship REST Endpoints
================================================================

REST API for organizing Lessons via ORGANIZES relationships.

Any Lesson can organize other Lessons — this is emergent identity, not a type discriminator.
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

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.route_factories import parse_int_query_param
from core.models.lesson.lesson_request import LessonOrganizeRequest, LessonReorderRequest
from core.ports.query_types import OrganizerResult, RootOrganizerResult
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports import LessonOperations


def create_lesson_organization_api_routes(
    app: Any, rt: Any, lesson_service: "LessonOperations", user_service: Any = None
) -> list[Any]:
    """
    Create Lesson organization API routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        lesson_service: Lesson service with organization methods
        user_service: User service for admin role verification
    """

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # IDENTITY OPERATIONS
    # ========================================================================

    @rt("/api/lesson/{uid}/is-organizer")
    @boundary_handler()
    async def is_organizer_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Check if a Lesson has organized children."""
        result = await lesson_service.is_organizer(uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"lesson_uid": uid, "is_organizer": result.value})

    @rt("/api/lesson/{uid}/organization")
    @boundary_handler()
    async def get_organization_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get a Lesson with its organized children hierarchy."""
        result = await lesson_service.get_organization_view(uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value.to_dict() if result.value else None)

    # ========================================================================
    # ORGANIZATION OPERATIONS (ADMIN ONLY)
    # ========================================================================

    @rt("/api/lesson/organize", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler(success_status=201)
    async def organize_route(request, current_user) -> Result[dict[str, Any]]:
        """Organize a Lesson under another Lesson (create ORGANIZES relationship)."""
        parsed = await parse_json_body(request, LessonOrganizeRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        result = await lesson_service.organize(req.parent_uid, req.child_uid, req.order)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            {"success": result.value, "parent_uid": req.parent_uid, "child_uid": req.child_uid}
        )

    @rt("/api/lesson/unorganize", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def unorganize_route(request, current_user) -> Result[dict[str, Any]]:
        """Remove organization relationship between Lessons."""
        parsed = await parse_json_body(request, LessonOrganizeRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        result = await lesson_service.unorganize(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"success": result.value})

    @rt("/api/lesson/reorder", methods=["POST"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def reorder_route(request, current_user) -> Result[dict[str, Any]]:
        """Change the order of a child Lesson within its parent."""
        parsed = await parse_json_body(request, LessonReorderRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        result = await lesson_service.reorder(req.parent_uid, req.child_uid, req.new_order)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"success": result.value})

    # ========================================================================
    # DISCOVERY OPERATIONS
    # ========================================================================

    @rt("/api/lesson/{uid}/organizers")
    @boundary_handler()
    async def find_organizers_route(request: Request, uid: str) -> Result[list[OrganizerResult]]:
        """Find all parent Lessons that organize the given Lesson."""
        return await lesson_service.find_organizers(uid)

    @rt("/api/lesson/root-organizers")
    @boundary_handler()
    async def list_root_organizers_route(request: Request) -> Result[list[RootOrganizerResult]]:
        """List Lessons that organize others but are not themselves organized (root organizers)."""
        params = dict(request.query_params)
        limit = parse_int_query_param(params, "limit", 50, minimum=1, maximum=500)
        return await lesson_service.list_root_organizers(limit)

    @rt("/api/lesson/{uid}/organized-children")
    @boundary_handler()
    async def get_organized_children_route(
        request: Request, uid: str
    ) -> Result[list[OrganizerResult]]:
        """Get direct children of a Lesson organized by ORGANIZES relationship."""
        return await lesson_service.get_organized_children(uid)

    return []  # Routes registered via @rt() decorators
