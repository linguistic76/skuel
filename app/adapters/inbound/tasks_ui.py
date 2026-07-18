"""Tasks UI routes.

Provides the read-focused task list view at /tasks and detail view at /tasks/detail.
Tasks enter via YAML upload; this UI shows them with status controls,
priority, cross-domain connections, and EntityRelationshipsSection.

Also registers the create / edit forms (``GET|POST /tasks/create``,
``GET|POST /tasks/edit``) which use ``ui/activities/tasks_form.py`` to render
:class:`~ui.patterns.form_generator.FormGenerator` with
:class:`~ui.patterns.entity_picker.EntityPicker` widgets for the cross-domain
pickers (``parent_uid``, ``fulfills_goal_uid``, and the habit picker). The habit
picker collects user input that the service routes to a
``(Task)-[:REINFORCES_HABIT]->(Habit)`` edge (graph-native, not a property).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div
from starlette.responses import RedirectResponse

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_form_body
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
from core.utils.connection_configs import TASK_CONNECTION_CONFIG
from core.utils.entity_filters import filter_tasks
from core.utils.logging import get_logger
from ui.activities.filter_bar import FILTER_CONFIGS
from ui.activities.nav import render_activity_sidebar_page
from ui.activities.tasks_form import TaskCreateForm, TaskEditForm
from ui.activities.tasks_views import (
    SubtaskListFragment,
    TaskDetailView,
    TaskList,
    TaskStatsBar,
)
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.ports import ConnectionFetchOperations
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.tasks_service import TasksService

logger = get_logger("skuel.routes.tasks_ui")


def create_tasks_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksService,
    connection_fetch_backend: ConnectionFetchOperations,
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
        backend=connection_fetch_backend,
        filter_fn=filter_tasks,
        connection_config=TASK_CONNECTION_CONFIG,
        filter_config=FILTER_CONFIGS["tasks"],
        list_component=TaskList,
        stats_component=TaskStatsBar,
        detail_component=TaskDetailView,
        create_href="/tasks/create",
    )
    base_routes = create_activity_ui_routes(app, rt, config)

    # ------------------------------------------------------------------
    # Create form: GET /tasks/create  +  POST /tasks/create
    # ------------------------------------------------------------------

    @rt("/tasks/create", methods=["GET"])
    def task_create_page(request: Request) -> Any:
        """Render the new-task form."""
        require_authenticated_user(request)
        content = Div(
            PageHeader("New Task"),
            TaskCreateForm(),
            cls="space-y-6",
        )
        return render_activity_sidebar_page(content, active="tasks", request=request)

    @rt("/tasks/create", methods=["POST"])
    @csrf_protected
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
            return render_activity_sidebar_page(content, active="tasks", request=request)

        result = await tasks_service.core.create_task(parsed.value, user_uid)
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader("New Task"),
                render_error_banner(err.display_message),
                TaskCreateForm(),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="tasks", request=request)

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

    @rt("/tasks/edit", methods=["GET"])
    async def task_edit_page(request: Request) -> Any:
        """Render the edit form prefilled from an existing task."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Missing task UID")),
                active="tasks",
                request=request,
            )

        result = await tasks_service.get_task(uid)
        if result.is_error or result.value.user_uid != user_uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Task not found")),
                active="tasks",
                request=request,
            )

        task = result.value
        reinforced = await tasks_service.get_reinforced_habit(task.uid)
        habit_uid = reinforced.value if reinforced.is_ok else None
        goal_display, habit_display = await _resolve_picker_titles(
            task.fulfills_goal_uid, habit_uid
        )

        content = Div(
            PageHeader(f"Edit: {task.title}"),
            TaskEditForm(
                task, goal_display=goal_display, habit_display=habit_display, habit_uid=habit_uid
            ),
            cls="space-y-6",
        )
        return render_activity_sidebar_page(content, active="tasks", request=request)

    @rt("/tasks/edit", methods=["POST"])
    @csrf_protected
    async def task_edit_submit(request: Request) -> Any:
        """Validate the form, apply updates, redirect to the detail page."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Missing task UID")),
                active="tasks",
                request=request,
            )

        existing = await tasks_service.get_task(uid)
        if existing.is_error or existing.value.user_uid != user_uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Task not found")),
                active="tasks",
                request=request,
            )
        task = existing.value
        reinforced = await tasks_service.get_reinforced_habit(task.uid)
        habit_uid = reinforced.value if reinforced.is_ok else None

        parsed = await parse_form_body(request, TaskUpdateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            goal_display, habit_display = await _resolve_picker_titles(
                task.fulfills_goal_uid, habit_uid
            )
            content = Div(
                PageHeader(f"Edit: {task.title}"),
                render_error_banner(err.display_message),
                TaskEditForm(
                    task,
                    goal_display=goal_display,
                    habit_display=habit_display,
                    habit_uid=habit_uid,
                ),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="tasks", request=request)

        # ADR-066: build the typed update intent from explicitly-set fields. Only fields
        # the form actually submitted become non-UNSET, so untouched fields are left alone
        # (an explicitly-cleared field clears; absent fields are not written).
        result = await tasks_service.update_task(uid, parsed.value.to_intent())
        if result.is_error:
            err = result.expect_error()
            goal_display, habit_display = await _resolve_picker_titles(
                task.fulfills_goal_uid, habit_uid
            )
            content = Div(
                PageHeader(f"Edit: {task.title}"),
                render_error_banner(err.display_message),
                TaskEditForm(
                    task,
                    goal_display=goal_display,
                    habit_display=habit_display,
                    habit_uid=habit_uid,
                ),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="tasks", request=request)

        return RedirectResponse(f"/tasks/detail?uid={uid}", status_code=303)

    # ------------------------------------------------------------------
    # Subtask fragments: GET /tasks/subtasks  +  POST /tasks/subtasks/add
    # ------------------------------------------------------------------

    @rt("/tasks/subtasks", methods=["GET"])
    async def subtasks_fragment(request: Request) -> Any:
        """HTMX fragment: parent breadcrumb + child rows + quick-add form."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return SubtaskListFragment(uid, None, [])

        task_result = await tasks_service.get_task(uid)
        if task_result.is_error or task_result.value.user_uid != user_uid:
            return SubtaskListFragment(uid, None, [])

        parent_result = await tasks_service.get_parent_task(uid)
        parent = (
            parent_result.value
            if parent_result.is_ok
            and parent_result.value is not None
            and parent_result.value.user_uid == user_uid
            else None
        )

        children_result = await tasks_service.get_subtasks(uid)
        children = (
            [t for t in children_result.value if t.user_uid == user_uid]
            if children_result.is_ok
            else []
        )

        return SubtaskListFragment(uid, parent, children)

    @rt("/tasks/subtasks/add", methods=["POST"])
    @csrf_protected
    async def subtasks_add(request: Request) -> Any:
        """Create a sub-task inline and return the refreshed subtask fragment."""
        user_uid = require_authenticated_user(request)

        form = await request.form()
        title = str(form.get("title", "")).strip()
        parent_uid = str(form.get("parent_uid", "")).strip()

        owner_result = await tasks_service.get_task(parent_uid)
        if owner_result.is_error or owner_result.value.user_uid != user_uid:
            return SubtaskListFragment(parent_uid, None, [])

        if title:
            create_req = TaskCreateRequest(title=title, parent_uid=parent_uid)
            await tasks_service.core.create_task(create_req, user_uid)

        grandparent_result = await tasks_service.get_parent_task(parent_uid)
        grandparent = (
            grandparent_result.value
            if grandparent_result.is_ok
            and grandparent_result.value is not None
            and grandparent_result.value.user_uid == user_uid
            else None
        )

        children_result = await tasks_service.get_subtasks(parent_uid)
        children = (
            [t for t in children_result.value if t.user_uid == user_uid]
            if children_result.is_ok
            else []
        )

        return SubtaskListFragment(parent_uid, grandparent, children)

    return [
        *base_routes,
        task_create_page,
        task_create_submit,
        task_edit_page,
        task_edit_submit,
        subtasks_fragment,
        subtasks_add,
    ]
