"""
Visualization Routes
====================

FastHTML API routes for visualization data endpoints.

These routes return JSON formatted for:
- Chart.js (completion, distribution, streak charts)
- Vis.js Timeline (calendar/task timelines)
- Frappe Gantt (project planning)

Security:
- All routes require authentication (January 2026 hardening)
- User data is fetched for the authenticated user only (no user_uid param)
- Prevents IDOR vulnerability where user_uid param could expose other users' data

Architecture:
    - Service: /core/services/visualization_service.py
    - Components: /components/visualization_components.py
    - Alpine.js: /static/js/skuel.js
"""

from datetime import date, timedelta

from starlette.requests import Request
from starlette.responses import JSONResponse

from core.auth import require_authenticated_user
from core.services.visualization_service import VisualizationService
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.visualization")


def create_visualization_routes(app, rt, services):
    """
    Create visualization API routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Services container with calendar_service, tasks_service, etc.
    """
    vis_service = VisualizationService()

    # =========================================================================
    # Chart.js Endpoints
    # =========================================================================

    @rt("/api/visualizations/completion")
    @boundary_handler()
    async def get_completion_chart(request: Request) -> JSONResponse:
        """
        Get task completion rate data for Chart.js.

        Query params:
            period: week, month, or quarter (default: week)

        Security: Uses authenticated user only (no user_uid param - IDOR fix)
        """
        user_uid = require_authenticated_user(request)
        period = request.query_params.get("period", "week")

        # Get completion data from service
        if services.tasks_service:
            data_result = await vis_service.get_completion_data(
                user_uid=user_uid,
                period=period,
                tasks_service=services.tasks_service,
            )

            if data_result.is_error:
                return JSONResponse({"error": str(data_result.error)}, status_code=400)

            data = data_result.value
            completed = data["completed"]
            total = data["total"]
            labels = data["labels"]
        else:
            # Demo data if no service
            completed = [3, 5, 4, 6, 4, 7, 5]
            total = [5, 6, 5, 7, 6, 8, 6]
            labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        # Format for Chart.js
        chart_result = vis_service.format_completion_chart(completed, total, labels)

        if chart_result.is_error:
            return JSONResponse({"error": str(chart_result.error)}, status_code=400)

        return JSONResponse(chart_result.value)

    @rt("/api/visualizations/priority-distribution")
    @boundary_handler()
    async def get_priority_distribution(request: Request) -> JSONResponse:
        """
        Get task priority distribution for Chart.js pie/doughnut.

        Security: Uses authenticated user only (no user_uid param - IDOR fix)
        """
        user_uid = require_authenticated_user(request)

        if services.tasks_service:
            # Get priority distribution from service
            dist_result = await vis_service.get_priority_distribution_data(
                user_uid=user_uid,
                tasks_service=services.tasks_service,
            )

            if dist_result.is_error:
                return JSONResponse({"error": str(dist_result.error)}, status_code=400)

            distribution = dist_result.value
        else:
            distribution = {}

        if not distribution:
            # Demo data
            distribution = {
                "critical": 2,
                "high": 5,
                "medium": 12,
                "low": 8,
                "none": 3,
            }

        # Format for Chart.js
        chart_result = vis_service.format_distribution_chart(
            distribution, "Task Priority Distribution", "doughnut"
        )

        if chart_result.is_error:
            return JSONResponse({"error": str(chart_result.error)}, status_code=400)

        return JSONResponse(chart_result.value)

    @rt("/api/visualizations/streaks")
    @boundary_handler()
    async def get_streak_chart(request: Request) -> JSONResponse:
        """
        Get habit streak data for Chart.js horizontal bar.

        Security: Uses authenticated user only (no user_uid param - IDOR fix)
        """
        user_uid = require_authenticated_user(request)

        if services.habits_service:
            # Get streak data from service
            streak_result = await vis_service.get_streak_data(
                user_uid=user_uid,
                habits_service=services.habits_service,
            )

            if streak_result.is_error:
                return JSONResponse({"error": str(streak_result.error)}, status_code=400)

            streaks = streak_result.value
        else:
            streaks = []

        if not streaks:
            # Demo data
            streaks = [
                {"name": "Morning Meditation", "current": 14, "best": 21},
                {"name": "Exercise", "current": 7, "best": 30},
                {"name": "Reading", "current": 45, "best": 45},
                {"name": "Journaling", "current": 3, "best": 15},
            ]

        # Format for Chart.js
        chart_result = vis_service.format_streak_chart(streaks)

        if chart_result.is_error:
            return JSONResponse({"error": str(chart_result.error)}, status_code=400)

        return JSONResponse(chart_result.value)

    @rt("/api/visualizations/status-distribution")
    @boundary_handler()
    async def get_status_distribution(request: Request) -> JSONResponse:
        """
        Get task status distribution for Chart.js.

        Security: Uses authenticated user only (no user_uid param - IDOR fix)
        """
        user_uid = require_authenticated_user(request)

        if services.tasks_service:
            # Get status distribution from service
            dist_result = await vis_service.get_status_distribution_data(
                user_uid=user_uid,
                tasks_service=services.tasks_service,
                days_back=30,
            )

            if dist_result.is_error:
                return JSONResponse({"error": str(dist_result.error)}, status_code=400)

            distribution = dist_result.value
        else:
            distribution = {}

        if not distribution:
            # Demo data
            distribution = {
                "done": 25,
                "in_progress": 8,
                "draft": 5,
                "blocked": 2,
            }

        # Format for Chart.js
        chart_result = vis_service.format_distribution_chart(
            distribution, "Task Status Distribution", "pie"
        )

        if chart_result.is_error:
            return JSONResponse({"error": str(chart_result.error)}, status_code=400)

        return JSONResponse(chart_result.value)

    # =========================================================================
    # Vis.js Timeline Endpoints
    # =========================================================================

    @rt("/api/visualizations/timeline")
    @boundary_handler()
    async def get_timeline_data(request: Request) -> JSONResponse:
        """
        Get calendar timeline data for Vis.js.

        Query params:
            start_date: Start date ISO format (optional)
            end_date: End date ISO format (optional)
            group_by: type, project, or none (default: type)

        Security: Uses authenticated user only (no user_uid param - IDOR fix)
        """
        user_uid = require_authenticated_user(request)

        # Parse dates
        today = date.today()
        start_str = request.query_params.get("start_date")
        end_str = request.query_params.get("end_date")

        start_date = date.fromisoformat(start_str) if start_str else today - timedelta(days=7)
        end_date = date.fromisoformat(end_str) if end_str else today + timedelta(days=14)

        group_by = request.query_params.get("group_by", "type")

        # Get calendar data
        if services.calendar_service:
            result = await services.calendar_service.get_calendar_view(
                user_uid=user_uid,
                start_date=start_date,
                end_date=end_date,
            )

            if result.is_error:
                return JSONResponse({"error": result.error}, status_code=500)

            calendar_data = result.value
            timeline_result = vis_service.format_for_visjs(calendar_data, group_by)

            if timeline_result.is_error:
                return JSONResponse({"error": timeline_result.error}, status_code=400)

            return JSONResponse(timeline_result.value)

        # Demo data if no service
        demo_data = {
            "items": [
                {
                    "id": "demo-1",
                    "content": "Project Planning",
                    "start": today.isoformat(),
                    "end": (today + timedelta(days=2)).isoformat(),
                    "group": "tasks",
                },
                {
                    "id": "demo-2",
                    "content": "Team Meeting",
                    "start": (today + timedelta(days=1)).isoformat(),
                    "group": "events",
                    "type": "point",
                },
            ],
            "groups": [
                {"id": "tasks", "content": "Tasks"},
                {"id": "events", "content": "Events"},
            ],
            "options": {"showCurrentTime": True},
        }
        return JSONResponse(demo_data)

    @rt("/api/visualizations/tasks-timeline")
    @boundary_handler()
    async def get_tasks_timeline(request: Request) -> JSONResponse:
        """
        Get tasks-only timeline data for Vis.js.

        Query params:
            project: Project filter (optional)

        Security: Uses authenticated user only (no user_uid param - IDOR fix)
        """
        user_uid = require_authenticated_user(request)

        project = request.query_params.get("project")

        today = date.today()

        if services.tasks_service:
            result = await services.tasks_service.get_user_items_in_range(
                user_uid=user_uid,
                start_date=today - timedelta(days=30),
                end_date=today + timedelta(days=60),
                include_completed=True,
            )

            if result.is_error:
                return JSONResponse({"error": result.error}, status_code=500)

            tasks = result.value or []

            # Filter by project if specified
            if project:
                tasks = [t for t in tasks if getattr(t, "project", None) == project]

            timeline_result = vis_service.format_tasks_for_visjs(tasks)

            if timeline_result.is_error:
                return JSONResponse({"error": timeline_result.error}, status_code=400)

            return JSONResponse(timeline_result.value)

        # Demo data
        demo_data = {
            "items": [
                {
                    "id": "task-1_work",
                    "content": "Complete Report",
                    "start": today.isoformat() + "T09:00:00",
                    "end": today.isoformat() + "T11:00:00",
                    "group": "tasks",
                },
            ],
            "groups": [
                {"id": "tasks", "content": "Tasks"},
                {"id": "deadlines", "content": "Deadlines"},
            ],
        }
        return JSONResponse(demo_data)

    # =========================================================================
    # Frappe Gantt Endpoints
    # =========================================================================

    @rt("/api/visualizations/gantt/tasks")
    @boundary_handler()
    async def get_tasks_gantt(request: Request) -> JSONResponse:
        """
        Get tasks Gantt data for Frappe Gantt.

        Query params:
            project: Project filter (optional)

        Security: Uses authenticated user only (no user_uid param - IDOR fix)
        """
        user_uid = require_authenticated_user(request)

        project = request.query_params.get("project")

        today = date.today()
        dependencies: dict[str, list[str]] = {}

        if services.tasks_service:
            result = await services.tasks_service.get_user_items_in_range(
                user_uid=user_uid,
                start_date=today - timedelta(days=7),
                end_date=today + timedelta(days=60),
                include_completed=True,
            )

            if result.is_error:
                return JSONResponse({"error": result.error}, status_code=500)

            tasks = result.value or []

            # Filter by project if specified
            if project:
                tasks = [t for t in tasks if getattr(t, "project", None) == project]

            # Get dependencies (tasks_service.relationships always exists per SKUEL architecture)
            for task in tasks:
                try:
                    deps_result = await services.tasks_service.relationships.get_task_prerequisites(
                        task.uid
                    )
                    if deps_result.is_ok and deps_result.value:
                        dependencies[task.uid] = [d.uid for d in deps_result.value]
                except Exception:
                    pass  # Dependencies are optional

            gantt_result = vis_service.format_for_gantt(tasks, dependencies)

            if gantt_result.is_error:
                return JSONResponse({"error": gantt_result.error}, status_code=400)

            return JSONResponse(gantt_result.value)

        # Demo data
        demo_data = {
            "tasks": [
                {
                    "id": "task-1",
                    "name": "Research Phase",
                    "start": today.isoformat(),
                    "end": (today + timedelta(days=5)).isoformat(),
                    "progress": 80,
                    "dependencies": "",
                },
                {
                    "id": "task-2",
                    "name": "Design Phase",
                    "start": (today + timedelta(days=5)).isoformat(),
                    "end": (today + timedelta(days=12)).isoformat(),
                    "progress": 20,
                    "dependencies": "task-1",
                },
                {
                    "id": "task-3",
                    "name": "Implementation",
                    "start": (today + timedelta(days=12)).isoformat(),
                    "end": (today + timedelta(days=25)).isoformat(),
                    "progress": 0,
                    "dependencies": "task-2",
                },
            ],
            "options": {"view_mode": "Week"},
        }
        return JSONResponse(demo_data)

    @rt("/api/visualizations/gantt/goal/{goal_uid}")
    @boundary_handler()
    async def get_goal_gantt(request: Request, goal_uid: str) -> JSONResponse:
        """
        Get goal with tasks as Gantt data.

        Path params:
            goal_uid: Goal UID
        """
        user_uid = require_authenticated_user(request)

        if services.goals_service:
            # Get goal
            goal_result = await services.goals_service.get_for_user(goal_uid, user_uid)

            if goal_result.is_error:
                return JSONResponse({"error": goal_result.error}, status_code=404)

            goal = goal_result.value

            # Get related tasks (goals_service.relationships always exists per SKUEL architecture)
            tasks = []
            tasks_result = await services.goals_service.relationships.get_goal_tasks(goal_uid)
            if tasks_result.is_ok:
                tasks = tasks_result.value or []

            gantt_result = vis_service.format_goal_gantt(goal, tasks)

            if gantt_result.is_error:
                return JSONResponse({"error": gantt_result.error}, status_code=400)

            return JSONResponse(gantt_result.value)

        # Demo data
        today = date.today()
        demo_data = {
            "tasks": [
                {
                    "id": goal_uid,
                    "name": "Goal: Complete Project",
                    "start": today.isoformat(),
                    "end": (today + timedelta(days=30)).isoformat(),
                    "progress": 40,
                    "custom_class": "goal-bar",
                },
            ],
            "options": {"view_mode": "Month"},
        }
        return JSONResponse(demo_data)

    logger.info("Visualization routes registered")
