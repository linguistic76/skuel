"""
Pathways API Routes - Migrated to CRUDRouteFactory
===================================================

Structured pathway browsing, progress tracking, and recommendations.

This file uses:
- CRUDRouteFactory for standard CRUD routes (create, get, update, delete, list)
- Manual routes for domain-specific operations (progress, steps, recommendations)
"""

__version__ = "4.0"

import dataclasses
from datetime import datetime
from typing import Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import CRUDRouteFactory, IntelligenceRouteFactory
from core.models.curriculum.curriculum_requests import (
    LearningPathCreateRequest,
    LearningPathProgressRequest,
)
from core.models.entity_requests import EntityUpdateRequest
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.services.lp_service import LpService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.pathways.api")


def create_pathways_api_routes(
    app: Any,
    rt: Any,
    learning_service: LpService,
    user_service: Any = None,
    user_progress: Any = None,
) -> list[Any]:
    """
    Create pathways API routes using factory pattern.

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
        domain_name="pathways",
        create_schema=LearningPathCreateRequest,
        update_schema=EntityUpdateRequest,
        uid_prefix="lp",
        scope=ContentScope.SHARED,
        require_role=UserRole.ADMIN,
        user_service_getter=user_service_getter,
    )

    # Register all standard CRUD routes:
    # - POST /api/pathways (create)
    # - GET /api/pathways/{uid} (get)
    # - PUT /api/pathways/{uid} (update)
    # - DELETE /api/pathways/{uid} (delete)
    # - GET /api/pathways (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # INTELLIGENCE ROUTES (Factory-Generated)
    # ========================================================================

    intelligence_factory = IntelligenceRouteFactory(
        intelligence_service=learning_service.intelligence,
        domain_name="pathways",
        scope=ContentScope.SHARED,  # Curriculum content is shared
    )

    # Register intelligence routes:
    # - GET /api/pathways/context?uid=...&depth=2 (entity with graph context)
    # - GET /api/pathways/analytics?period_days=30 (user performance analytics)
    # - GET /api/pathways/insights?uid=... (domain-specific insights)
    intelligence_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    # Path Steps
    # ----------

    @rt("/api/pathways/steps")
    @boundary_handler()
    async def get_path_steps_route(request: Request, path_uid: str) -> Result[Any]:
        """Get all steps for a learning path."""
        return await learning_service.get_path_steps(path_uid)

    @rt("/api/pathways/current-step")
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

    @rt("/api/pathways/progress")
    @boundary_handler(success_status=201)
    async def update_progress_route(request: Request) -> Result[Any]:
        """Update progress for a learning step.

        Resolves the step's knowledge UIDs and records mastery or progress
        for each via UserService delegation to UserProgressRecorderService.
        """
        user_uid = require_authenticated_user(request)
        body = await request.json()

        progress_req = LearningPathProgressRequest.model_validate(body)

        # Resolve step to knowledge UIDs
        step_result = await learning_service.get_step(progress_req.step_uid)
        if step_result.is_error:
            return step_result

        step = step_result.value
        if not step:
            return Result.fail(
                Errors.not_found(resource="LearningStep", identifier=progress_req.step_uid)
            )

        ku_uids = list(step.primary_knowledge_uids) + list(step.supporting_knowledge_uids)
        if not ku_uids:
            return Result.fail(
                Errors.validation(
                    message="Learning step has no associated knowledge units",
                    field="step_uid",
                )
            )

        updated_ku_uids: list[str] = []
        is_completed = progress_req.completed is True
        is_mastered = is_completed and progress_req.mastery_level >= 0.8

        for ku_uid in ku_uids:
            if is_mastered:
                result = await user_service.record_knowledge_mastery(
                    user_uid=user_uid,
                    knowledge_uid=ku_uid,
                    mastery_score=progress_req.mastery_level,
                )
            else:
                result = await user_service.record_knowledge_progress(
                    user_uid=user_uid,
                    knowledge_uid=ku_uid,
                    progress=progress_req.mastery_level,
                )

            if result.is_error:
                logger.warning(f"Failed to record progress for {ku_uid}: {result.error}")
                continue

            updated_ku_uids.append(ku_uid)

        return Result.ok(
            {
                "step_uid": progress_req.step_uid,
                "updated_ku_uids": updated_ku_uids,
                "mastery_level": progress_req.mastery_level,
                "completed": is_completed,
            }
        )

    @rt("/api/pathways/progress/summary")
    @boundary_handler()
    async def get_progress_summary_route(request: Request) -> Result[Any]:
        """Get comprehensive learning progress summary for a user."""
        user_uid = require_authenticated_user(request)

        if not user_progress:
            return Result.fail(
                Errors.system(
                    message="User progress service not available",
                    operation="get_progress_summary",
                )
            )

        profile_result: Result[Any] = await user_progress.build_user_knowledge_profile(user_uid)
        if profile_result.is_error:
            return profile_result

        profile = profile_result.value

        def serialize_profile(obj: Any) -> Any:
            """Convert dataclass to JSON-safe dict."""
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return {k: serialize_profile(v) for k, v in dataclasses.asdict(obj).items()}
            if isinstance(obj, set):
                return sorted(obj)
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        return Result.ok(serialize_profile(profile))

    # Path Recommendations
    # --------------------

    @rt("/api/pathways/recommendations")
    @boundary_handler()
    async def get_path_recommendations_route(request: Request) -> Result[Any]:
        """Get recommended learning paths for a user."""
        require_authenticated_user(request)

        return Result.fail(
            Errors.system(
                message="Path recommendations not yet implemented", operation="get_recommendations"
            )
        )

    logger.info("Pathways API routes registered (CRUDRouteFactory + 6 domain routes)")
    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_pathways_api_routes"]
