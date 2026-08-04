"""
Visualization API Routes
=========================

FastHTML API routes for visualization data endpoints.

These routes return JSON formatted for:
- Chart.js (completion, distribution, streak charts)
- Frappe Gantt (project planning)

Security:
- All routes require authentication (January 2026 hardening)
- User data is fetched for the authenticated user only (no user_uid param)
- Prevents IDOR vulnerability where user_uid param could expose other users' data

Architecture:
    - Aggregation: core/services/analytics/visualization_aggregation_service.py
    - Formatting: core/services/visualization_service.py
    - Components: /components/visualization_components.py
    - Alpine.js: /static/js/skuel.js
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import Request
from core.ports.query_types import ChartJsConfig, GanttConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports import VisualizationOperations

logger = get_logger("skuel.routes.visualization_api")


def create_visualization_api_routes(
    app: Any,
    rt: Any,
    visualization_service: "VisualizationOperations",
) -> list[Any]:
    """Create visualization API routes."""
    vis_service = visualization_service
    routes: list[Any] = []

    # =========================================================================
    # Chart.js Endpoints
    # =========================================================================

    @rt("/api/visualizations/completion")
    @boundary_handler()
    async def get_completion_chart(request: Request) -> Result[ChartJsConfig]:
        """Get task completion rate data for Chart.js."""
        user_uid = require_authenticated_user(request)
        period = request.query_params.get("period", "week")
        return await vis_service.get_completion_chart_data(user_uid=user_uid, period=period)

    @rt("/api/visualizations/priority-distribution")
    @boundary_handler()
    async def get_priority_distribution(request: Request) -> Result[ChartJsConfig]:
        """Get task priority distribution for Chart.js pie/doughnut."""
        user_uid = require_authenticated_user(request)
        return await vis_service.get_priority_distribution_chart_data(user_uid=user_uid)

    @rt("/api/visualizations/streaks")
    @boundary_handler()
    async def get_streak_chart(request: Request) -> Result[ChartJsConfig]:
        """Get habit streak data for Chart.js horizontal bar."""
        user_uid = require_authenticated_user(request)
        return await vis_service.get_streak_chart_data(user_uid=user_uid)

    @rt("/api/visualizations/status-distribution")
    @boundary_handler()
    async def get_status_distribution(request: Request) -> Result[ChartJsConfig]:
        """Get task status distribution for Chart.js."""
        user_uid = require_authenticated_user(request)
        return await vis_service.get_status_distribution_chart_data(user_uid=user_uid)

    # =========================================================================
    # Frappe Gantt Endpoints
    # =========================================================================

    @rt("/api/visualizations/gantt/tasks")
    @boundary_handler()
    async def get_tasks_gantt(request: Request) -> Result[GanttConfig]:
        """Get tasks Gantt data for Frappe Gantt."""
        user_uid = require_authenticated_user(request)
        project = request.query_params.get("project")
        return await vis_service.get_tasks_gantt_data(user_uid=user_uid, project=project)

    @rt("/api/visualizations/gantt/goal/{goal_uid}")
    @boundary_handler()
    async def get_goal_gantt(request: Request, goal_uid: str) -> Result[GanttConfig]:
        """Get goal with tasks as Gantt data."""
        user_uid = require_authenticated_user(request)
        return await vis_service.get_goal_gantt_data(user_uid=user_uid, goal_uid=goal_uid)

    # Collect all routes
    routes.extend(
        [
            get_completion_chart,
            get_priority_distribution,
            get_streak_chart,
            get_status_distribution,
            get_tasks_gantt,
            get_goal_gantt,
        ]
    )

    logger.info(f"Visualization API routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_visualization_api_routes"]
