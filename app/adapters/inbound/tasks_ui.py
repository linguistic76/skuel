"""Tasks UI routes.

Provides the read-focused task list view at /tasks and detail view at /tasks/detail.
Tasks enter via YAML upload; this UI shows them with status controls,
priority, cross-domain connections, and EntityRelationshipsSection.

Also registers the create / edit forms (``GET|POST /tasks/create``,
``GET|POST /tasks/edit``) which use ``ui/activities/tasks_form.py`` to render
:class:`~ui.patterns.form_generator.FormGenerator` with
:class:`~ui.patterns.entity_picker.EntityPicker` widgets for the three
cross-domain UID fields (``parent_uid``, ``fulfills_goal_uid``,
``reinforces_habit_uid``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div
from starlette.responses import RedirectResponse

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_form_body
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
from core.utils.connection_fetcher import TASK_CONNECTION_CONFIG
from core.utils.entity_filters import filter_tasks
from core.utils.logging import get_logger
from ui.activities.filter_bar import FILTER_CONFIGS
from ui.activities.nav import render_activity_sidebar_page
from ui.activities.tasks_form import TaskCreateForm, TaskEditForm
from ui.activities.tasks_views import TaskDetailView, TaskList, TaskStatsBar
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.tasks_service import TasksService

logger = get_logger("skuel.routes.tasks_ui")


def create_tasks_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksService,
    user_service: Any = None,  # kept for DomainRouteConfig signature compat
    goals_service: GoalsService | None = None,
    habits_service: HabitsService | None = None,
) -> list[Any]:
    """Register Tasks UI routes (list/detail + create/edit forms)."""
    config = ActivityUIConfig(
        domain_name="tasks",
        domain_singular="task",
        page_title="Tasks",
        filter_params=(("status", "active"), ("priority", "all"), ("sort_by", "priority")),
        get_all=tasks_service.get_user_tasks,
        get_one=tasks_service.get_task,
        backend=tasks_service.core.backend,
        filter_fn=filter_tasks,
        connection_config=TASK_CONNECTION_CONFIG,
        filter_config=FILTER_CONFIGS["tasks"],
        list_component=TaskList,
        stats_component=TaskStatsBar,
        detail_component=TaskDetailView,
    )
    base_routes = create_activity_ui_routes(app, rt, config)

    # ------------------------------------------------------------------
    # Create form: GET /tasks/create  +  POST /tasks/create
    # ------------------------------------------------------------------

    @rt("/tasks/create")
    async def task_create_page(request: Request) -> Any:
        """Render the new-task form."""
        require_authenticated_user(request)
        content = Div(
            PageHeader("New Task"),
            TaskCreateForm(),
            cls="space-y-6",
        )
        return await render_activity_sidebar_page(content, active="tasks", request=request)

    @rt("/tasks/create", methods=["POST"])
    async def task_create_submit(request: Request) -> Any:
        """Validate the form, create the task, redirect to its detail page."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_form_body(request, TaskCreateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            content = Div(
                PageHeader("New Task"),
                render_error_banner(err.display_message),
                TaskCreateForm(),
                cls="space-y-6",
            )
            return await render_activity_sidebar_page(content, active="tasks", request=request)

        result = await tasks_service.core.create_task(parsed.value, user_uid)
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader("New Task"),
                render_error_banner(err.display_message),
                TaskCreateForm(),
                cls="space-y-6",
            )
            return await render_activity_sidebar_page(content, active="tasks", request=request)

        return RedirectResponse(f"/tasks/detail?uid={result.value.uid}", status_code=303)

    # ------------------------------------------------------------------
    # Edit form: GET /tasks/edit?uid=...  +  POST /tasks/edit?uid=...
    # ------------------------------------------------------------------

    async def _resolve_picker_titles(
        goal_uid: str | None, habit_uid: str | None
    ) -> tuple[str | None, str | None]:
        """Look up titles for the goal/habit pickers' visible-input prefill."""
        goal_display: str | None = None
        habit_display: str | None = None

        if goal_uid and goals_service is not None:
            goal_result = await goals_service.get_goal(goal_uid)
            if goal_result.is_ok:
                goal_display = goal_result.value.title

        if habit_uid and habits_service is not None:
            habit_result = await habits_service.get_habit(habit_uid)
            if habit_result.is_ok:
                habit_display = habit_result.value.title

        return goal_display, habit_display

    @rt("/tasks/edit")
    async def task_edit_page(request: Request) -> Any:
        """Render the edit form prefilled from an existing task."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing task UID")),
                active="tasks",
                request=request,
            )

        result = await tasks_service.get_task(uid)
        if result.is_error or result.value.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Task not found")),
                active="tasks",
                request=request,
            )

        task = result.value
        goal_display, habit_display = await _resolve_picker_titles(
            task.fulfills_goal_uid, task.reinforces_habit_uid
        )

        content = Div(
            PageHeader(f"Edit: {task.title}"),
            TaskEditForm(task, goal_display=goal_display, habit_display=habit_display),
            cls="space-y-6",
        )
        return await render_activity_sidebar_page(content, active="tasks", request=request)

    @rt("/tasks/edit", methods=["POST"])
    async def task_edit_submit(request: Request) -> Any:
        """Validate the form, apply updates, redirect to the detail page."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing task UID")),
                active="tasks",
                request=request,
            )

        existing = await tasks_service.get_task(uid)
        if existing.is_error or existing.value.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Task not found")),
                active="tasks",
                request=request,
            )
        task = existing.value

        parsed = await parse_form_body(request, TaskUpdateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            goal_display, habit_display = await _resolve_picker_titles(
                task.fulfills_goal_uid, task.reinforces_habit_uid
            )
            content = Div(
                PageHeader(f"Edit: {task.title}"),
                render_error_banner(err.display_message),
                TaskEditForm(task, goal_display=goal_display, habit_display=habit_display),
                cls="space-y-6",
            )
            return await render_activity_sidebar_page(content, active="tasks", request=request)

        # Drop None values: TaskUpdateRequest fields are all optional, and the
        # backend update applies whatever keys are present. Sending None for
        # fields the user left blank would clobber valid existing values.
        updates = {k: v for k, v in parsed.value.model_dump().items() if v is not None}

        result = await tasks_service.update_task(uid, updates)
        if result.is_error:
            err = result.expect_error()
            goal_display, habit_display = await _resolve_picker_titles(
                task.fulfills_goal_uid, task.reinforces_habit_uid
            )
            content = Div(
                PageHeader(f"Edit: {task.title}"),
                render_error_banner(err.display_message),
                TaskEditForm(task, goal_display=goal_display, habit_display=habit_display),
                cls="space-y-6",
            )
            return await render_activity_sidebar_page(content, active="tasks", request=request)

        return RedirectResponse(f"/tasks/detail?uid={uid}", status_code=303)

    return [
        *base_routes,
        task_create_page,
        task_create_submit,
        task_edit_page,
        task_edit_submit,
    ]
