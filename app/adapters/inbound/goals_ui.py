"""Goals UI routes.

Provides the read-focused goal list view at /goals and detail view at /goals/detail.
Goals are the gravity well — they show incoming relationships from tasks, habits,
events, choices, and principles.

Also registers the create / edit forms (``GET|POST /goals/create``,
``GET|POST /goals/edit``) which use ``ui/activities/goals_form.py`` to render
:class:`~ui.patterns.form_generator.FormGenerator`. The create form wires an
:class:`~ui.patterns.entity_picker.EntityPicker` for the ``parent_goal_uid``
field; ``GoalUpdateRequest`` exposes no cross-domain UID fields so the edit
form has no pickers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div
from starlette.responses import RedirectResponse

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_form_body
from core.models.goal.goal_request import GoalCreateRequest, GoalUpdateRequest
from core.utils.connection_fetcher import GOAL_CONNECTION_CONFIG
from core.utils.entity_filters import filter_goals
from core.utils.logging import get_logger
from ui.activities.filter_bar import FILTER_CONFIGS
from ui.activities.goals_form import GoalCreateForm, GoalEditForm
from ui.activities.goals_views import GoalDetailView, GoalList, GoalStatsBar
from ui.activities.nav import render_activity_sidebar_page
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.goals_service import GoalsService

logger = get_logger("skuel.routes.goals_ui")


def create_goals_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    goals_service: GoalsService,
) -> list[Any]:
    """Register Goals UI routes (list/detail + create/edit forms)."""
    config = ActivityUIConfig(
        domain_name="goals",
        domain_singular="goal",
        page_title="Goals",
        filter_params=(("status", "active"), ("sort_by", "target_date")),
        get_all=goals_service.get_user_goals,
        get_one=goals_service.get_goal,
        backend=goals_service.core.backend,
        filter_fn=filter_goals,
        connection_config=GOAL_CONNECTION_CONFIG,
        filter_config=FILTER_CONFIGS["goals"],
        list_component=GoalList,
        stats_component=GoalStatsBar,
        detail_component=GoalDetailView,
        create_href="/goals/create",
    )
    base_routes = create_activity_ui_routes(app, rt, config)

    # ------------------------------------------------------------------
    # Create form: GET /goals/create  +  POST /goals/create
    # ------------------------------------------------------------------

    @rt("/goals/create")
    async def goal_create_page(request: Request) -> Any:
        """Render the new-goal form."""
        require_authenticated_user(request)
        content = Div(
            PageHeader("New Goal"),
            GoalCreateForm(),
            cls="space-y-6",
        )
        return await render_activity_sidebar_page(content, active="goals", request=request)

    @rt("/goals/create", methods=["POST"])
    async def goal_create_submit(request: Request) -> Any:
        """Validate the form, create the goal, redirect to its detail page."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_form_body(request, GoalCreateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            content = Div(
                PageHeader("New Goal"),
                render_error_banner(err.display_message),
                GoalCreateForm(),
                cls="space-y-6",
            )
            return await render_activity_sidebar_page(content, active="goals", request=request)

        result = await goals_service.core.create_goal(parsed.value, user_uid)
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader("New Goal"),
                render_error_banner(err.display_message),
                GoalCreateForm(),
                cls="space-y-6",
            )
            return await render_activity_sidebar_page(content, active="goals", request=request)

        return RedirectResponse(f"/goals/detail?uid={result.value.uid}", status_code=303)

    # ------------------------------------------------------------------
    # Edit form: GET /goals/edit?uid=...  +  POST /goals/edit?uid=...
    # ------------------------------------------------------------------

    @rt("/goals/edit")
    async def goal_edit_page(request: Request) -> Any:
        """Render the edit form prefilled from an existing goal."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing goal UID")),
                active="goals",
                request=request,
            )

        result = await goals_service.get_goal(uid)
        if result.is_error or result.value.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Goal not found")),
                active="goals",
                request=request,
            )

        goal = result.value
        content = Div(
            PageHeader(f"Edit: {goal.title}"),
            GoalEditForm(goal),
            cls="space-y-6",
        )
        return await render_activity_sidebar_page(content, active="goals", request=request)

    @rt("/goals/edit", methods=["POST"])
    async def goal_edit_submit(request: Request) -> Any:
        """Validate the form, apply updates, redirect to the detail page."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing goal UID")),
                active="goals",
                request=request,
            )

        existing = await goals_service.get_goal(uid)
        if existing.is_error or existing.value.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Goal not found")),
                active="goals",
                request=request,
            )
        goal = existing.value

        parsed = await parse_form_body(request, GoalUpdateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            content = Div(
                PageHeader(f"Edit: {goal.title}"),
                render_error_banner(err.display_message),
                GoalEditForm(goal),
                cls="space-y-6",
            )
            return await render_activity_sidebar_page(content, active="goals", request=request)

        # Drop None values: GoalUpdateRequest fields are all optional, and the
        # backend update applies whatever keys are present. Sending None for
        # fields the user left blank would clobber valid existing values.
        updates = {k: v for k, v in parsed.value.model_dump().items() if v is not None}

        result = await goals_service.core.update(uid, updates)
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader(f"Edit: {goal.title}"),
                render_error_banner(err.display_message),
                GoalEditForm(goal),
                cls="space-y-6",
            )
            return await render_activity_sidebar_page(content, active="goals", request=request)

        return RedirectResponse(f"/goals/detail?uid={uid}", status_code=303)

    return [
        *base_routes,
        goal_create_page,
        goal_create_submit,
        goal_edit_page,
        goal_edit_submit,
    ]
