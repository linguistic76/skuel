"""
Learning API Routes - Migrated to CRUDRouteFactory
===================================================

Migrated to use CRUDRouteFactory for standard CRUD operations.

Before: 235 lines with manual CRUD routes
After: ~150 lines with CRUDRouteFactory + domain-specific routes

This file uses:
- CRUDRouteFactory for standard CRUD routes (create, get, update, delete, list)
- Manual routes for domain-specific operations (progress, steps, recommendations)
"""

__version__ = "3.0"

from typing import Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import CRUDRouteFactory, IntelligenceRouteFactory
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.models.ku.ku_request import KuLearningPathCreateRequest, KuUpdateRequest
from core.ports.facade_protocols import LpFacadeProtocol
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.learning.api")


def create_learning_api_routes(
    app: Any, rt: Any, learning_service: LpFacadeProtocol, user_service: Any = None
) -> list[Any]:
    """
    Create learning API routes using factory pattern.

    SECURITY: CRUD write operations (create, update, delete) require ADMIN role.
    Read operations (get, list) are public.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        learning_service: LpService instance
        user_service: User service for admin role verification
    """

    def user_service_getter():
        return user_service

    # ========================================================================
    # STANDARD CRUD ROUTES (Factory-Generated, Admin-Gated Writes)
    # ========================================================================

    crud_factory = CRUDRouteFactory(
        service=learning_service,
        domain_name="learning",
        create_schema=KuLearningPathCreateRequest,
        update_schema=KuUpdateRequest,
        uid_prefix="lp",
        scope=ContentScope.SHARED,
        require_role=UserRole.ADMIN,
        user_service_getter=user_service_getter,
    )

    # Register all standard CRUD routes:
    # - POST   /api/learning           (create)
    # - GET    /api/learning/{uid}     (get)
    # - PUT    /api/learning/{uid}     (update)
    # - DELETE /api/learning/{uid}     (delete)
    # - GET    /api/learning           (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # INTELLIGENCE ROUTES (Factory-Generated)
    # ========================================================================

    intelligence_factory = IntelligenceRouteFactory(
        intelligence_service=learning_service.intelligence,
        domain_name="learning",
        scope=ContentScope.SHARED,  # Curriculum content is shared
    )

    # Register intelligence routes:
    # - GET /api/learning/context?uid=...&depth=2     (entity with graph context)
    # - GET /api/learning/analytics?period_days=30   (user performance analytics)
    # - GET /api/learning/insights?uid=...           (domain-specific insights)
    intelligence_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    # Path Steps
    # ----------

    @rt("/api/learning/steps")
    @boundary_handler()
    async def get_path_steps_route(request: Request, path_uid: str) -> Result[Any]:
        """Get all steps for a learning path."""
        return await learning_service.get_path_steps(path_uid)

    @rt("/api/learning/current-step")
    @boundary_handler()
    async def get_current_step_route(request: Request, path_uid: str) -> Result[Any]:
        """Get the current (first incomplete) step in a learning path."""

        result = await learning_service.get_current_step(path_uid)
        if result.is_error:
            return result

        current_step = result.value
        if not current_step:
            return Result.fail(
                Errors.not_found(resource="Ls", identifier=f"incomplete step in path {path_uid}")
            )

        return Result.ok(current_step)

    # Progress Tracking
    # -----------------

    @rt("/api/learning/progress")
    @boundary_handler(success_status=201)
    async def update_progress_route(request: Request) -> Result[Any]:
        """Update progress for a learning step."""
        body = await request.json()

        from core.models.ku.ku_request import KuLearningPathProgressRequest

        KuLearningPathProgressRequest.model_validate(body)

        return Result.fail(
            Errors.system(
                message="Progress tracking not yet implemented - requires progress service integration",
                operation="update_progress",
            )
        )

    @rt("/api/learning/progress/summary")
    @boundary_handler()
    async def get_progress_summary_route(request: Request) -> Result[Any]:
        """Get comprehensive learning progress summary for a user."""
        require_authenticated_user(request)

        return Result.fail(
            Errors.system(
                message="Progress summary not yet implemented - requires progress service integration",
                operation="get_progress_summary",
            )
        )

    # Path Recommendations
    # --------------------

    @rt("/api/learning/recommendations")
    @boundary_handler()
    async def get_path_recommendations_route(request: Request) -> Result[Any]:
        """Get recommended learning paths for a user."""
        require_authenticated_user(request)

        return Result.fail(
            Errors.system(
                message="Path recommendations not yet implemented", operation="get_recommendations"
            )
        )

    logger.info("✅ Learning API routes registered (CRUDRouteFactory + 6 domain routes)")
    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_learning_api_routes"]


# Migration Statistics (Phase 1 Complete):
# ========================================
# Before (manual CRUD): 235 lines
# After (CRUDRouteFactory): ~110 lines
# Reduction: 125 lines (53% reduction)
#
# Routes Generated by CRUDRouteFactory:
# - POST   /api/learning           (create)
# - GET    /api/learning/{uid}     (get)
# - PUT    /api/learning/{uid}     (update)
# - DELETE /api/learning/{uid}     (delete)
# - GET    /api/learning           (list with pagination)
#
# Domain-Specific Routes (Manual):
# - GET    /api/learning/{path_uid}/steps               (get steps)
# - GET    /api/learning/{path_uid}/current-step        (get current step)
# - POST   /api/learning/progress                       (update progress)
# - GET    /api/learning/progress/summary               (get progress summary)
# - GET    /api/learning/recommendations                (get recommendations)
#
# Next Steps:
# - Task 4: Add LS CRUD operations to LpService
# - Task 5: Create learning_steps_api.py with CRUDRouteFactory for standalone LS management
