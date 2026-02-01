"""
Tasks UI Routes - Three-View Standalone Implementation
======================================================

Standalone task management UI with three views: List, Create, Calendar.

Routes:
- GET /tasks - Main dashboard with three views (standalone, no drawer)
- GET /tasks/view/list - HTMX fragment for list view
- GET /tasks/view/create - HTMX fragment for create view
- GET /tasks/view/calendar - HTMX fragment for calendar view
- GET /tasks/list-fragment - HTMX filtered list (for filter updates)
- POST /tasks/quick-add - Create task via form
- POST /tasks/{uid}/toggle - Toggle task completion
- GET /tasks/autocomplete/projects - Project suggestions
- GET /tasks/autocomplete/assignees - Assignee suggestions
"""

import contextlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from fasthtml.common import H1, H2, Div, JSONResponse, P, Response, Span

from components.error_components import ErrorComponents
from components.tasks_views import TasksViewComponents
from components.todoist_task_components import TodoistTaskComponents
from core.auth import require_authenticated_user
from core.infrastructure.routes import QuickAddConfig, QuickAddRouteFactory
from core.models.enums.scheduling_enums import RecurrencePattern
from core.models.shared_enums import ActivityStatus, Priority
from core.models.task.task_request import TaskCreateRequest
from core.services.protocols.facade_protocols import TasksFacadeProtocol
from core.ui.daisy_components import Button, ButtonT, Card
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import (
    get_created_at_attr,
    get_project_and_title,
    get_task_due_date_sort_key,
    make_priority_order_getter,
)
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.relationships import EntityRelationshipsSection
from ui.tasks.layout import create_tasks_page
from ui.tokens import Container, Spacing

logger = get_logger("skuel.routes.tasks.todoist")


# ========================================================================
# TYPE PROTOCOLS
# ========================================================================


class RouteDecorator(Protocol):
    """Protocol for FastHTML route decorator."""

    def __call__(self, path: str, methods: list[str] | None = None) -> Any: ...


class Request(Protocol):
    """Protocol for Starlette Request (lightweight)."""

    query_params: dict[str, str]

    async def form(self) -> dict[str, Any]: ...


def create_tasks_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    tasks_service: TasksFacadeProtocol,
    services: Any = None,
) -> list:
    """
    Create three-view task UI routes (standalone, no drawer).

    Views:
    - List: Sortable, filterable task list
    - Create: Full task creation form
    - Calendar: Month/Week/Day views

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        tasks_service: Tasks service instance
        services: Full services container (unused, kept for API compatibility)
    """

    logger.info("Registering three-view task routes (standalone)")

    # ========================================================================
    # QUERY PARAM TYPES
    # ========================================================================

    @dataclass
    class Filters:
        """Typed filters for task list queries."""

        project: str
        assignee: str
        due_filter: str
        status_filter: str
        sort_by: str

    @dataclass
    class CalendarParams:
        """Typed params for calendar view."""

        calendar_view: str
        current_date: date

    # ========================================================================
    # HELPER FUNCTIONS
    # ========================================================================

    def parse_filters(request: Request) -> Filters:
        """Extract filter parameters from request query params."""
        return Filters(
            project=request.query_params.get("filter_project", ""),
            assignee=request.query_params.get("filter_assignee", ""),
            due_filter=request.query_params.get("filter_due", ""),
            status_filter=request.query_params.get("filter_status", "active"),
            sort_by=request.query_params.get("sort_by", "due_date"),
        )

    def parse_calendar_params(request: Request) -> CalendarParams:
        """Extract calendar view parameters from request query params."""
        calendar_view = request.query_params.get("calendar_view", "month")
        date_str = request.query_params.get("date", "")

        # Parse date or use today
        try:
            current_date = date.fromisoformat(date_str) if date_str else date.today()
        except ValueError:
            current_date = date.today()

        return CalendarParams(calendar_view=calendar_view, current_date=current_date)

    # Error rendering moved to components.error_components.ErrorComponents

    # ========================================================================
    # AUTOCOMPLETE CACHE
    # ========================================================================

    _autocomplete_cache: dict[str, tuple[datetime, list[str]]] = {}
    _cache_ttl_seconds = 300  # 5 minutes

    def _get_cached_autocomplete(
        cache_key: str,
        fetch_fn: Any,  # Callable returning list[str]
    ) -> list[str]:
        """
        Get autocomplete results from cache or fetch fresh.

        Args:
            cache_key: Unique key for cache (e.g., "projects:user.mike")
            fetch_fn: Function to fetch fresh data if cache miss

        Returns:
            Cached or fresh list of strings
        """
        now = datetime.now()

        # Check cache
        if cache_key in _autocomplete_cache:
            cached_time, cached_data = _autocomplete_cache[cache_key]
            age = (now - cached_time).total_seconds()

            if age < _cache_ttl_seconds:
                logger.debug(f"Autocomplete cache HIT: {cache_key} (age: {age:.1f}s)")
                return cached_data

        # Cache miss - fetch fresh
        logger.debug(f"Autocomplete cache MISS: {cache_key}")
        fresh_data = fetch_fn()
        _autocomplete_cache[cache_key] = (now, fresh_data)

        return fresh_data

    # ========================================================================
    # ERROR HANDLING
    # ========================================================================

    def render_safe_error_response(
        user_message: str,
        error_context: Any,
        logger_instance: Any,  # Logger instance
        log_extra: dict[str, Any],
        status_code: int = 500,
    ) -> Response:
        """
        Return sanitized error to client, log detailed error server-side.

        Args:
            user_message: Safe message for client (e.g., "Failed to update task")
            error_context: Detailed error (logged but NOT sent to client)
            logger_instance: Logger instance for structured logging
            log_extra: Additional context for logs (user_uid, entity_uid, etc.)
            status_code: HTTP status code

        Returns:
            Response with sanitized message
        """
        # Log detailed error server-side
        logger_instance.error(
            user_message,
            extra={
                **log_extra,
                "error_type": type(error_context).__name__,
                "error_detail": str(error_context),
            },
        )

        # Return safe message to client
        return Response(user_message, status_code=status_code)

    # ========================================================================
    # DATA FETCHING
    # ========================================================================

    async def get_all_tasks(user_uid: str) -> Result[list[Any]]:
        """Get all tasks for user."""
        try:
            result = await tasks_service.get_user_tasks(user_uid)
            if result.is_error:
                logger.warning(f"Failed to fetch tasks: {result.error}")
                return result  # Propagate the error
            return Result.ok(result.value or [])
        except Exception as e:
            logger.error(
                "Error fetching all tasks",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to fetch tasks: {e}"))

    async def get_distinct_projects(user_uid: str) -> Result[list[str]]:
        """Get distinct project names for the user's tasks (with caching)."""
        cache_key = f"projects:{user_uid}"

        try:
            # Try cache first
            now = datetime.now()
            if cache_key in _autocomplete_cache:
                cached_time, cached_data = _autocomplete_cache[cache_key]
                age = (now - cached_time).total_seconds()
                if age < _cache_ttl_seconds:
                    logger.debug(f"Autocomplete cache HIT: {cache_key} (age: {age:.1f}s)")
                    return Result.ok(cached_data)

            # Cache miss - fetch fresh
            logger.debug(f"Autocomplete cache MISS: {cache_key}")
            tasks_result = await get_all_tasks(user_uid)
            if tasks_result.is_error:
                return tasks_result

            tasks = tasks_result.value
            projects = sorted({t.project for t in tasks if t.project})

            # Update cache
            _autocomplete_cache[cache_key] = (now, projects)

            return Result.ok(projects)
        except Exception as e:
            logger.error(
                "Error fetching projects",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to fetch projects: {e}"))

    async def get_distinct_assignees(user_uid: str) -> Result[list[str]]:
        """Get distinct assignee names for the user's tasks (with caching)."""
        cache_key = f"assignees:{user_uid}"

        try:
            # Try cache first
            now = datetime.now()
            if cache_key in _autocomplete_cache:
                cached_time, cached_data = _autocomplete_cache[cache_key]
                age = (now - cached_time).total_seconds()
                if age < _cache_ttl_seconds:
                    logger.debug(f"Autocomplete cache HIT: {cache_key} (age: {age:.1f}s)")
                    return Result.ok(cached_data)

            # Cache miss - fetch fresh
            logger.debug(f"Autocomplete cache MISS: {cache_key}")
            tasks_result = await get_all_tasks(user_uid)
            if tasks_result.is_error:
                return tasks_result

            tasks = tasks_result.value
            assignees = {getattr(t, "assignee", None) for t in tasks}
            assignees.discard(None)
            assignees_sorted = sorted(assignees)

            # Update cache
            _autocomplete_cache[cache_key] = (now, assignees_sorted)

            return Result.ok(assignees_sorted)
        except Exception as e:
            logger.error(
                "Error fetching assignees",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to fetch assignees: {e}"))

    # ========================================================================
    # PURE COMPUTATION HELPERS (Testable without mocks)
    # ========================================================================

    def validate_task_form_data(form_data: dict[str, Any]) -> Result[None]:
        """
        Validate task form data early.

        Pure function: returns clear error messages for UI.

        Args:
            form_data: Raw form data from request

        Returns:
            Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
        """
        # Required fields
        title = form_data.get("title", "").strip()
        if not title:
            return Result.fail(Errors.validation("Task title is required"))

        if len(title) > 200:
            return Result.fail(Errors.validation("Task title must be 200 characters or less"))

        # Date validation
        scheduled_date_str = form_data.get("scheduled_date", "")
        due_date_str = form_data.get("due_date", "")

        if scheduled_date_str and due_date_str:
            try:
                scheduled = date.fromisoformat(scheduled_date_str)
                due = date.fromisoformat(due_date_str)
                if due < scheduled:
                    return Result.fail(
                        Errors.validation("Due date cannot be before scheduled date")
                    )
            except ValueError:
                return Result.fail(Errors.validation("Invalid date format"))

        return Result.ok(None)

    def compute_task_stats(tasks: list[Any]) -> dict[str, int]:
        """Calculate task statistics.

        Pure function: testable without database or async.

        Args:
            tasks: List of task entities

        Returns:
            Stats dict with total, completed, overdue counts
        """
        today = date.today()
        return {
            "total": len(tasks),
            "completed": sum(1 for t in tasks if t.status == ActivityStatus.COMPLETED),
            "overdue": sum(
                1
                for t in tasks
                if t.due_date and t.due_date < today and t.status != ActivityStatus.COMPLETED
            ),
        }

    def apply_task_filters(
        tasks: list[Any],
        project: str | None = None,
        assignee: str | None = None,
        due_filter: str | None = None,
        status_filter: str = "active",
    ) -> list[Any]:
        """Apply filter criteria to task list.

        Pure function: testable without database or async.

        Args:
            tasks: List of task entities
            project: Filter by project name
            assignee: Filter by assignee name
            due_filter: Date filter (today, tomorrow, week, overdue, etc.)
            status_filter: Status filter (active, completed, all)

        Returns:
            Filtered list of tasks
        """
        today = date.today()

        # Filter: project
        if project:
            tasks = [t for t in tasks if t.project == project]

        # Filter: assignee
        if assignee:
            tasks = [t for t in tasks if getattr(t, "assignee", None) == assignee]

        # Filter: due date
        if due_filter == "today":
            tasks = [t for t in tasks if t.due_date == today]
        elif due_filter == "tomorrow":
            tomorrow = today + timedelta(days=1)
            tasks = [t for t in tasks if t.due_date == tomorrow]
        elif due_filter == "week":
            week_end = today + timedelta(days=7)
            tasks = [t for t in tasks if t.due_date and t.due_date <= week_end]
        elif due_filter == "overdue":
            tasks = [
                t
                for t in tasks
                if t.due_date and t.due_date < today and t.status != ActivityStatus.COMPLETED
            ]

        # Filter: status
        if status_filter == "active":
            tasks = [t for t in tasks if t.status != ActivityStatus.COMPLETED]
        elif status_filter == "completed":
            tasks = [t for t in tasks if t.status == ActivityStatus.COMPLETED]
        # "all" - no filtering

        return tasks

    def apply_task_sort(tasks: list[Any], sort_by: str = "due_date") -> list[Any]:
        """Sort tasks by specified field.

        Pure function: testable without database or async.

        Args:
            tasks: List of task entities
            sort_by: Sort field (due_date, priority, created_at, project)

        Returns:
            Sorted list of tasks
        """
        if sort_by == "due_date":
            return sorted(tasks, key=get_task_due_date_sort_key)
        elif sort_by == "priority":
            priority_order = {
                Priority.CRITICAL: 0,
                Priority.HIGH: 1,
                Priority.MEDIUM: 2,
                Priority.LOW: 3,
            }
            priority_sort_key = make_priority_order_getter(priority_order)
            return sorted(tasks, key=priority_sort_key)
        elif sort_by == "created_at":
            return sorted(tasks, key=get_created_at_attr, reverse=True)
        elif sort_by == "project":
            return sorted(tasks, key=get_project_and_title)
        else:
            # Default: due_date
            return sorted(tasks, key=get_task_due_date_sort_key)

    async def get_filtered_tasks(
        user_uid: str,
        project: str | None = None,
        assignee: str | None = None,
        due_filter: str | None = None,
        status_filter: str = "active",
        sort_by: str = "due_date",
    ) -> Result[tuple[list[Any], dict[str, int]]]:
        """Get filtered and sorted tasks for user.

        Orchestrates: fetch (I/O) → stats → filter → sort.
        Pure computation delegated to testable helper functions.
        """
        try:
            # I/O: Fetch all tasks
            tasks_result = await get_all_tasks(user_uid)
            if tasks_result.is_error:
                return tasks_result

            tasks = tasks_result.value

            # Computation: Calculate stats BEFORE filtering
            stats = compute_task_stats(tasks)

            # Computation: Apply filters
            filtered_tasks = apply_task_filters(tasks, project, assignee, due_filter, status_filter)

            # Computation: Apply sort
            sorted_tasks = apply_task_sort(filtered_tasks, sort_by)

            return Result.ok((sorted_tasks, stats))

        except Exception as e:
            logger.error(
                "Error filtering tasks",
                extra={
                    "user_uid": user_uid,
                    "project": project,
                    "status_filter": status_filter,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to filter tasks: {e}"))

    # ========================================================================
    # MAIN DASHBOARD (Standalone Three-View)
    # ========================================================================

    @rt("/tasks")
    async def tasks_dashboard(request) -> Any:
        """Main tasks dashboard with three views (standalone, no drawer)."""
        user_uid = require_authenticated_user(request)

        # Get view parameter (default to list)
        view = request.query_params.get("view", "list")

        # Get filter params (for list view)
        filters = parse_filters(request)

        # Get calendar params (for calendar view)
        calendar_params = parse_calendar_params(request)

        # Get data (with error handling)
        filtered_result = await get_filtered_tasks(
            user_uid,
            filters.project or None,
            filters.assignee or None,
            filters.due_filter or None,
            filters.status_filter,
            filters.sort_by,
        )
        projects_result = await get_distinct_projects(user_uid)
        assignees_result = await get_distinct_assignees(user_uid)

        # Check for errors
        if filtered_result.is_error:
            error_content = Div(
                TasksViewComponents.render_view_tabs(active_view=view),
                ErrorComponents.render_error_banner("Failed to load tasks"),
                cls=f"{Spacing.PAGE} {Container.WIDE}",
            )
            return create_tasks_page(error_content, user_uid)

        tasks, stats = filtered_result.value
        projects = projects_result.value if not projects_result.is_error else []
        assignees = assignees_result.value if not assignees_result.is_error else []

        # Render the appropriate view content
        if view == "create":
            view_content = TasksViewComponents.render_create_view(
                projects=projects,
                existing_tasks=tasks,
                user_uid=user_uid,
            )
        elif view == "calendar":
            # Get all user's tasks (not filtered by status) for calendar
            all_tasks_result = await get_all_tasks(user_uid)
            if all_tasks_result.is_error:
                view_content = ErrorComponents.render_error_banner(
                    f"Unable to load calendar: {all_tasks_result.error}"
                )
            else:
                view_content = TasksViewComponents.render_calendar_view(
                    tasks=all_tasks_result.value,
                    current_date=calendar_params.current_date,
                    calendar_view=calendar_params.calendar_view,
                )
        else:  # list (default)
            view_content = TasksViewComponents.render_list_view(
                tasks=tasks,
                filters={
                    "project": filters.project,
                    "assignee": filters.assignee,
                    "due": filters.due_filter,
                    "status": filters.status_filter,
                    "sort_by": filters.sort_by,
                },
                stats=stats,
                projects=projects,
                assignees=assignees,
                user_uid=user_uid,
            )

        # Build page with tabs + view content
        page_content = Div(
            TasksViewComponents.render_view_tabs(active_view=view),
            Div(view_content, id="view-content", role="tabpanel"),
            cls=f"{Spacing.PAGE} {Container.WIDE}",
        )

        return create_tasks_page(page_content, user_uid)

    # ========================================================================
    # HTMX VIEW FRAGMENTS
    # ========================================================================

    @rt("/tasks/view/list")
    async def tasks_view_list(request) -> Any:
        """HTMX fragment for list view."""
        user_uid = require_authenticated_user(request)

        # Get filter params
        filters = parse_filters(request)

        # Get data
        filtered_result = await get_filtered_tasks(
            user_uid,
            filters.project or None,
            filters.assignee or None,
            filters.due_filter or None,
            filters.status_filter,
            filters.sort_by,
        )
        projects_result = await get_distinct_projects(user_uid)
        assignees_result = await get_distinct_assignees(user_uid)

        # Handle errors
        if filtered_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load tasks")

        tasks, stats = filtered_result.value
        projects = projects_result.value if not projects_result.is_error else []
        assignees = assignees_result.value if not assignees_result.is_error else []

        return TasksViewComponents.render_list_view(
            tasks=tasks,
            filters={
                "project": filters.project,
                "assignee": filters.assignee,
                "due": filters.due_filter,
                "status": filters.status_filter,
                "sort_by": filters.sort_by,
            },
            stats=stats,
            projects=projects,
            assignees=assignees,
            user_uid=user_uid,
        )

    @rt("/tasks/view/create")
    async def tasks_view_create(request) -> Any:
        """HTMX fragment for create view."""
        user_uid = require_authenticated_user(request)

        tasks_result = await get_all_tasks(user_uid)
        projects_result = await get_distinct_projects(user_uid)

        # Handle errors
        if tasks_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load tasks")

        tasks = tasks_result.value
        projects = projects_result.value if not projects_result.is_error else []

        return TasksViewComponents.render_create_view(
            projects=projects,
            existing_tasks=tasks,
            user_uid=user_uid,
        )

    @rt("/tasks/view/calendar")
    async def tasks_view_calendar(request) -> Any:
        """HTMX fragment for calendar view with Month/Week/Day sub-views."""
        user_uid = require_authenticated_user(request)

        # Get calendar params
        calendar_params = parse_calendar_params(request)

        # Get all user's tasks for calendar (not filtered by status)
        tasks_result = await get_all_tasks(user_uid)

        # Handle errors
        if tasks_result.is_error:
            return ErrorComponents.render_error_banner("Unable to load calendar")

        return TasksViewComponents.render_calendar_view(
            tasks=tasks_result.value,
            current_date=calendar_params.current_date,
            calendar_view=calendar_params.calendar_view,
        )

    # ========================================================================
    # HTMX FRAGMENTS
    # ========================================================================

    @rt("/tasks/list-fragment")
    async def tasks_list_fragment(request) -> Any:
        """Return filtered task list for HTMX updates."""
        user_uid = require_authenticated_user(request)

        # Get filter params
        filters = parse_filters(request)

        # Get filtered tasks
        filtered_result = await get_filtered_tasks(
            user_uid,
            filters.project or None,
            filters.assignee or None,
            filters.due_filter or None,
            filters.status_filter,
            filters.sort_by,
        )

        # Handle errors
        if filtered_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load tasks")

        tasks, _stats = filtered_result.value
        return TodoistTaskComponents.render_task_list(tasks, user_uid)

    # ========================================================================
    # QUICK ADD (via QuickAddRouteFactory)
    # ========================================================================

    async def create_task_from_form(form_data: dict[str, Any], user_uid: str) -> Result[Any]:
        """
        Domain-specific task creation logic.

        Handles form parsing, request building, and service call.
        """
        # VALIDATE EARLY
        validation_result = validate_task_form_data(form_data)
        if validation_result.is_error:
            return validation_result  # Return validation error to UI

        # Extract form data
        title = form_data.get("title", "").strip()
        description = form_data.get("description", "").strip() or None
        project = form_data.get("project", "").strip() or None
        assignee = form_data.get("assignee", "").strip() or None
        priority_str = form_data.get("priority", "medium")
        scheduled_date_str = form_data.get("scheduled_date", "")
        due_date_str = form_data.get("due_date", "")

        # New fields: parent_uid, recurrence_pattern, recurrence_end_date
        parent_uid = form_data.get("parent_uid", "").strip() or None
        recurrence_pattern_str = form_data.get("recurrence_pattern", "")
        recurrence_end_date_str = form_data.get("recurrence_end_date", "")

        # Parse priority
        try:
            priority = Priority(priority_str)
        except ValueError:
            priority = Priority.MEDIUM

        # Parse recurrence pattern
        recurrence_pattern = None
        if recurrence_pattern_str:
            with contextlib.suppress(ValueError):
                recurrence_pattern = RecurrencePattern(recurrence_pattern_str)

        # Parse dates
        scheduled_date = None
        due_date = None
        recurrence_end_date = None
        if scheduled_date_str:
            with contextlib.suppress(ValueError):
                scheduled_date = date.fromisoformat(scheduled_date_str)
        if due_date_str:
            with contextlib.suppress(ValueError):
                due_date = date.fromisoformat(due_date_str)
        if recurrence_end_date_str:
            with contextlib.suppress(ValueError):
                recurrence_end_date = date.fromisoformat(recurrence_end_date_str)

        # Build request and call service
        create_request = TaskCreateRequest(
            title=title,
            description=description,
            project=project,
            assignee=assignee,
            priority=priority,
            scheduled_date=scheduled_date,
            due_date=due_date,
            status=ActivityStatus.DRAFT,
            parent_uid=parent_uid,
            recurrence_pattern=recurrence_pattern,
            recurrence_end_date=recurrence_end_date,
        )

        return await tasks_service.create_task(create_request, user_uid)

    async def render_task_success_view(user_uid: str) -> Any:
        """Render list view after successful task creation."""
        filtered_result = await get_filtered_tasks(user_uid, None, None, None, "active", "due_date")
        projects_result = await get_distinct_projects(user_uid)
        assignees_result = await get_distinct_assignees(user_uid)

        # Handle errors
        if filtered_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load tasks")

        all_tasks, stats = filtered_result.value
        projects = projects_result.value if not projects_result.is_error else []
        assignees = assignees_result.value if not assignees_result.is_error else []

        return TasksViewComponents.render_list_view(
            tasks=all_tasks,
            filters={},
            stats=stats,
            projects=projects,
            assignees=assignees,
            user_uid=user_uid,
        )

    async def render_task_add_another_view(user_uid: str) -> Any:
        """Render create view for add-another flow."""
        tasks_result = await get_all_tasks(user_uid)
        projects_result = await get_distinct_projects(user_uid)

        # Handle errors
        if tasks_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load tasks")

        tasks = tasks_result.value
        projects = projects_result.value if not projects_result.is_error else []

        return TasksViewComponents.render_create_view(
            projects=projects,
            existing_tasks=tasks,
            user_uid=user_uid,
        )

    # Register quick-add route via factory
    tasks_quick_add_config = QuickAddConfig(
        domain_name="tasks",
        required_field="title",
        create_entity=create_task_from_form,
        render_success_view=render_task_success_view,
        render_add_another_view=render_task_add_another_view,
    )
    QuickAddRouteFactory.register_route(rt, tasks_quick_add_config)

    # ========================================================================
    # TOGGLE COMPLETION
    # ========================================================================

    @rt("/tasks/{uid}/toggle", methods=["POST"])
    async def toggle_task_completion(request, uid: str) -> Any:
        """Toggle task completion status."""
        user_uid = require_authenticated_user(request)

        try:
            # Ownership verification before mutation
            get_result = await tasks_service.core.verify_ownership(uid, user_uid)
            if get_result.is_error:
                return Response("Task not found", status_code=404)

            task = get_result.value

            # Toggle status
            if task.status == ActivityStatus.COMPLETED:
                new_status = ActivityStatus.IN_PROGRESS
            else:
                new_status = ActivityStatus.COMPLETED

            # Update task
            update_result = await tasks_service.update_task(uid, {"status": new_status})
            if update_result.is_error:
                return render_safe_error_response(
                    user_message="Failed to update task status",
                    error_context=update_result.error,
                    logger_instance=logger,
                    log_extra={"task_uid": uid, "user_uid": user_uid},
                    status_code=500,
                )

            updated_task = update_result.value
            return TodoistTaskComponents.render_task_item(updated_task, user_uid)

        except Exception as e:
            logger.error(
                "Error toggling task - returning 500",
                extra={
                    "task_uid": uid,
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Response(f"Error: {e}", status_code=500)

    # ========================================================================
    # AUTOCOMPLETE
    # ========================================================================

    @rt("/tasks/autocomplete/projects")
    async def autocomplete_projects(request) -> Any:
        """Return project suggestions for autocomplete."""
        user_uid = require_authenticated_user(request)
        query = request.query_params.get("q", "").lower()

        projects_result = await get_distinct_projects(user_uid)

        # Graceful degradation: fall back to empty list for autocomplete
        projects = projects_result.value if not projects_result.is_error else []

        if query:
            projects = [p for p in projects if query in p.lower()]

        return JSONResponse(projects[:10])

    @rt("/tasks/autocomplete/assignees")
    async def autocomplete_assignees(request) -> Any:
        """Return assignee suggestions for autocomplete."""
        user_uid = require_authenticated_user(request)
        query = request.query_params.get("q", "").lower()

        assignees_result = await get_distinct_assignees(user_uid)

        # Graceful degradation: fall back to empty list for autocomplete
        assignees = assignees_result.value if not assignees_result.is_error else []

        if query:
            assignees = [a for a in assignees if query in a.lower()]

        return JSONResponse(assignees[:10])

    # ========================================================================
    # TASK EDIT MODAL
    # ========================================================================

    @rt("/tasks/edit-modal")
    async def get_task_edit_modal(request) -> Any:
        """Load task edit modal via HTMX."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")

        if not uid:
            return Response("Task UID required", status_code=400)

        # Ownership verification - returns NotFound if user doesn't own this task
        get_result = await tasks_service.core.verify_ownership(uid, user_uid)
        if get_result.is_error:
            return Response("Task not found", status_code=404)

        task = get_result.value

        # Get projects for autocomplete
        projects_result = await get_distinct_projects(user_uid)
        projects = projects_result.value if not projects_result.is_error else []

        return TodoistTaskComponents.render_task_edit_modal(task, projects)

    @rt("/tasks/edit-save", methods=["POST"])
    async def update_task_route(request) -> Any:
        """Update task from edit modal form."""
        # Initialize before try block to prevent UnboundLocalError in exception handler
        user_uid = ""
        uid = ""

        try:
            user_uid = require_authenticated_user(request)
            uid = request.query_params.get("uid", "")

            if not uid:
                return Response("Task UID required", status_code=400)

            # Ownership verification before mutation
            ownership_result = await tasks_service.core.verify_ownership(uid, user_uid)
            if ownership_result.is_error:
                return Response("Task not found", status_code=404)

            form = await request.form()

            # Build update dict (only include non-empty fields)
            updates: dict[str, Any] = {}

            # Title (required)
            title = form.get("title", "").strip()
            if title:
                updates["title"] = title

            # Description (can be cleared)
            description = form.get("description", "").strip()
            updates["description"] = description if description else None

            # Parse dates
            due_date_str = form.get("due_date", "")
            if due_date_str:
                with contextlib.suppress(ValueError):
                    updates["due_date"] = date.fromisoformat(due_date_str)
            else:
                updates["due_date"] = None

            scheduled_date_str = form.get("scheduled_date", "")
            if scheduled_date_str:
                with contextlib.suppress(ValueError):
                    updates["scheduled_date"] = date.fromisoformat(scheduled_date_str)
            else:
                updates["scheduled_date"] = None

            # Parse duration
            duration_str = form.get("duration_minutes", "")
            if duration_str:
                with contextlib.suppress(ValueError):
                    duration = int(duration_str)
                    if 5 <= duration <= 480:
                        updates["duration_minutes"] = duration

            # Parse priority
            priority_str = form.get("priority", "")
            if priority_str:
                with contextlib.suppress(ValueError):
                    updates["priority"] = Priority(priority_str)

            # Parse status
            status_str = form.get("status", "")
            if status_str:
                with contextlib.suppress(ValueError):
                    updates["status"] = ActivityStatus(status_str)

            # Project (can be cleared)
            project = form.get("project", "").strip()
            updates["project"] = project if project else None

            # Tags (comma-separated to list)
            tags_str = form.get("tags", "").strip()
            if tags_str:
                updates["tags"] = [t.strip() for t in tags_str.split(",") if t.strip()]
            else:
                updates["tags"] = []

            logger.info(f"Updating task {uid} with: {updates}")

            # Update task
            update_result = await tasks_service.update_task(uid, updates)
            if update_result.is_error:
                return render_safe_error_response(
                    user_message="Failed to update task",
                    error_context=update_result.error,
                    logger_instance=logger,
                    log_extra={"task_uid": uid, "user_uid": user_uid},
                    status_code=500,
                )

            updated_task = update_result.value
            logger.info(f"Task updated successfully: {updated_task.uid}")

            # Return the updated task row for HTMX swap
            return TodoistTaskComponents.render_task_item(updated_task, user_uid)

        except Exception as e:
            logger.error(
                "Exception in update_task_route - returning 500",
                extra={
                    "task_uid": uid,
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True,
            )
            return Response("Error updating task", status_code=500)

    # ========================================================================
    # TASK DETAIL PAGE (Phase 5)
    # ========================================================================

    @rt("/tasks/{uid}")
    async def task_detail_view(request: Request, uid: str) -> Any:
        """
        Task detail view with full context and relationships.

        Phase 5: Shows task details plus lateral relationships visualization.
        """
        user_uid = require_authenticated_user(request)

        # Fetch task with ownership verification
        result = await tasks_service.get_for_user(uid, user_uid)

        if result.is_error:
            logger.error(f"Failed to get task {uid}: {result.error}")
            return BasePage(
                content=Card(
                    H2("Task Not Found", cls="text-xl font-bold text-error mb-4"),
                    P(f"Could not find task: {uid}", cls="text-base-content/70"),
                    Button(
                        "← Back to Tasks",
                        **{"hx-get": "/tasks", "hx-target": "body"},
                        variant=ButtonT.primary,
                        cls="mt-4",
                    ),
                    cls="p-6",
                ),
                title="Task Not Found",
                page_type=PageType.STANDARD,
                request=request,
                active_page="tasks",
            )

        task = result.value

        # Render detail page
        content = Div(
            # Header Card
            Card(
                H1(f"✓ {task.title}", cls="text-2xl font-bold mb-2"),
                P(task.description or "No description provided", cls="text-base-content/70 mb-4"),
                # Status and Priority badges
                Div(
                    Span(f"Status: {task.status.value}", cls="badge badge-info mr-2"),
                    Span(f"Priority: {task.priority.value}", cls="badge badge-warning mr-2"),
                    Span(f"Project: {task.project or 'None'}", cls="badge badge-ghost")
                    if task.project
                    else "",
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-6 mb-4",
            ),
            # Details Card
            Card(
                H2("📋 Task Details", cls="text-xl font-semibold mb-4"),
                Div(
                    # Due Date
                    (
                        Div(
                            P("Due Date:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                            P(str(task.due_date), cls="text-base-content mb-3"),
                            cls="mb-4",
                        )
                        if task.due_date
                        else Div()
                    ),
                    # Assignee
                    (
                        Div(
                            P("Assignee:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                            P(task.assignee or "Unassigned", cls="text-base-content mb-3"),
                            cls="mb-4",
                        )
                        if task.assignee
                        else Div()
                    ),
                    # Created Date
                    Div(
                        P("Created:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                        P(str(task.created_at)[:10], cls="text-base-content/60 text-sm"),
                        cls="mb-4",
                    ),
                    cls="space-y-2",
                ),
                cls="p-6 mb-4",
            ),
            # Actions Card
            Card(
                Div(
                    Button(
                        "← Back to Tasks",
                        **{"hx-get": "/tasks", "hx-target": "body"},
                        variant=ButtonT.ghost,
                        cls="mr-2",
                    ),
                    Button(
                        "✏️ Edit Task",
                        **{"hx-get": f"/tasks/{task.uid}/edit", "hx-target": "#modal"},
                        variant=ButtonT.primary,
                        cls="mr-2",
                    ),
                    Button(
                        "✓ Toggle Complete",
                        **{"hx-post": f"/tasks/{task.uid}/toggle", "hx-target": "body"},
                        variant=ButtonT.success
                        if task.status != ActivityStatus.COMPLETED
                        else ButtonT.ghost,
                    ),
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-4 mb-4",
            ),
            # Phase 5: Lateral Relationships Section
            EntityRelationshipsSection(
                entity_uid=task.uid,
                entity_type="tasks",
            ),
            cls=f"{Container.STANDARD} {Spacing.PAGE_PADDING}",
        )

        return BasePage(
            content=content,
            title=task.title,
            page_type=PageType.STANDARD,
            request=request,
            active_page="tasks",
        )

    logger.info("Three-view task routes registered (standalone)")

    return []  # Routes registered via @rt() decorators (no objects returned)
