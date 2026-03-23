"""
Learning Steps API - Domain-Specific Routes
=============================================

CRUD and Intelligence routes are config-driven via CRUDRouteConfig
in learning_steps_routes.py. This file contains only domain-specific
manual routes (attach/detach to path, prerequisites).
"""

__version__ = "3.0"  # Config-driven CRUD via learning_steps_routes.py

from typing import Any

from fasthtml.common import Request

from adapters.inbound.boundary import boundary_handler
from adapters.inbound.form_helpers import parse_json_body
from core.models.pathways.pathways_request import LearningStepPathRequest
from core.services.ls_service import LsService
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.routes.learning_steps.api")


def create_learning_steps_api_routes(
    app: Any, rt: Any, ls_service: LsService, user_service: Any = None
) -> list[Any]:
    """
    Create learning steps API routes using factory pattern.

    SECURITY: CRUD write operations (create, update, delete) require ADMIN role.
    Read operations (get, list) are public.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        ls_service: LsService instance (dedicated LS service)
        user_service: User service for admin role verification
    """

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    # Step-Path Relationships
    # ------------------------

    @rt("/api/learning-steps/attach-to-path", methods=["POST"])
    @boundary_handler()
    async def attach_step_to_path_route(request: Request, step_uid: str) -> Result[Any]:
        """Attach a learning step to a learning path."""
        result = await parse_json_body(request, LearningStepPathRequest)
        if result.is_error:
            return result  # type: ignore[return-value]

        return await ls_service.attach_step_to_path(
            step_uid, result.value.path_uid, result.value.sequence
        )

    @rt("/api/learning-steps/detach-from-path", methods=["POST"])
    @boundary_handler()
    async def detach_step_from_path_route(request: Request, step_uid: str) -> Result[Any]:
        """Detach a learning step from a learning path."""
        result = await parse_json_body(request, LearningStepPathRequest)
        if result.is_error:
            return result  # type: ignore[return-value]

        return await ls_service.detach_step_from_path(step_uid, result.value.path_uid)

    # Step Prerequisites
    # ------------------

    @rt("/api/learning-steps/prerequisites")
    @boundary_handler()
    async def get_step_prerequisites_route(request: Request, step_uid: str) -> Result[Any]:
        """Get prerequisites for a learning step."""

        # GRAPH-NATIVE: Query prerequisites via UnifiedRelationshipService
        # Prerequisites are stored as (ls)-[:REQUIRES_STEP]->(ls) edges
        prereq_steps_result = await ls_service.relationships.get_related_uids(
            "prerequisite_steps", step_uid
        )
        prereq_knowledge_result = await ls_service.relationships.get_related_uids(
            "prerequisite_knowledge", step_uid
        )

        prereq_steps = prereq_steps_result.value if prereq_steps_result.is_ok else []
        prereq_knowledge = prereq_knowledge_result.value if prereq_knowledge_result.is_ok else []

        return Result.ok(
            {
                "step_uid": step_uid,
                "prerequisite_steps": prereq_steps,
                "prerequisite_knowledge": prereq_knowledge,
                "has_prerequisites": len(prereq_steps) > 0 or len(prereq_knowledge) > 0,
            }
        )

    logger.info("✅ Learning Steps domain-specific routes registered (3 manual routes)")
    return []  # Routes registered via @rt() decorators (no objects returned)


__all__ = ["create_learning_steps_api_routes"]
