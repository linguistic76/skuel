"""Admin UI Orchestrator
========================

Application orchestrator for the Admin Dashboard. Consolidates
UserService, AdminStatsService, and SystemService into a single unified
facade for UI rendering.

All service dependencies are required except system_service, which
degrades gracefully when unavailable (system health returns unknown status).

See: /docs/patterns/UI_ORCHESTRATOR_PATTERN.md
"""

from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.admin_stats_service import AdminStatsService
    from core.services.system_service import SystemService
    from core.services.user_service import UserService


logger = get_logger("skuel.orchestrators.admin")


class AdminOrchestrator:
    """Facade for the Admin Dashboard UI layer.

    Abstracts cross-domain reads so the UI routing layer depends only on
    this orchestrator. ``user_service`` and ``admin_stats`` are required;
    ``system_service`` is optional (degrades gracefully — system health
    returns unknown status).
    """

    def __init__(
        self,
        user_service: "UserService",
        admin_stats: "AdminStatsService",
        system_service: "SystemService | None" = None,
    ) -> None:
        self._user_service = user_service
        self._admin_stats = admin_stats
        self._system_service = system_service

    @property
    def user_service(self) -> "UserService":
        """Exposed for make_service_getter() / @require_admin decorator."""
        return self._user_service

    # ------------------------------------------------------------------
    # System Health
    # ------------------------------------------------------------------

    async def get_system_status(self) -> tuple[dict[str, Any], bool]:
        """Get system health summary for navbar/overview widgets.

        Returns:
            (status_dict, had_error) — mirrors the old _get_system_status()
            helper signature so route call-sites need no restructuring.
        """
        try:
            if self._system_service:
                result = await self._system_service.get_health_status()
                if not result.is_error:
                    status = (
                        dict(result.value)
                        if result.value
                        else {"status": "unknown", "healthy": True}
                    )
                    return status, False
                return {"status": "unknown", "healthy": True}, True
        except Exception as e:  # safety-net: dashboard degrades gracefully on health check failure
            logger.warning(f"Failed to get system status: {e}")

        return {"status": "unknown", "healthy": True}, True

    async def get_full_health_status(self) -> dict[str, Any]:
        """Get detailed system health for the /admin/system page.

        Returns a health dict with status, components, and optional
        error_message. Never raises — returns error-state dict on failure.
        """
        try:
            if self._system_service:
                result = await self._system_service.get_health_status()
                if not result.is_error:
                    return (
                        dict(result.value)
                        if result.value
                        else {"status": "unknown", "components": {}}
                    )
                return {
                    "status": "error",
                    "components": {},
                    "error_message": result.expect_error().message,
                }
        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Unexpected error fetching system health: {e}")
            return {
                "status": "error",
                "components": {},
                "error_message": str(e),
            }

        return {"status": "unknown", "components": {}}

    # ------------------------------------------------------------------
    # User Management
    # ------------------------------------------------------------------

    async def get_user(self, uid: str) -> Result[Any]:
        """Fetch a single user by UID."""
        return await self._user_service.get_user(uid)

    async def get_users_with_activity_counts(
        self,
        role_filter: str | None = None,
        active_only: bool = True,
    ) -> Result[list[Any]]:
        """Fetch users with their activity counts, optionally filtered."""
        return await self._admin_stats.get_users_with_activity_counts(
            role_filter=role_filter,
            active_only=active_only,
        )

    async def get_user_role_counts(self) -> Result[dict[str, Any]]:
        """Fetch aggregate user counts grouped by role."""
        return await self._admin_stats.get_user_role_counts()

    async def get_user_detail_stats(self, uid: str) -> Result[dict[str, Any]]:
        """Fetch per-user activity and session stats for the detail view."""
        return await self._admin_stats.get_user_detail_stats(uid)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    async def get_activity_entity_counts(self) -> Result[dict[str, Any]]:
        """Fetch entity counts across activity domains (tasks, habits, etc.)."""
        return await self._admin_stats.get_activity_entity_counts()

    async def get_analytics_data(self) -> dict[str, Any]:
        """Aggregate user role counts + activity entity counts for the analytics page.

        Partial-failure tolerant — returns zero-value fallbacks for each
        failed sub-query rather than surfacing a top-level error.
        """
        user_stats_result = await self.get_user_role_counts()
        user_stats: dict[str, Any] = (
            user_stats_result.value
            if not user_stats_result.is_error
            else {"total": 0, "admins": 0, "teachers": 0, "members": 0, "registered": 0}
        )
        if user_stats_result.is_error:
            logger.error(f"Failed to load user role counts: {user_stats_result.error}")

        activity_result = await self.get_activity_entity_counts()
        activity_stats: dict[str, Any] = (
            activity_result.value
            if not activity_result.is_error
            else {
                k: "N/A"
                for k in ("tasks_created", "habits_active", "goals_active", "journals_submitted")
            }
        )
        if activity_result.is_error:
            logger.error(f"Error fetching activity stats: {activity_result.error}")

        return {"user_stats": user_stats, "activity_stats": activity_stats}
