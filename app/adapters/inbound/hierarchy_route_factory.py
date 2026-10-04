"""
HierarchyRouteFactory - Tree-Manipulation API Routes for Hierarchical Domains
==============================================================================

Provides HTMX-friendly endpoints for all hierarchical domains:
- POST /api/{domain}/{uid}/move - Move node to new parent
- PATCH /api/{domain}/{uid} - Update node (inline edit)
- POST /api/{domain}/bulk-delete - Delete multiple nodes

The children reads (JSON + TreeNodeList fragment) come from
``create_activity_hierarchy_api_routes`` in ``route_factories/hierarchy_api_factory.py``.

Usage:
    HierarchyRouteFactory(
        app=app,
        rt=rt,
        domain="goals",
        service=goals_service,
        entity_name="Goal",
    ).create_routes()

See: /docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md
"""

from typing import Any, Protocol

from pydantic import BaseModel

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from core.models.type_hints import UserUID
from core.models.update_contracts import RawChanges, SupportsToChanges, SupportsToIntent
from core.utils.result_simplified import Errors, Result


class HierarchicalService(Protocol):
    """Protocol for services with hierarchical methods."""

    async def get(self, uid: str) -> Result[Any]:
        """Get entity by UID."""
        ...

    async def update(self, uid: str, updates: SupportsToChanges) -> Result[Any]:
        """Update entity with a typed update value (a ``*UpdateIntent`` or ``RawChanges``)."""
        ...

    async def delete(self, uid: str) -> Result[bool]:
        """Delete entity."""
        ...

    async def verify_ownership(self, uid: str, user_uid: UserUID) -> Result[Any]:
        """Verify user owns entity."""
        ...


class HierarchyRouteFactory:
    """Factory for creating hierarchy API routes."""

    def __init__(
        self,
        app: Any,
        rt: Any,
        domain: str,  # "goals", "habits", etc.
        service: HierarchicalService,
        entity_name: str,  # "Goal", "Habit", etc.
        update_schema: type[BaseModel],  # domain *UpdateRequest (ADR-066)
        create_relationship_method: str | None = None,  # e.g., "create_subgoal_relationship"
        remove_relationship_method: str | None = None,  # e.g., "remove_subgoal_relationship"
        get_parent_method: str | None = None,  # e.g., "get_parent_goal"
    ) -> None:
        """
        Initialize hierarchy route factory.

        Args:
            app: FastHTML app instance
            rt: FastHTML route decorator
            domain: Domain name (plural, e.g., "goals")
            service: Domain service instance
            entity_name: Entity display name (singular, e.g., "Goal")
            update_schema: Domain ``*UpdateRequest`` (Pydantic) used to build the typed
                ``*UpdateIntent`` for inline title edits.
            create_relationship_method: Method name for creating parent-child relationship
            remove_relationship_method: Method name for removing parent-child relationship
            get_parent_method: Method name for getting parent entity
        """
        self.app = app
        self.rt = rt
        self.domain = domain
        self.service = service
        self.entity_name = entity_name
        # Domain *UpdateRequest so inline title edits build the typed *UpdateIntent
        # (ADR-066).
        self.update_schema = update_schema

        # Auto-detect method names if not provided
        singular = domain.rstrip("s")  # "goals" -> "goal"
        self.create_relationship_method = (
            create_relationship_method or f"create_sub{singular}_relationship"
        )
        self.remove_relationship_method = (
            remove_relationship_method or f"remove_sub{singular}_relationship"
        )
        self.get_parent_method = get_parent_method or f"get_parent_{singular}"

    def create_routes(self) -> None:
        """Register all hierarchy routes."""
        self._create_move_node_route()
        self._create_update_node_route()
        self._create_bulk_delete_route()

    async def _move_node(self, uid: str, new_parent_uid: str) -> Result[bool]:
        """
        Move a node to a new parent: remove old parent relationship, create new one.

        Handles the three-step orchestration (get old parent → remove old rel → create new rel)
        that applies uniformly across all hierarchical domains.

        Args:
            uid: UID of the node to move
            new_parent_uid: UID of the new parent node

        Returns:
            Result[bool] — success or failure with error details
        """
        get_parent_fn = getattr(self.service, self.get_parent_method, None)
        remove_rel_fn = getattr(self.service, self.remove_relationship_method, None)
        create_rel_fn = getattr(self.service, self.create_relationship_method, None)

        if get_parent_fn is None or remove_rel_fn is None or create_rel_fn is None:
            return Result.fail(
                Errors.system(f"Hierarchy methods not available on {self.domain} service")
            )

        # Remove old relationship (if exists)
        old_parent_result = await get_parent_fn(uid)
        if not old_parent_result.is_error and old_parent_result.value:
            await remove_rel_fn(old_parent_result.value.uid, uid)

        # Create new relationship (includes cycle check in service)
        create_result = await create_rel_fn(new_parent_uid, uid)
        if create_result.is_error:
            return Result.fail(create_result)

        return Result.ok(True)

    def _create_move_node_route(self) -> None:
        """POST /api/{domain}/{uid}/move - Move node to new parent."""

        @self.rt(f"/api/{self.domain}/{{uid}}/move", methods=["POST"])
        @csrf_protected
        async def move_node(request: Request, uid: str) -> Any:
            """Move node to new parent (drag-and-drop)."""
            user_uid = require_authenticated_user(request)

            body = await request.json()
            new_parent_uid = body.get("new_parent_uid")

            if not new_parent_uid:
                return {"success": False, "error": "new_parent_uid required"}, 400

            # Verify ownership of both nodes
            ownership_result = await self.service.verify_ownership(uid, user_uid)
            if ownership_result.is_error:
                return {"success": False, "error": "Not found or access denied"}, 404

            parent_ownership_result = await self.service.verify_ownership(new_parent_uid, user_uid)
            if parent_ownership_result.is_error:
                return {"success": False, "error": "Parent not found or access denied"}, 404

            move_result = await self._move_node(uid, new_parent_uid)
            if move_result.is_error:
                return {"success": False, "error": str(move_result.error)}, 400

            return {
                "success": True,
                "message": f"{self.entity_name} moved successfully",
            }

    def _create_update_node_route(self) -> None:
        """PATCH /api/{domain}/{uid} - Update node title (inline editing)."""

        @self.rt(f"/api/{self.domain}/{{uid}}", methods=["PATCH"])
        @csrf_protected
        async def update_node(request: Request, uid: str) -> Any:
            """Update node title (inline editing)."""
            user_uid = require_authenticated_user(request)

            # Parse JSON body
            body = await request.json()
            title = body.get("title")

            if not title:
                return {"success": False, "error": "title required"}, 400

            # Verify ownership
            ownership_result = await self.service.verify_ownership(uid, user_uid)
            if ownership_result.is_error:
                return {"success": False, "error": "Not found or access denied"}, 404

            # Build the typed update value (ADR-066): *UpdateRequest → *UpdateIntent.
            schema = self.update_schema(title=title)
            updates: SupportsToChanges = (
                schema.to_intent()
                if isinstance(schema, SupportsToIntent)
                else RawChanges({"title": title})
            )

            # Update
            result = await self.service.update(uid, updates)

            if result.is_error:
                return {
                    "success": False,
                    "error": str(result.error),
                }, 400

            return {
                "success": True,
                "message": f"{self.entity_name} updated",
                "uid": uid,
                "title": title,
            }

    def _create_bulk_delete_route(self) -> None:
        """POST /api/{domain}/bulk-delete - Delete multiple nodes."""

        @self.rt(f"/api/{self.domain}/bulk-delete", methods=["POST"])
        @csrf_protected
        async def bulk_delete(request: Request) -> Any:
            """Delete multiple nodes (multi-select)."""
            user_uid = require_authenticated_user(request)

            # Parse JSON body
            body = await request.json()
            uids = body.get("uids", [])

            if not uids:
                return {"success": False, "error": "uids required"}, 400

            deleted_count = 0
            errors = []

            for uid in uids:
                # Verify ownership
                ownership_result = await self.service.verify_ownership(uid, user_uid)
                if ownership_result.is_error:
                    errors.append(f"{uid}: Not found or access denied")
                    continue

                # Delete
                result = await self.service.delete(uid)
                if result.is_error:
                    errors.append(f"{uid}: {result.error}")
                else:
                    deleted_count += 1

            return {
                "success": len(errors) == 0,
                "deleted_count": deleted_count,
                "errors": errors,
            }
