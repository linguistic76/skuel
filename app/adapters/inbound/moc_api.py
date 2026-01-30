"""
MOC API - KU-Based Map of Content REST Endpoints
=================================================

Provides REST API for MOC (Map of Content) operations.

**January 2026 - KU-Based Architecture:**
MOC is NOT a separate entity - it IS a Knowledge Unit that organizes other KUs.
A KU "is" a MOC when it has outgoing ORGANIZES relationships.

This API provides MOC-specific semantics on top of KU operations:
- organize(): Create ORGANIZES relationship between KUs
- get(): Get KU with organized children (the "MOC view")
- is_moc(): Check if a KU has organized children
- find_mocs_containing(): Find MOCs that organize a KU

**Two Paths to Knowledge (Montessori-Inspired):**
- LS Path: Structured, linear, teacher-directed curriculum
- MOC Path: Unstructured, graph, learner-directed exploration

Same KU can be accessed via either path - progress is tracked on the KU itself.

Routes follow SKUEL's established patterns:
- Result[T] error handling throughout
- @boundary_handler() for automatic HTTP response conversion
- 201 Created for POST resource creation
- 200 OK for actions and updates
"""

from typing import Any

from fasthtml.common import Request

from core.services.protocols.facade_protocols import KuFacadeProtocol
from core.utils.error_boundary import boundary_handler
from core.utils.result_simplified import Errors, Result


def create_moc_api_routes(app: Any, rt: Any, moc_service: KuFacadeProtocol) -> list[Any]:
    """
    Create MOC API routes.

    MOC is KU-based - these routes provide MOC-specific semantics
    for organizing KUs via ORGANIZES relationships.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        moc_service: MOC service instance
    """

    # ========================================================================
    # MOC IDENTITY OPERATIONS
    # ========================================================================

    @rt("/api/moc/is-moc")
    @boundary_handler()
    async def is_moc_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """
        Check if a KU is acting as a MOC (has organized children).

        Query params:
            uid: KU UID to check

        Returns:
            {"ku_uid": str, "is_moc": bool}
        """
        result = await moc_service.is_moc(uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok({"ku_uid": uid, "is_moc": result.value})

    @rt("/api/moc/get")
    @boundary_handler()
    async def get_moc_view_route(request: Request, uid: str) -> Result[dict[str, Any]]:
        """
        Get a KU as a MOC view (with organized children hierarchy).

        Query params:
            uid: KU UID (the MOC root)
            max_depth: Maximum depth to traverse (default 3)

        Returns:
            MocView with root info and organized children tree
        """
        params = dict(request.query_params)
        max_depth = int(params.get("max_depth", 3))

        result = await moc_service.get(uid, max_depth)
        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(result.value.to_dict() if result.value else None)

    # ========================================================================
    # MOC ORGANIZATION OPERATIONS
    # ========================================================================

    @rt("/api/moc/organize", methods=["POST"])
    @boundary_handler(success_status=201)
    async def organize_route(request: Request) -> Result[dict[str, Any]]:
        """
        Organize a KU under another KU (create ORGANIZES relationship).

        This makes the parent KU act as a MOC for the child KU.

        Request body:
        {
            "parent_uid": "ku.python-reference",
            "child_uid": "ku.python-basics",
            "order": 1
        }

        Returns:
            {"success": bool, "parent_uid": str, "child_uid": str}
        """
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

        result = await moc_service.organize(parent_uid, child_uid, order)
        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {"success": result.value, "parent_uid": parent_uid, "child_uid": child_uid}
        )

    @rt("/api/moc/unorganize", methods=["POST"])
    @boundary_handler()
    async def unorganize_route(request: Request) -> Result[dict[str, Any]]:
        """
        Remove organization relationship between KUs.

        Request body:
        {
            "parent_uid": "ku.python-reference",
            "child_uid": "ku.python-basics"
        }

        Returns:
            {"success": bool}
        """
        body = await request.json()

        parent_uid = body.get("parent_uid")
        child_uid = body.get("child_uid")

        if not parent_uid or not child_uid:
            return Result.fail(
                Errors.validation(
                    message="parent_uid and child_uid are required", field="request_body"
                )
            )

        result = await moc_service.unorganize(parent_uid, child_uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok({"success": result.value})

    @rt("/api/moc/reorder", methods=["POST"])
    @boundary_handler()
    async def reorder_route(request: Request) -> Result[dict[str, Any]]:
        """
        Change the order of a child KU within its parent MOC.

        Request body:
        {
            "parent_uid": "ku.python-reference",
            "child_uid": "ku.python-basics",
            "new_order": 5
        }

        Returns:
            {"success": bool}
        """
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

        result = await moc_service.reorder(parent_uid, child_uid, new_order)
        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok({"success": result.value})

    # ========================================================================
    # MOC DISCOVERY OPERATIONS
    # ========================================================================

    @rt("/api/moc/containing")
    @boundary_handler()
    async def find_mocs_containing_route(request: Request, uid: str) -> Result[list[Any]]:
        """
        Find all MOCs (parent KUs) that organize the given KU.

        Query params:
            uid: KU UID to find parents for

        Returns:
            List of MOC KUs with order info
        """
        return await moc_service.find_mocs_containing(uid)

    @rt("/api/moc/roots")
    @boundary_handler()
    async def list_root_mocs_route(request: Request) -> Result[list[Any]]:
        """
        List KUs that act as root MOCs (organize others, not organized themselves).

        These are top-level entry points for MOC navigation.

        Query params:
            limit: Maximum number to return (default 50)

        Returns:
            List of root MOC KUs
        """
        params = dict(request.query_params)
        limit = int(params.get("limit", 50))

        return await moc_service.list_root_mocs(limit)

    @rt("/api/moc/children")
    @boundary_handler()
    async def get_children_route(request: Request, uid: str) -> Result[list[Any]]:
        """
        Get direct children of a KU organized by ORGANIZES relationship.

        Query params:
            uid: Parent KU UID

        Returns:
            List of child KUs with order
        """
        return await moc_service.get_children(uid)

    # ========================================================================
    # KU CRUD DELEGATION (for MOC creation convenience)
    # ========================================================================

    @rt("/api/moc/create-ku", methods=["POST"])
    @boundary_handler(success_status=201)
    async def create_ku_for_moc_route(request: Request) -> Result[Any]:
        """
        Create a new KU that will act as a MOC root.

        This is a convenience endpoint - you can also use /api/ku directly.
        To make the KU a MOC, use /api/moc/organize to add children.

        Request body: Same as KU creation
        {
            "title": "Python Reference",
            "description": "Comprehensive Python knowledge map",
            "domain": "learning",
            ...
        }

        Returns:
            Created KU
        """
        body = await request.json()
        return await moc_service.create_ku(**body)

    return []  # Routes registered via @rt() decorators (no objects returned)


# API Summary:
# ============
# Identity:        2 routes (is-moc, get)
# Organization:    3 routes (organize, unorganize, reorder)
# Discovery:       3 routes (containing, roots, children)
# CRUD Delegation: 1 route (create-ku)
#
# Total:           9 routes
#
# Note: This is significantly simpler than the old MOC API because
# MOC is now KU-based. Most operations delegate to KU operations
# with MOC-specific semantics layered on top.
