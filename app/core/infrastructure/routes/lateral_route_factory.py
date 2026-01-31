"""
LateralRouteFactory - Unified API Routes for Lateral Relationships
===================================================================

Provides HTMX-friendly endpoints for lateral relationships across all domains.

Generic endpoints work for all 8 domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP):
- POST /api/{domain}/{uid}/lateral/blocks - Create blocking relationship
- GET /api/{domain}/{uid}/lateral/blocking - Get relationships that block this entity
- GET /api/{domain}/{uid}/lateral/blocked - Get relationships blocked by this entity
- POST /api/{domain}/{uid}/lateral/prerequisites - Create prerequisite relationship
- GET /api/{domain}/{uid}/lateral/prerequisites - Get prerequisite relationships
- POST /api/{domain}/{uid}/lateral/alternatives - Create alternative relationship
- GET /api/{domain}/{uid}/lateral/alternatives - Get alternative relationships
- POST /api/{domain}/{uid}/lateral/complementary - Create complementary relationship
- GET /api/{domain}/{uid}/lateral/complementary - Get complementary relationships
- GET /api/{domain}/{uid}/lateral/siblings - Get sibling relationships (derived from hierarchy)
- DELETE /api/{domain}/{uid}/lateral/{type}/{target_uid} - Delete relationship

Domain-specific routes can be added separately for unique relationship types:
- Habits: POST /api/habits/{uid}/lateral/stacks - Create habit stacking
- Habits: GET /api/habits/{uid}/lateral/stack - Get habit stack
- etc.

Usage:
    LateralRouteFactory(
        app=app,
        rt=rt,
        domain="goals",
        lateral_service=goals_lateral_service,
        entity_name="Goal",
    ).create_routes()

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from fasthtml.common import Request

from core.auth import require_authenticated_user
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


class LateralRouteFactory:
    """Factory for creating lateral relationship API routes."""

    def __init__(
        self,
        app: Any,
        rt: Any,
        domain: str,  # "goals", "tasks", "habits", etc.
        lateral_service: Any,  # Domain lateral service (e.g., GoalsLateralService)
        entity_name: str,  # "Goal", "Task", "Habit", etc.
    ):
        self.app = app
        self.rt = rt
        self.domain = domain
        self.lateral_service = lateral_service
        self.entity_name = entity_name

    def create_routes(self) -> list[Any]:
        """Create all lateral relationship routes for this domain."""
        return [
            self._create_blocking_routes(),
            self._create_prerequisite_routes(),
            self._create_alternative_routes(),
            self._create_complementary_routes(),
            self._create_sibling_route(),
            self._create_delete_route(),
            # Phase 5: Enhanced UX routes
            self._create_chain_route(),
            self._create_comparison_route(),
            self._create_graph_route(),
        ]

    def _create_blocking_routes(self) -> list[Any]:
        """Create BLOCKS relationship routes."""
        routes = []

        # POST /api/{domain}/{uid}/lateral/blocks - Create blocking relationship
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/blocks", methods=["POST"])
        async def create_blocking(
            request: Request,
            uid: str,
            target_uid: str,
            reason: str,
            severity: str = "required",
        ) -> dict[str, Any]:
            """
            Create BLOCKS relationship.

            Args:
                uid: Blocker entity UID
                target_uid: Blocked entity UID
                reason: Why blocker must complete first
                severity: "required", "recommended", or "suggested"
            """
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.create_blocking_relationship(
                blocker_uid=uid,
                blocked_uid=target_uid,
                reason=reason,
                severity=severity,
                user_uid=user_uid,
            )

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "message": f"{self.entity_name} blocking relationship created",
                "blocker_uid": uid,
                "blocked_uid": target_uid,
            }

        routes.append(create_blocking)

        # GET /api/{domain}/{uid}/lateral/blocking - Get entities that block this one
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/blocking", methods=["GET"])
        async def get_blocking(request: Request, uid: str) -> dict[str, Any]:
            """Get entities that block this entity."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_blocking_goals(uid, user_uid=user_uid)

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "blocking": result.value,
                "count": len(result.value),
            }

        routes.append(get_blocking)

        # GET /api/{domain}/{uid}/lateral/blocked - Get entities blocked by this one
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/blocked", methods=["GET"])
        async def get_blocked(request: Request, uid: str) -> dict[str, Any]:
            """Get entities blocked by this entity."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_blocked_goals(uid, user_uid=user_uid)

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "blocked": result.value,
                "count": len(result.value),
            }

        routes.append(get_blocked)

        return routes

    def _create_prerequisite_routes(self) -> list[Any]:
        """Create PREREQUISITE_FOR relationship routes."""
        routes = []

        # POST /api/{domain}/{uid}/lateral/prerequisites - Create prerequisite relationship
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/prerequisites", methods=["POST"])
        async def create_prerequisite(
            request: Request,
            uid: str,
            target_uid: str,
            strength: float = 0.8,
            reasoning: str | None = None,
        ) -> dict[str, Any]:
            """
            Create PREREQUISITE_FOR relationship.

            Args:
                uid: Prerequisite entity UID
                target_uid: Dependent entity UID
                strength: How essential prerequisite is (0.0-1.0)
                reasoning: Optional explanation
            """
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.create_prerequisite_relationship(
                prerequisite_uid=uid,
                dependent_uid=target_uid,
                strength=strength,
                reasoning=reasoning,
                user_uid=user_uid,
            )

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "message": f"{self.entity_name} prerequisite relationship created",
                "prerequisite_uid": uid,
                "dependent_uid": target_uid,
            }

        routes.append(create_prerequisite)

        # GET /api/{domain}/{uid}/lateral/prerequisites - Get prerequisite entities
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/prerequisites", methods=["GET"])
        async def get_prerequisites(request: Request, uid: str) -> dict[str, Any]:
            """Get entities that are prerequisites for this entity."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_prerequisites(uid, user_uid=user_uid)

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "prerequisites": result.value,
                "count": len(result.value),
            }

        routes.append(get_prerequisites)

        return routes

    def _create_alternative_routes(self) -> list[Any]:
        """Create ALTERNATIVE_TO relationship routes."""
        routes = []

        # POST /api/{domain}/{uid}/lateral/alternatives - Create alternative relationship
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/alternatives", methods=["POST"])
        async def create_alternative(
            request: Request,
            uid: str,
            target_uid: str,
            comparison_criteria: str,
            tradeoffs: list[str] | None = None,
        ) -> dict[str, Any]:
            """
            Create ALTERNATIVE_TO relationship.

            Args:
                uid: First entity UID
                target_uid: Alternative entity UID
                comparison_criteria: How to compare alternatives
                tradeoffs: Optional list of tradeoffs
            """
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.create_alternative_relationship(
                goal_a_uid=uid,
                goal_b_uid=target_uid,
                comparison_criteria=comparison_criteria,
                tradeoffs=tradeoffs or [],
                user_uid=user_uid,
            )

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "message": f"{self.entity_name} alternative relationship created",
                "entity_a_uid": uid,
                "entity_b_uid": target_uid,
            }

        routes.append(create_alternative)

        # GET /api/{domain}/{uid}/lateral/alternatives - Get alternative entities
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/alternatives", methods=["GET"])
        async def get_alternatives(request: Request, uid: str) -> dict[str, Any]:
            """Get alternative entities."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_alternative_goals(uid, user_uid=user_uid)

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "alternatives": result.value,
                "count": len(result.value),
            }

        routes.append(get_alternatives)

        return routes

    def _create_complementary_routes(self) -> list[Any]:
        """Create COMPLEMENTARY_TO relationship routes."""
        routes = []

        # POST /api/{domain}/{uid}/lateral/complementary - Create complementary relationship
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/complementary", methods=["POST"])
        async def create_complementary(
            request: Request,
            uid: str,
            target_uid: str,
            synergy_description: str,
            synergy_score: float = 0.7,
        ) -> dict[str, Any]:
            """
            Create COMPLEMENTARY_TO relationship.

            Args:
                uid: First entity UID
                target_uid: Complementary entity UID
                synergy_description: How entities complement each other
                synergy_score: Strength of synergy (0.0-1.0)
            """
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.create_complementary_relationship(
                goal_a_uid=uid,
                goal_b_uid=target_uid,
                synergy_description=synergy_description,
                synergy_score=synergy_score,
                user_uid=user_uid,
            )

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "message": f"{self.entity_name} complementary relationship created",
                "entity_a_uid": uid,
                "entity_b_uid": target_uid,
            }

        routes.append(create_complementary)

        # GET /api/{domain}/{uid}/lateral/complementary - Get complementary entities
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/complementary", methods=["GET"])
        async def get_complementary(request: Request, uid: str) -> dict[str, Any]:
            """Get complementary entities."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_complementary_goals(uid, user_uid=user_uid)

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "complementary": result.value,
                "count": len(result.value),
            }

        routes.append(get_complementary)

        return routes

    def _create_sibling_route(self) -> Any:
        """Create sibling relationship route (derived from hierarchy)."""

        # GET /api/{domain}/{uid}/lateral/siblings - Get sibling entities
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/siblings", methods=["GET"])
        async def get_siblings(request: Request, uid: str) -> dict[str, Any]:
            """Get sibling entities (same parent in hierarchy)."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_sibling_goals(uid, user_uid=user_uid)

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "siblings": result.value,
                "count": len(result.value),
            }

        return get_siblings

    def _create_delete_route(self) -> Any:
        """Create route to delete lateral relationships."""

        # DELETE /api/{domain}/{uid}/lateral/{type}/{target_uid} - Delete relationship
        @self.rt(
            f"/api/{self.domain}/{{uid}}/lateral/{{relationship_type}}/{{target_uid}}",
            methods=["DELETE"],
        )
        async def delete_lateral_relationship(
            request: Request,
            uid: str,
            relationship_type: str,
            target_uid: str,
        ) -> dict[str, Any]:
            """
            Delete lateral relationship.

            Args:
                uid: Source entity UID
                relationship_type: Type (blocks, prerequisites, alternatives, complementary)
                target_uid: Target entity UID
            """
            user_uid = require_authenticated_user(request)

            # Map route type to service method
            method_map = {
                "blocks": "delete_blocking_relationship",
                "prerequisites": "delete_prerequisite_relationship",
                # Note: alternatives and complementary don't have delete methods in all services
                # They can be deleted via core lateral service
            }

            method_name = method_map.get(relationship_type)
            if not method_name:
                return {
                    "success": False,
                    "error": f"Unsupported relationship type: {relationship_type}",
                }, 400

            # Check if service has the method
            if not hasattr(self.lateral_service, method_name):
                return {
                    "success": False,
                    "error": f"Delete method not available for {relationship_type}",
                }, 400

            delete_method = getattr(self.lateral_service, method_name)
            result = await delete_method(
                blocker_uid=uid if relationship_type == "blocks" else uid,
                blocked_uid=target_uid if relationship_type == "blocks" else target_uid,
                user_uid=user_uid,
            )

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "message": f"{self.entity_name} {relationship_type} relationship deleted",
                "source_uid": uid,
                "target_uid": target_uid,
            }

        return delete_lateral_relationship

    # ========================================================================
    # Phase 5: Enhanced UX Routes
    # ========================================================================

    def _create_chain_route(self) -> Any:
        """Create route to get blocking chain with depth levels."""

        # GET /api/{domain}/{uid}/lateral/chain - Get transitive blocking chain
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/chain", methods=["GET"])
        async def get_chain(
            request: Request,
            uid: str,
            max_depth: int = 10,
        ) -> dict[str, Any]:
            """
            Get transitive blocking chain organized by depth.

            Args:
                uid: Entity UID
                max_depth: Maximum depth to traverse (default 10)

            Returns:
                Chain data with levels, depth, and critical path
            """
            user_uid = require_authenticated_user(request)

            # Access the core lateral service through the domain lateral service
            result = await self.lateral_service.lateral_service.get_blocking_chain(
                uid, max_depth
            )

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {"success": True, **result.value}

        return get_chain

    def _create_comparison_route(self) -> Any:
        """Create route to get alternatives with comparison data."""

        # GET /api/{domain}/{uid}/lateral/alternatives/compare - Get alternatives with comparison
        @self.rt(
            f"/api/{self.domain}/{{uid}}/lateral/alternatives/compare",
            methods=["GET"],
        )
        async def get_comparison(
            request: Request,
            uid: str,
            fields: str | None = None,
        ) -> dict[str, Any]:
            """
            Get alternative entities with side-by-side comparison data.

            Args:
                uid: Entity UID
                fields: Comma-separated list of comparison fields (optional)

            Returns:
                List of alternatives with comparison data
            """
            user_uid = require_authenticated_user(request)

            comparison_fields = fields.split(",") if fields else None

            result = await self.lateral_service.lateral_service.get_alternatives_with_comparison(
                uid, comparison_fields
            )

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            return {
                "success": True,
                "alternatives": result.value,
                "count": len(result.value),
            }

        return get_comparison

    def _create_graph_route(self) -> Any:
        """Create route to get relationship graph in Vis.js format."""

        # GET /api/{domain}/{uid}/lateral/graph - Get relationship graph
        @self.rt(f"/api/{self.domain}/{{uid}}/lateral/graph", methods=["GET"])
        async def get_graph(
            request: Request,
            uid: str,
            depth: int = 2,
            types: str | None = None,
        ) -> dict[str, Any]:
            """
            Get relationship graph in Vis.js Network format.

            Args:
                uid: Center entity UID
                depth: Graph traversal depth (1-3 recommended)
                types: Comma-separated relationship types to include (optional)

            Returns:
                Vis.js Network format (nodes and edges)
            """
            user_uid = require_authenticated_user(request)

            # Parse relationship types if provided
            from core.models.enums.lateral_relationship_types import (
                LateralRelationType,
            )

            relationship_types = None
            if types:
                try:
                    relationship_types = [
                        LateralRelationType(t.strip()) for t in types.split(",")
                    ]
                except ValueError as e:
                    return {
                        "success": False,
                        "error": f"Invalid relationship type: {str(e)}",
                    }, 400

            result = await self.lateral_service.lateral_service.get_relationship_graph(
                uid, depth, relationship_types
            )

            if result.is_error:
                return {"success": False, "error": str(result.error)}, 400

            # Return Vis.js format directly (includes nodes and edges)
            return result.value

        return get_graph


__all__ = ["LateralRouteFactory"]
