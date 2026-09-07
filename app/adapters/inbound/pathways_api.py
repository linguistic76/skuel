"""
Pathways API - Domain-Specific Routes
=======================================

CRUD and Intelligence routes are config-driven via CRUDRouteConfig
in pathways_routes.py. This file contains only domain-specific manual routes
(progress tracking, steps, recommendations).
"""

__version__ = "4.0"

from typing import Any

from fasthtml.common import Request
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.result_helpers import require_found
from core.models.pathways.path_step import PathStep
from core.models.pathways.pathways_request import (
    LearningPathProgressRequest,
)
from core.services.lp_service import LpService
from core.services.user_progress_service import UserKnowledgeProfile
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

    # Fail-fast: user_progress is always wired at compose (api_related_services
    # maps it from services.user_progress) — a missing one is a wiring defect.
    assert user_progress is not None, "UserProgressService must be wired before pathways API routes"

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    # Path Steps
    # ----------

    @rt("/api/pathways/steps")
    @boundary_handler()
    async def get_path_steps_route(request: Request, path_uid: str) -> Result[list[PathStep]]:
        """Get all steps for a learning path."""
        return await learning_service.get_path_steps(path_uid)

    @rt("/api/pathways/current-step")
    @boundary_handler()
    async def get_current_step_route(request: Request, path_uid: str) -> Result[PathStep]:
        """Get the current (first incomplete) step in a learning path."""

        return require_found(
            await learning_service.get_current_step(path_uid),
            "Ls",
            f"incomplete step in path {path_uid}",
        )

    # Progress Tracking
    # -----------------

    @rt("/api/pathways/progress")
    @csrf_protected
    @boundary_handler(success_status=201)
    async def update_progress_route(request: Request) -> Result[dict[str, Any]]:
        """Update progress for a path step.

        Resolves the step's knowledge UIDs and records mastery or progress
        for each via UserService delegation to UserProgressRecorderService.
        """
        user_uid = require_authenticated_user(request)

        # A rejected body is bad input, not a server fault: without the helper
        # the raw ValidationError reaches `boundary_handler` as a 500.
        parsed = await parse_json_body(request, LearningPathProgressRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        progress_req = parsed.value

        # Resolve step to knowledge UIDs
        step_found = require_found(
            await learning_service.get_step(progress_req.step_uid),
            "PathStep",
            progress_req.step_uid,
        )
        if step_found.is_error:
            return Result.fail(step_found)

        step = step_found.value

        ku_uids = list(step.knowledge_uids)
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
    async def get_progress_summary_route(request: Request) -> Result[dict[str, Any]]:
        """Get comprehensive learning progress summary for a user."""
        user_uid = require_authenticated_user(request)

        profile_result: Result[
            UserKnowledgeProfile
        ] = await user_progress.build_user_knowledge_profile(user_uid)
        if profile_result.is_error:
            return Result.fail(profile_result)

        profile = profile_result.value

        return Result.ok(profile.to_dict())

    # Path Recommendations
    # --------------------

    @rt("/api/pathways/recommendations")
    @boundary_handler()
    async def get_path_recommendations_route(
        request: Request,
    ) -> Result[
        dict[str, Any]
    ]:  # skuel-lint: disable=SKUEL029 -- wrapped by @boundary_handler() which awaits the handler unconditionally (boundary.py)
        """Get recommended learning paths for a user."""
        require_authenticated_user(request)

        return Result.fail(
            Errors.system(
                message="Path recommendations not yet implemented", operation="get_recommendations"
            )
        )

    # Enrollment
    # ----------

    @rt("/api/pathways/enroll/{uid}", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def enroll_in_path_route(request: Request, uid: str) -> Any:
        """Enroll the authenticated user in a learning path.

        Errors convert to proper HTTP error responses via boundary_handler;
        success returns an HX-Redirect Response (passed through untouched).
        """
        user_uid = require_authenticated_user(request)

        result = await user_service.enroll_in_learning_path(user_uid, uid)
        if result.is_error:
            return Result.fail(result)

        return Response(headers={"HX-Redirect": f"/pathways/path/{uid}"})

    logger.info("Pathways API routes registered (CRUDRouteFactory + 7 domain routes)")

    return []


# Export the route creation function
__all__ = ["create_pathways_api_routes"]
