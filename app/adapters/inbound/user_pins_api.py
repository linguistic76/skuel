"""
User Pins API Routes
====================

Entity pinning/bookmarking functionality.

Routes:
- GET /api/user/pins - Get user's pinned entities
- POST /api/user/pins - Pin an entity
- DELETE /api/user/pins/{entity_uid} - Unpin an entity
- POST /api/user/pins/reorder - Reorder pinned entities
"""

from typing import Any

from starlette.requests import Request

from core.auth import require_authenticated_user
from core.utils.error_boundary import boundary_handler
from core.utils.result_simplified import Errors, Result


def create_user_pins_routes(_app, rt, user_relationship_service):
    """
    Create user pins API routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        user_relationship_service: UserRelationshipService instance
    """

    @rt("/api/user/pins")
    @boundary_handler()
    async def get_pinned_entities(request: Request) -> Result[list[str]]:
        """
        Get user's pinned entities.

        Returns:
        - List of pinned entity UIDs (ordered)
        """
        user_uid = require_authenticated_user(request)
        return await user_relationship_service.get_pinned_entities(user_uid)

    @rt("/api/user/pins", methods=["POST"])
    @boundary_handler()
    async def pin_entity(request: Request) -> Result[bool]:
        """
        Pin an entity.

        JSON body:
        - entity_uid: UID of entity to pin

        Returns:
        - True if pinned successfully
        """
        user_uid = require_authenticated_user(request)

        body = await request.json()
        entity_uid = body.get("entity_uid")

        if not entity_uid:
            return Result.fail(Errors.validation("entity_uid required"))

        return await user_relationship_service.pin_entity(user_uid, entity_uid)

    @rt("/api/user/pins/{entity_uid}", methods=["DELETE"])
    @boundary_handler()
    async def unpin_entity(request: Request, entity_uid: str) -> Result[bool]:
        """
        Unpin an entity.

        Path parameters:
        - entity_uid: UID of entity to unpin

        Returns:
        - True if unpinned successfully
        """
        user_uid = require_authenticated_user(request)
        return await user_relationship_service.unpin_entity(user_uid, entity_uid)

    @rt("/api/user/pins/reorder", methods=["POST"])
    @boundary_handler()
    async def reorder_pins(request: Request) -> Result[int]:
        """
        Reorder pinned entities.

        JSON body:
        - ordered_entity_uids: List of entity UIDs in desired order

        Returns:
        - Number of pins reordered
        """
        user_uid = require_authenticated_user(request)

        body = await request.json()
        ordered_uids = body.get("ordered_entity_uids", [])

        if not ordered_uids:
            return Result.fail(Errors.validation("ordered_entity_uids required"))

        return await user_relationship_service.reorder_pins(user_uid, ordered_uids)

    return [get_pinned_entities, pin_entity, unpin_entity, reorder_pins]
