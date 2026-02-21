"""
LateralRouteFactory - Unified API Routes for Lateral Relationships
===================================================================

Provides HTMX-friendly endpoints for lateral relationships across all domains.

Generic endpoints work for all 9 domains (Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP):
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
    factory = LateralRouteFactory(
        domain="goals",
        lateral_service=lateral_service,  # Core LateralRelationshipService
        entity_name="Goal",
        domain_service=goals_service,     # For ownership verification
    )
    factory.register_routes(app, rt)

See: /docs/patterns/DOMAIN_LATERAL_SERVICES.md
"""

from typing import Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from core.models.relationship_names import RelationshipName
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class LateralRouteFactory:
    """Factory for creating lateral relationship API routes."""

    def __init__(
        self,
        domain: str,  # "goals", "tasks", "habits", etc.
        lateral_service: Any,  # LateralRelationshipService (core, not wrapper)
        entity_name: str,  # "Goal", "Task", "Habit", etc.
        domain_service: Any | None = None,  # For ownership (None = shared/curriculum)
    ) -> None:
        self.domain = domain
        self.lateral_service = lateral_service
        self.entity_name = entity_name
        self.domain_service = domain_service

    def register_routes(self, _app, rt) -> list[Any]:
        """Register all lateral relationship routes for this domain."""
        return [
            self._create_blocking_routes(rt),
            self._create_prerequisite_routes(rt),
            self._create_alternative_routes(rt),
            self._create_complementary_routes(rt),
            self._create_sibling_route(rt),
            self._create_delete_route(rt),
            # Phase 5: Enhanced UX routes
            self._create_chain_route(rt),
            self._create_comparison_route(rt),
            self._create_graph_route(rt),
        ]

    def _create_blocking_routes(self, rt) -> list[Any]:
        """Create BLOCKS relationship routes."""
        routes = []

        # POST /api/{domain}/{uid}/lateral/blocks - Create blocking relationship
        @rt(f"/api/{self.domain}/{{uid}}/lateral/blocks", methods=["POST"])
        @boundary_handler(success_status=201)
        async def create_blocking(
            request: Request,
            uid: str,
            target_uid: str,
            reason: str,
            severity: str = "required",
        ) -> Result[dict[str, Any]]:
            """
            Create BLOCKS relationship.

            Args:
                uid: Blocker entity UID
                target_uid: Blocked entity UID
                reason: Why blocker must complete first
                severity: "required", "recommended", or "suggested"
            """
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.create_lateral_relationship(
                source_uid=uid,
                target_uid=target_uid,
                relationship_type=RelationshipName.BLOCKS,
                metadata={
                    "reason": reason,
                    "severity": severity,
                    "domain": self.domain,
                    "created_by": user_uid,
                },
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "message": f"{self.entity_name} blocking relationship created",
                    "blocker_uid": uid,
                    "blocked_uid": target_uid,
                }
            )

        routes.append(create_blocking)

        # GET /api/{domain}/{uid}/lateral/blocking - Get entities that block this one
        @rt(f"/api/{self.domain}/{{uid}}/lateral/blocking", methods=["GET"])
        @boundary_handler()
        async def get_blocking(request: Request, uid: str) -> Result[dict[str, Any]]:
            """Get entities that block this entity."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_lateral_relationships(
                entity_uid=uid,
                relationship_types=[RelationshipName.BLOCKS],
                direction="incoming",
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "blocking": result.value,
                    "count": len(result.value),
                }
            )

        routes.append(get_blocking)

        # GET /api/{domain}/{uid}/lateral/blocked - Get entities blocked by this one
        @rt(f"/api/{self.domain}/{{uid}}/lateral/blocked", methods=["GET"])
        @boundary_handler()
        async def get_blocked(request: Request, uid: str) -> Result[dict[str, Any]]:
            """Get entities blocked by this entity."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_lateral_relationships(
                entity_uid=uid,
                relationship_types=[RelationshipName.BLOCKS],
                direction="outgoing",
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "blocked": result.value,
                    "count": len(result.value),
                }
            )

        routes.append(get_blocked)

        return routes

    def _create_prerequisite_routes(self, rt) -> list[Any]:
        """Create PREREQUISITE_FOR relationship routes."""
        routes = []

        # POST /api/{domain}/{uid}/lateral/prerequisites - Create prerequisite relationship
        @rt(f"/api/{self.domain}/{{uid}}/lateral/prerequisites", methods=["POST"])
        @boundary_handler(success_status=201)
        async def create_prerequisite(
            request: Request,
            uid: str,
            target_uid: str,
            strength: float = 0.8,
            reasoning: str | None = None,
        ) -> Result[dict[str, Any]]:
            """
            Create PREREQUISITE_FOR relationship.

            Args:
                uid: Prerequisite entity UID
                target_uid: Dependent entity UID
                strength: How essential prerequisite is (0.0-1.0)
                reasoning: Optional explanation
            """
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.create_lateral_relationship(
                source_uid=uid,
                target_uid=target_uid,
                relationship_type=RelationshipName.PREREQUISITE_FOR,
                metadata={
                    "strength": strength,
                    "reasoning": reasoning,
                    "domain": self.domain,
                    "created_by": user_uid,
                },
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "message": f"{self.entity_name} prerequisite relationship created",
                    "prerequisite_uid": uid,
                    "dependent_uid": target_uid,
                }
            )

        routes.append(create_prerequisite)

        # GET /api/{domain}/{uid}/lateral/prerequisites - Get prerequisite entities
        @rt(f"/api/{self.domain}/{{uid}}/lateral/prerequisites", methods=["GET"])
        @boundary_handler()
        async def get_prerequisites(request: Request, uid: str) -> Result[dict[str, Any]]:
            """Get entities that are prerequisites for this entity."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_lateral_relationships(
                entity_uid=uid,
                relationship_types=[
                    RelationshipName.PREREQUISITE_FOR,
                    RelationshipName.REQUIRES_PREREQUISITE,
                ],
                direction="both",
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "prerequisites": result.value,
                    "count": len(result.value),
                }
            )

        routes.append(get_prerequisites)

        return routes

    def _create_alternative_routes(self, rt) -> list[Any]:
        """Create ALTERNATIVE_TO relationship routes."""
        routes = []

        # POST /api/{domain}/{uid}/lateral/alternatives - Create alternative relationship
        @rt(f"/api/{self.domain}/{{uid}}/lateral/alternatives", methods=["POST"])
        @boundary_handler(success_status=201)
        async def create_alternative(
            request: Request,
            uid: str,
            target_uid: str,
            comparison_criteria: str,
            tradeoffs: list[str] | None = None,
        ) -> Result[dict[str, Any]]:
            """
            Create ALTERNATIVE_TO relationship.

            Args:
                uid: First entity UID
                target_uid: Alternative entity UID
                comparison_criteria: How to compare alternatives
                tradeoffs: Optional list of tradeoffs
            """
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.create_lateral_relationship(
                source_uid=uid,
                target_uid=target_uid,
                relationship_type=RelationshipName.ALTERNATIVE_TO,
                metadata={
                    "comparison_criteria": comparison_criteria,
                    "tradeoffs": tradeoffs or [],
                    "domain": self.domain,
                    "created_by": user_uid,
                },
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "message": f"{self.entity_name} alternative relationship created",
                    "entity_a_uid": uid,
                    "entity_b_uid": target_uid,
                }
            )

        routes.append(create_alternative)

        # GET /api/{domain}/{uid}/lateral/alternatives - Get alternative entities
        @rt(f"/api/{self.domain}/{{uid}}/lateral/alternatives", methods=["GET"])
        @boundary_handler()
        async def get_alternatives(request: Request, uid: str) -> Result[dict[str, Any]]:
            """Get alternative entities."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_lateral_relationships(
                entity_uid=uid,
                relationship_types=[RelationshipName.ALTERNATIVE_TO],
                direction="both",
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "alternatives": result.value,
                    "count": len(result.value),
                }
            )

        routes.append(get_alternatives)

        return routes

    def _create_complementary_routes(self, rt) -> list[Any]:
        """Create COMPLEMENTARY_TO relationship routes."""
        routes = []

        # POST /api/{domain}/{uid}/lateral/complementary - Create complementary relationship
        @rt(f"/api/{self.domain}/{{uid}}/lateral/complementary", methods=["POST"])
        @boundary_handler(success_status=201)
        async def create_complementary(
            request: Request,
            uid: str,
            target_uid: str,
            synergy_description: str,
            synergy_score: float = 0.7,
        ) -> Result[dict[str, Any]]:
            """
            Create COMPLEMENTARY_TO relationship.

            Args:
                uid: First entity UID
                target_uid: Complementary entity UID
                synergy_description: How entities complement each other
                synergy_score: Strength of synergy (0.0-1.0)
            """
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.create_lateral_relationship(
                source_uid=uid,
                target_uid=target_uid,
                relationship_type=RelationshipName.COMPLEMENTARY_TO,
                metadata={
                    "synergy_description": synergy_description,
                    "synergy_score": synergy_score,
                    "domain": self.domain,
                    "created_by": user_uid,
                },
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "message": f"{self.entity_name} complementary relationship created",
                    "entity_a_uid": uid,
                    "entity_b_uid": target_uid,
                }
            )

        routes.append(create_complementary)

        # GET /api/{domain}/{uid}/lateral/complementary - Get complementary entities
        @rt(f"/api/{self.domain}/{{uid}}/lateral/complementary", methods=["GET"])
        @boundary_handler()
        async def get_complementary(request: Request, uid: str) -> Result[dict[str, Any]]:
            """Get complementary entities."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_lateral_relationships(
                entity_uid=uid,
                relationship_types=[RelationshipName.COMPLEMENTARY_TO],
                direction="both",
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "complementary": result.value,
                    "count": len(result.value),
                }
            )

        routes.append(get_complementary)

        return routes

    def _create_sibling_route(self, rt) -> Any:
        """Create sibling relationship route (derived from hierarchy)."""

        # GET /api/{domain}/{uid}/lateral/siblings - Get sibling entities
        @rt(f"/api/{self.domain}/{{uid}}/lateral/siblings", methods=["GET"])
        @boundary_handler()
        async def get_siblings(request: Request, uid: str) -> Result[dict[str, Any]]:
            """Get sibling entities (same parent in hierarchy)."""
            user_uid = require_authenticated_user(request)

            result = await self.lateral_service.get_siblings(
                entity_uid=uid,
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "siblings": result.value,
                    "count": len(result.value),
                }
            )

        return get_siblings

    def _create_delete_route(self, rt) -> Any:
        """Create route to delete lateral relationships."""

        # DELETE /api/{domain}/{uid}/lateral/{type}/{target_uid} - Delete relationship
        @rt(
            f"/api/{self.domain}/{{uid}}/lateral/{{relationship_type}}/{{target_uid}}",
            methods=["DELETE"],
        )
        @boundary_handler()
        async def delete_lateral_relationship(
            request: Request,
            uid: str,
            relationship_type: str,
            target_uid: str,
        ) -> Result[dict[str, Any]]:
            """
            Delete lateral relationship.

            Args:
                uid: Source entity UID
                relationship_type: Type (blocks, prerequisites, alternatives, complementary)
                target_uid: Target entity UID
            """
            user_uid = require_authenticated_user(request)

            # Map route type to RelationshipName
            type_map = {
                "blocks": RelationshipName.BLOCKS,
                "prerequisites": RelationshipName.PREREQUISITE_FOR,
                "alternatives": RelationshipName.ALTERNATIVE_TO,
                "complementary": RelationshipName.COMPLEMENTARY_TO,
            }

            rel_name = type_map.get(relationship_type)
            if not rel_name:
                return Result.fail(
                    Errors.validation(f"Unsupported relationship type: {relationship_type}")
                )

            result = await self.lateral_service.delete_lateral_relationship(
                source_uid=uid,
                target_uid=target_uid,
                relationship_type=rel_name,
                user_uid=user_uid,
                domain_service=self.domain_service,
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "message": f"{self.entity_name} {relationship_type} relationship deleted",
                    "source_uid": uid,
                    "target_uid": target_uid,
                }
            )

        return delete_lateral_relationship

    # ========================================================================
    # Phase 5: Enhanced UX Routes
    # ========================================================================

    def _create_chain_route(self, rt) -> Any:
        """Create route to get blocking chain with depth levels."""

        # GET /api/{domain}/{uid}/lateral/chain - Get transitive blocking chain
        @rt(f"/api/{self.domain}/{{uid}}/lateral/chain", methods=["GET"])
        @boundary_handler()
        async def get_chain(
            request: Request,
            uid: str,
            max_depth: int = 10,
        ) -> Result[dict[str, Any]]:
            """
            Get transitive blocking chain organized by depth.

            Args:
                uid: Entity UID
                max_depth: Maximum depth to traverse (default 10)

            Returns:
                Chain data with levels, depth, and critical path
            """
            require_authenticated_user(request)

            result = await self.lateral_service.get_blocking_chain(uid, max_depth)

            if result.is_error:
                return result

            return Result.ok(result.value)

        return get_chain

    def _create_comparison_route(self, rt) -> Any:
        """Create route to get alternatives with comparison data."""

        # GET /api/{domain}/{uid}/lateral/alternatives/compare - Get alternatives with comparison
        @rt(
            f"/api/{self.domain}/{{uid}}/lateral/alternatives/compare",
            methods=["GET"],
        )
        @boundary_handler()
        async def get_comparison(
            request: Request,
            uid: str,
            fields: str | None = None,
        ) -> Result[dict[str, Any]]:
            """
            Get alternative entities with side-by-side comparison data.

            Args:
                uid: Entity UID
                fields: Comma-separated list of comparison fields (optional)

            Returns:
                List of alternatives with comparison data
            """
            require_authenticated_user(request)

            comparison_fields = fields.split(",") if fields else None

            result = await self.lateral_service.get_alternatives_with_comparison(
                uid, comparison_fields
            )

            if result.is_error:
                return result

            return Result.ok(
                {
                    "alternatives": result.value,
                    "count": len(result.value),
                }
            )

        return get_comparison

    def _create_graph_route(self, rt) -> Any:
        """Create route to get relationship graph in Vis.js format."""

        # GET /api/{domain}/{uid}/lateral/graph - Get relationship graph
        @rt(f"/api/{self.domain}/{{uid}}/lateral/graph", methods=["GET"])
        @boundary_handler()
        async def get_graph(
            request: Request,
            uid: str,
            depth: int = 2,
            types: str | None = None,
        ) -> Result[dict[str, Any]]:
            """
            Get relationship graph in Vis.js Network format.

            Args:
                uid: Center entity UID
                depth: Graph traversal depth (1-3 recommended)
                types: Comma-separated relationship types to include (optional)

            Returns:
                Vis.js Network format (nodes and edges)
            """
            require_authenticated_user(request)

            # Parse relationship types if provided
            relationship_types = None
            if types:
                try:
                    relationship_types = [RelationshipName(t.strip()) for t in types.split(",")]
                except ValueError as e:
                    return Result.fail(Errors.validation(f"Invalid relationship type: {e!s}"))

            result = await self.lateral_service.get_relationship_graph(
                uid, depth, relationship_types
            )

            if result.is_error:
                return result

            # Return Vis.js format directly (includes nodes and edges)
            return Result.ok(result.value)

        return get_graph


__all__ = ["LateralRouteFactory"]
