"""Pathways Orchestrator
========================

Application orchestrator for the Pathways UI. Consolidates LpService and
UserProgressService into a single facade for pathways_ui.py, eliminating
the three-service dependency gravity in create_pathways_ui_routes.

LpService is always required. UserProgressService is optional — methods that
use it degrade gracefully (zero progress data returned).
"""

from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.path_step import PathStep
    from core.ports.query_types import LpDashboardSummary
    from core.services.lp_service import LpService
    from core.services.user_progress_service import UserProgressService
    from core.utils.result_simplified import Result


class PathwaysOrchestrator:
    """Facade for the Pathways UI layer.

    Wraps LpService and injects UserProgressService into calls that need it,
    so route handlers depend only on this orchestrator — not on the individual
    services or how progress is threaded through.
    """

    def __init__(
        self,
        lp_service: "LpService",
        user_progress: "UserProgressService | None" = None,
    ) -> None:
        self._lp = lp_service
        self._user_progress = user_progress

    # --- Dashboard ---

    async def get_dashboard_summary(self, user_uid: UserUID) -> "Result[LpDashboardSummary]":
        """Build pathways dashboard summary with active paths and learning stats."""
        return await self._lp.get_dashboard_summary(user_uid, self._user_progress)

    # --- Browse ---

    async def list_all_paths(self, limit: int = 50) -> "Result[list[LearningPath]]":
        """List all available learning paths."""
        return await self._lp.list_all_paths(limit=limit)

    async def filter_paths(
        self,
        difficulty: str = "all",
        domain: str = "all",
        duration: str = "all",
        limit: int = 50,
    ) -> "Result[list[dict[str, Any]]]":
        """Filter learning paths by difficulty, domain, and duration."""
        return await self._lp.filter_paths(
            difficulty=difficulty,
            domain=domain,
            duration=duration,
            limit=limit,
        )

    async def list_steps(self, limit: int = 50) -> "Result[list[PathStep]]":
        """List available path steps. Returns Result.fail when PsService unavailable."""
        return await self._lp.list_steps(limit=limit)

    # --- Detail ---

    async def get_path_detail_progress(
        self, path_uid: str, user_uid: UserUID
    ) -> "Result[dict[str, Any]]":
        """Get a learning path with per-user progress and mastery info."""
        return await self._lp.get_path_detail_progress(path_uid, self._user_progress, user_uid)

    async def get_learning_path(self, uid: str) -> "Result[LearningPath | None]":
        """Fetch a single learning path by UID."""
        return await self._lp.get_learning_path(uid)

    # --- Analytics ---

    async def get_learning_analytics(self, user_uid: UserUID) -> "Result[dict[str, Any]]":
        """Get learning analytics data from user's knowledge profile."""
        return await self._lp.get_learning_analytics(user_uid, self._user_progress)
