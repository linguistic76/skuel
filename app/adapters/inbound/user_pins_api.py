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

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.form_helpers import parse_json_body
from core.models.user_pins_request import PinEntityRequest, ReorderPinsRequest
from core.services.user_relationship_service import UserRelationshipService
from core.utils.result_simplified import Errors, Result


def create_user_pins_routes(
    _app: Any, rt: Any, user_relationship_service: UserRelationshipService
) -> list[Any]:
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
    async def pin_entity(request: Request):
        """
        Pin an entity.

        JSON body or form data:
        - entity_uid: UID of entity to pin

        Returns:
        - Updated pin button HTML (for HTMX) or JSON (for API)
        """
        from adapters.inbound.form_helpers import parse_form_body

        user_uid = require_authenticated_user(request)

        # Try JSON first, then form data (HTMX sends form data)
        json_result = await parse_json_body(request, PinEntityRequest)
        if json_result.is_error:
            form_result = await parse_form_body(request, PinEntityRequest)
            if form_result.is_error:
                return Result.fail(Errors.validation("entity_uid required"))
            entity_uid = form_result.value.entity_uid
        else:
            entity_uid = json_result.value.entity_uid

        result = await user_relationship_service.pin_entity(user_uid, entity_uid)

        if result.is_error:
            return result

        # Return updated pin button for HTMX
        from ui.patterns.pin_button import PinButton

        return PinButton(entity_uid=entity_uid, is_pinned=True)

    @rt("/api/user/pins/{entity_uid}", methods=["DELETE"])
    async def unpin_entity(request: Request, entity_uid: str):
        """
        Unpin an entity.

        Path parameters:
        - entity_uid: UID of entity to unpin

        Returns:
        - Updated pin button HTML (for HTMX) or JSON (for API)
        """
        user_uid = require_authenticated_user(request)
        result = await user_relationship_service.unpin_entity(user_uid, entity_uid)

        if result.is_error:
            return result

        # Return updated pin button for HTMX
        from ui.patterns.pin_button import PinButton

        return PinButton(entity_uid=entity_uid, is_pinned=False)

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

        parsed = await parse_json_body(request, ReorderPinsRequest)
        if parsed.is_error:
            return parsed  # type: ignore[return-value]

        return await user_relationship_service.reorder_pins(
            user_uid, parsed.value.ordered_entity_uids
        )

    return [get_pinned_entities, pin_entity, unpin_entity, reorder_pins]
