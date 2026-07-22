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

from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.user import User
    from core.ports.query_types import KnowledgeHealthReport
    from core.services.admin_stats_service import AdminStatsService
    from core.services.analytics_service import AnalyticsService
    from core.services.system_service import SystemService
    from core.services.user_service import UserService


logger = get_logger("skuel.orchestrators.admin")


class AdminOrchestrator:
    """Facade for the Admin Dashboard UI layer.

    Abstracts cross-domain reads so the UI routing layer depends only on
    this orchestrator. ``user_service`` and ``admin_stats`` are required;
    ``system_service`` and ``analytics_service`` are optional (degrade
    gracefully — system health returns unknown status, knowledge-health
    returns a clean error).
    """

    def __init__(
        self,
        user_service: "UserService",
        admin_stats: "AdminStatsService",
        system_service: "SystemService | None" = None,
        analytics_service: "AnalyticsService | None" = None,
    ) -> None:
        self._user_service = user_service
        self._admin_stats = admin_stats
        self._system_service = system_service
        self._analytics_service = analytics_service

    @property
    def user_service(self) -> "UserService":
        """Exposed for make_service_getter() / @require_admin decorator."""
        return self._user_service

    # ------------------------------------------------------------------
    # System Health
    # ------------------------------------------------------------------

    async def get_system_status(self) -> dict[str, Any]:
        """Get system health summary for navbar/overview widgets.

        Never raises — returns ``{"status": "unknown", "healthy": False}``
        when the system service is unavailable or returns an error.
        """
        try:
            if self._system_service:
                result = await self._system_service.get_health_status()
                if not result.is_error:
                    return (
                        dict(result.value)
                        if result.value
                        else {"status": "unknown", "healthy": False}
                    )
                logger.warning(f"System health check failed: {result.expect_error().message}")
        except Exception as e:  # safety-net: dashboard degrades gracefully on health check failure
            logger.warning(f"Failed to get system status: {e}")

        return {"status": "unknown", "healthy": False}

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

    async def get_user(self, uid: UserUID) -> "Result[User | None]":
        """Fetch a single user by UID."""
        return await self._user_service.get_user(uid)

    async def get_users_with_activity_counts(
        self,
        role_filter: str | None = None,
        active_only: bool = True,
    ) -> "Result[list[dict[str, Any]]]":
        """Fetch users with their activity counts, optionally filtered."""
        return await self._admin_stats.get_users_with_activity_counts(
            role_filter=role_filter,
            active_only=active_only,
        )

    async def get_user_role_counts(self) -> "Result[dict[str, int]]":
        """Fetch aggregate user counts grouped by role."""
        return await self._admin_stats.get_user_role_counts()

    async def get_user_detail_stats(self, uid: UserUID) -> "Result[dict[str, int]]":
        """Fetch per-user activity and session stats for the detail view."""
        return await self._admin_stats.get_user_detail_stats(uid)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    async def _get_activity_entity_counts(self) -> "Result[dict[str, int]]":
        """Fetch entity counts across activity domains (tasks, habits, etc.)."""
        return await self._admin_stats.get_activity_entity_counts()

    async def get_analytics_data(self) -> dict[str, Any]:
        """Aggregate role counts + activity counts + search gaps for the analytics page.

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

        activity_result = await self._get_activity_entity_counts()
        activity_stats: dict[str, Any] = (
            activity_result.value
            if not activity_result.is_error
            else {k: 0 for k in ("tasks_created", "habits_active", "goals_active")}
        )
        if activity_result.is_error:
            logger.error(f"Error fetching activity stats: {activity_result.error}")

        gaps_result = await self._admin_stats.get_search_gaps()
        search_gaps: list[dict[str, Any]] = (
            [dict(row) for row in (gaps_result.value or [])] if not gaps_result.is_error else []
        )
        if gaps_result.is_error:
            logger.error(f"Failed to load search gaps: {gaps_result.error}")

        total_result = await self._admin_stats.get_search_event_total()
        search_event_total: int = (total_result.value or 0) if not total_result.is_error else 0
        if total_result.is_error:
            logger.error(f"Failed to load search event total: {total_result.error}")

        return {
            "user_stats": user_stats,
            "activity_stats": activity_stats,
            "search_gaps": search_gaps,
            "search_event_total": search_event_total,
        }

    # ------------------------------------------------------------------
    # Knowledge-Subgraph Structural Health (ADR-080 Horizon-1)
    # ------------------------------------------------------------------

    async def get_knowledge_health(self) -> "Result[KnowledgeHealthReport]":
        """Corpus-level structural-health report over the knowledge subgraph.

        Delegates to the analytics facade's knowledge-health gauge. Returns a
        clean error Result when analytics is not wired (rather than raising), so
        the admin page can render an error banner.
        """
        if self._analytics_service is None:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(
                    message="Analytics service not available",
                    operation="get_knowledge_health",
                )
            )
        return await self._analytics_service.analyze_knowledge_subgraph_health()
