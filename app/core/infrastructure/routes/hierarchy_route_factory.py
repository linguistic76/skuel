"""
HierarchyRouteFactory - Unified API Routes for Hierarchical Methods
====================================================================

Provides HTMX-friendly endpoints for all 6 domains:
- GET /api/{domain}/{uid}/children - Fetch children nodes
- POST /api/{domain}/{uid}/move - Move node to new parent
- PATCH /api/{domain}/{uid} - Update node (inline edit)
- POST /api/{domain}/bulk-delete - Delete multiple nodes

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

from fasthtml.common import Div, Request, Span

from core.auth import require_authenticated_user
from core.utils.result_simplified import Result


class HierarchicalService(Protocol):
    """Protocol for services with hierarchical methods."""

    async def get(self, uid: str) -> Result[Any]:
        """Get entity by UID."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Any]:
        """Update entity."""
        ...

    async def delete(self, uid: str) -> Result[bool]:
        """Delete entity."""
        ...

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[Any]:
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
        get_children_method: str | None = None,  # e.g., "get_subgoals"
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
            get_children_method: Method name for fetching children (auto-detected if None)
            create_relationship_method: Method name for creating parent-child relationship
            remove_relationship_method: Method name for removing parent-child relationship
            get_parent_method: Method name for getting parent entity
        """
        self.app = app
        self.rt = rt
        self.domain = domain
        self.service = service
        self.entity_name = entity_name

        # Auto-detect method names if not provided
        singular = domain.rstrip("s")  # "goals" -> "goal"
        self.get_children_method = get_children_method or f"get_sub{domain}"
        self.create_relationship_method = (
            create_relationship_method or f"create_sub{singular}_relationship"
        )
        self.remove_relationship_method = (
            remove_relationship_method or f"remove_sub{singular}_relationship"
        )
        self.get_parent_method = get_parent_method or f"get_parent_{singular}"

    def create_routes(self) -> list[Any]:
        """Create all hierarchy routes."""
        return [
            self._create_get_children_route(),
            self._create_move_node_route(),
            self._create_update_node_route(),
            self._create_bulk_delete_route(),
        ]

    def _create_get_children_route(self) -> Any:
        """GET /api/{domain}/{uid}/children - Fetch children for HTMX lazy loading."""

        @self.rt(f"/api/{self.domain}/{{uid}}/children", methods=["GET"])
        async def get_children(request: Request, uid: str, parent_depth: int = 0) -> Any:
            """
            Fetch children for HTMX lazy loading.

            Args:
                request: FastHTML request
                uid: Parent node UID
                parent_depth: Depth of parent node (children will be parent_depth + 1)
                              -1 for root loading (children will be depth 0)
            """
            user_uid = require_authenticated_user(request)

            # Verify ownership
            ownership_result = await self.service.verify_ownership(uid, user_uid)
            if ownership_result.is_error:
                return Div(
                    Span("Not found or access denied", cls="text-error text-sm"),
                    cls="px-2 py-1",
                )

            # Get children
            get_children_fn = getattr(self.service, self.get_children_method, None)
            if not get_children_fn:
                return Div(
                    Span(f"Method {self.get_children_method} not found", cls="text-error text-sm"),
                    cls="px-2 py-1",
                )

            result = await get_children_fn(uid, depth=1)

            if result.is_error:
                return Div(
                    Span(f"Error loading children: {result.error}", cls="text-error text-sm"),
                    cls="px-2 py-1",
                )

            children = result.value

            # Convert to dicts for rendering
            children_data = []
            for child in children:
                # Check if child has children
                child_children_result = await get_children_fn(child.uid, depth=1)
                has_children = (
                    not child_children_result.is_error and len(child_children_result.value) > 0
                )

                children_data.append(
                    {
                        "uid": child.uid,
                        "title": child.title,
                        "has_children": has_children,
                    }
                )

            # Render using TreeNodeList component
            from ui.patterns.tree_view import TreeNodeList

            return TreeNodeList(
                nodes=children_data,
                entity_type=self.domain.rstrip("s"),  # "goals" -> "goal"
                children_endpoint=f"/api/{self.domain}/{{uid}}/children",
                parent_depth=parent_depth,  # Use actual parent depth from query parameter
            )

        return get_children

    def _create_move_node_route(self) -> Any:
        """POST /api/{domain}/{uid}/move - Move node to new parent."""

        @self.rt(f"/api/{self.domain}/{{uid}}/move", methods=["POST"])
        async def move_node(request: Request, uid: str) -> Any:
            """Move node to new parent (drag-and-drop)."""
            user_uid = require_authenticated_user(request)

            # Parse JSON body
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

            # Get old parent (if any)
            get_parent_fn = getattr(self.service, self.get_parent_method, None)
            remove_rel_fn = getattr(self.service, self.remove_relationship_method, None)
            create_rel_fn = getattr(self.service, self.create_relationship_method, None)

            if not all([get_parent_fn, remove_rel_fn, create_rel_fn]):
                return {"success": False, "error": "Hierarchy methods not available"}, 500

            # Remove old relationship (if exists)
            old_parent_result = await get_parent_fn(uid)
            if not old_parent_result.is_error and old_parent_result.value:
                await remove_rel_fn(old_parent_result.value.uid, uid)

            # Create new relationship
            create_result = await create_rel_fn(new_parent_uid, uid)

            if create_result.is_error:
                return {
                    "success": False,
                    "error": str(create_result.error),
                }, 400

            return {
                "success": True,
                "message": f"{self.entity_name} moved successfully",
            }

        return move_node

    def _create_update_node_route(self) -> Any:
        """PATCH /api/{domain}/{uid} - Update node title (inline editing)."""

        @self.rt(f"/api/{self.domain}/{{uid}}", methods=["PATCH"])
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

            # Update
            result = await self.service.update(uid, {"title": title})

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

        return update_node

    def _create_bulk_delete_route(self) -> Any:
        """POST /api/{domain}/bulk-delete - Delete multiple nodes."""

        @self.rt(f"/api/{self.domain}/bulk-delete", methods=["POST"])
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

        return bulk_delete
