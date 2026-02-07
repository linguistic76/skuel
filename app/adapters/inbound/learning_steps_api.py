"""
Learning Steps API - CRUDRouteFactory Implementation
====================================================

Provides standalone CRUD operations for Ls entities.

This file uses:
- CRUDRouteFactory for standard CRUD routes (create, get, update, delete, list)
- LsService directly (no adapter needed - implements CRUD protocol)
- Manual routes for domain-specific operations (attach to path, prerequisites)

Architecture:
- LsService is THE single owner for all learning step operations
- Direct service usage (no wrapper/adapter pattern)
"""

__version__ = "2.0"  # Updated to use LsService directly

from typing import Any

from fasthtml.common import Request

from core.infrastructure.routes import CRUDRouteFactory, IntelligenceRouteFactory
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.models.ls.ls_request import LearningStepCreateRequest, LearningStepUpdateRequest
from core.services.protocols.facade_protocols import LsFacadeProtocol
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.routes.learning_steps.api")


def create_learning_steps_api_routes(
    app: Any, rt: Any, ls_service: LsFacadeProtocol, user_service: Any = None
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

    def user_service_getter():
        return user_service

    # ========================================================================
    # STANDARD CRUD ROUTES (Factory-Generated, Admin-Gated Writes)
    # ========================================================================

    crud_factory = CRUDRouteFactory(
        service=ls_service,
        domain_name="learning-steps",
        create_schema=LearningStepCreateRequest,
        update_schema=LearningStepUpdateRequest,
        uid_prefix="ls",
        scope=ContentScope.SHARED,
        require_role=UserRole.ADMIN,
        user_service_getter=user_service_getter,
    )

    # Register all standard CRUD routes:
    # - POST   /api/learning-steps           (create)
    # - GET    /api/learning-steps/{uid}     (get)
    # - PUT    /api/learning-steps/{uid}     (update)
    # - DELETE /api/learning-steps/{uid}     (delete)
    # - GET    /api/learning-steps           (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # INTELLIGENCE ROUTES (Factory-Generated)
    # ========================================================================

    intelligence_factory = IntelligenceRouteFactory(
        intelligence_service=ls_service.intelligence,
        domain_name="learning-steps",
        scope=ContentScope.SHARED,  # Curriculum content is shared
    )

    # Register intelligence routes:
    # - GET /api/learning-steps/context?uid=...&depth=2     (entity with graph context)
    # - GET /api/learning-steps/analytics?period_days=30   (user performance analytics)
    # - GET /api/learning-steps/insights?uid=...           (domain-specific insights)
    intelligence_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    # Step-Path Relationships
    # ------------------------

    @rt("/api/learning-steps/attach-to-path", methods=["POST"])
    @boundary_handler()
    async def attach_step_to_path_route(request: Request, step_uid: str) -> Result[Any]:
        """Attach a learning step to a learning path."""
        body = await request.json()
        path_uid = body.get("path_uid")
        sequence = body.get("sequence")  # Optional

        if not path_uid:
            from core.utils.result_simplified import Errors

            return Result.fail(Errors.validation(message="path_uid is required", field="path_uid"))

        # Call LsService.attach_step_to_path (exists in relationship sub-service)
        return await ls_service.attach_step_to_path(step_uid, path_uid, sequence)

    @rt("/api/learning-steps/detach-from-path", methods=["POST"])
    @boundary_handler()
    async def detach_step_from_path_route(request: Request, step_uid: str) -> Result[Any]:
        """Detach a learning step from a learning path."""
        body = await request.json()
        path_uid = body.get("path_uid")

        if not path_uid:
            from core.utils.result_simplified import Errors

            return Result.fail(Errors.validation(message="path_uid is required", field="path_uid"))

        # Call LsService.detach_step_from_path (exists in relationship sub-service)
        return await ls_service.detach_step_from_path(step_uid, path_uid)

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

    logger.info("✅ Learning Steps API routes registered (CRUDRouteFactory + 3 domain routes)")
    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_learning_steps_api_routes"]


# Implementation Statistics:
# ==========================
# - 5 CRUD routes (via CRUDRouteFactory)
# - 3 domain-specific routes (manual)
# - Total: 8 routes
#
# Routes Generated by CRUDRouteFactory:
# - POST   /api/learning-steps           (create)
# - GET    /api/learning-steps/{uid}     (get)
# - PUT    /api/learning-steps/{uid}     (update)
# - DELETE /api/learning-steps/{uid}     (delete)
# - GET    /api/learning-steps           (list with pagination)
#
# Domain-Specific Routes (Manual):
# - POST   /api/learning-steps/{step_uid}/attach-to-path      (attach to path)
# - POST   /api/learning-steps/{step_uid}/detach-from-path    (detach from path)
# - GET    /api/learning-steps/{step_uid}/prerequisites       (get prerequisites)
