"""Events UI routes.

Provides the read-focused event list view at /events and detail view at /events/detail.
Events enter via YAML upload OR the create form; this UI shows them with status
controls, scheduling info, cross-domain connections, and EntityRelationshipsSection.

Also registers the create / edit forms (``GET|POST /events/create``,
``GET|POST /events/edit``) which use ``ui/activities/events_form.py`` to render
:class:`~ui.patterns.form_generator.FormGenerator` with
:class:`~ui.patterns.entity_picker.EntityPicker` widgets for the cross-domain
goal/habit pickers. The goal picker collects user input that the service routes
to a ``(Event)-[:CELEBRATES_GOAL]->(Goal)`` edge (graph-native, not a property).
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
from core.models.event.event_request import EventCreateRequest, EventUpdateRequest
from core.utils.connection_configs import EVENT_CONNECTION_CONFIG
from core.utils.entity_filters import filter_events
from core.utils.logging import get_logger
from ui.activities.events_form import EventCreateForm, EventEditForm
from ui.activities.events_views import EventDetailView, EventList, EventStatsBar
from ui.activities.filter_bar import FILTER_CONFIGS
from ui.activities.nav import (
    render_activity_sidebar_error,
    render_activity_sidebar_page,
)
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.ports import ConnectionFetchOperations
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService

logger = get_logger("skuel.routes.events_ui")


def create_events_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    events_service: EventsService,
    connection_fetch_backend: ConnectionFetchOperations,
    user_service: Any = None,  # kept for DomainRouteConfig signature compat
    goals_service: GoalsService | None = None,
    habits_service: HabitsService | None = None,
) -> list[Any]:
    """Register Events UI routes (list/detail + create/edit forms)."""
    config = ActivityUIConfig(
        domain_name="events",
        domain_singular="event",
        page_title="Events",
        filter_params=(("status", "upcoming"), ("sort_by", "date")),
        get_all=events_service.get_user_events,
        get_one=events_service.get_event,
        backend=connection_fetch_backend,
        filter_fn=filter_events,
        connection_config=EVENT_CONNECTION_CONFIG,
        filter_config=FILTER_CONFIGS["events"],
        list_component=EventList,
        stats_component=EventStatsBar,
        detail_component=EventDetailView,
        create_href="/events/create",
    )
    base_routes = create_activity_ui_routes(app, rt, config)

    async def _resolve_picker_titles(
        habit_uid: str | None, goal_uid: str | None
    ) -> tuple[str | None, str | None]:
        """Look up titles for the habit/goal pickers' visible-input prefill."""
        habit_display: str | None = None
        goal_display: str | None = None

        if habit_uid and habits_service is not None:
            habit_result = await habits_service.get_habit(habit_uid)
            if habit_result.is_ok:
                habit_display = habit_result.value.title

        if goal_uid and goals_service is not None:
            goal_result = await goals_service.get_goal(goal_uid)
            if goal_result.is_ok:
                goal_display = goal_result.value.title

        return habit_display, goal_display

    @rt("/events/create", methods=["GET"])
    def event_create_page(request: Request) -> Any:
        """Render the new-event form."""
        require_authenticated_user(request)
        content = Div(PageHeader("New Event"), EventCreateForm(), cls="space-y-6")
        return render_activity_sidebar_page(content, active="events", request=request)

    @rt("/events/create", methods=["POST"])
    @csrf_protected
    async def event_create_submit(request: Request) -> Any:
        """Validate the form, create the event, redirect to its detail page."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_form_body(request, EventCreateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            content = Div(
                PageHeader("New Event"),
                render_error_banner(err.display_message),
                EventCreateForm(),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="events", request=request)

        result = await events_service.create_event(parsed.value, user_uid)
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader("New Event"),
                render_error_banner(err.display_message),
                EventCreateForm(),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="events", request=request)

        return RedirectResponse(f"/events/detail?uid={result.value.uid}", status_code=303)

    @rt("/events/edit", methods=["GET"])
    async def event_edit_page(request: Request) -> Any:
        """Render the edit form prefilled from an existing event."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_error(
                "Missing event UID",
                active="events",
                request=request,
            )

        result = await events_service.get_event(uid)
        if result.is_error or result.value.user_uid != user_uid:
            return render_activity_sidebar_error(
                "Event not found",
                active="events",
                request=request,
            )

        event = result.value
        celebrated = await events_service.get_celebrated_goal(event.uid)
        goal_uid = celebrated.value if celebrated.is_ok else None
        reinforced = await events_service.get_reinforced_habit(event.uid)
        habit_uid = reinforced.value if reinforced.is_ok else None
        habit_display, goal_display = await _resolve_picker_titles(habit_uid, goal_uid)

        content = Div(
            PageHeader(f"Edit: {event.title}"),
            EventEditForm(
                event,
                habit_display=habit_display,
                goal_display=goal_display,
                goal_uid=goal_uid,
                habit_uid=habit_uid,
            ),
            cls="space-y-6",
        )
        return render_activity_sidebar_page(content, active="events", request=request)

    @rt("/events/edit", methods=["POST"])
    @csrf_protected
    async def event_edit_submit(request: Request) -> Any:
        """Validate the form, apply updates, redirect to the detail page."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_error(
                "Missing event UID",
                active="events",
                request=request,
            )

        existing = await events_service.get_event(uid)
        if existing.is_error or existing.value.user_uid != user_uid:
            return render_activity_sidebar_error(
                "Event not found",
                active="events",
                request=request,
            )
        event = existing.value
        celebrated = await events_service.get_celebrated_goal(event.uid)
        goal_uid = celebrated.value if celebrated.is_ok else None
        reinforced = await events_service.get_reinforced_habit(event.uid)
        habit_uid = reinforced.value if reinforced.is_ok else None

        parsed = await parse_form_body(request, EventUpdateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            habit_display, goal_display = await _resolve_picker_titles(habit_uid, goal_uid)
            content = Div(
                PageHeader(f"Edit: {event.title}"),
                render_error_banner(err.display_message),
                EventEditForm(
                    event,
                    habit_display=habit_display,
                    goal_display=goal_display,
                    goal_uid=goal_uid,
                    habit_uid=habit_uid,
                ),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="events", request=request)

        # ADR-066: build the typed EventUpdateIntent from explicitly-set fields only
        # (model_fields_set). A field the edit form does not render is absent from the body
        # and stays UNSET — untouched, never clobbered. A field the form DOES render posts
        # on every submit, and a blank one arrives as "" which parse_form_body maps to None:
        # an explicit clear. That is how the edge pickers are cleared — the facade splits
        # the CELEBRATES_GOAL / REINFORCES_HABIT edges off the intent and a None deletes
        # the edge. Pinned by tests/unit/adapters/test_edit_form_edge_clear.py.
        result = await events_service.update_event(uid, parsed.value.to_intent())
        if result.is_error:
            err = result.expect_error()
            habit_display, goal_display = await _resolve_picker_titles(habit_uid, goal_uid)
            content = Div(
                PageHeader(f"Edit: {event.title}"),
                render_error_banner(err.display_message),
                EventEditForm(
                    event,
                    habit_display=habit_display,
                    goal_display=goal_display,
                    goal_uid=goal_uid,
                    habit_uid=habit_uid,
                ),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="events", request=request)

        return RedirectResponse(f"/events/detail?uid={uid}", status_code=303)

    return [
        *base_routes,
        event_create_page,
        event_create_submit,
        event_edit_page,
        event_edit_submit,
    ]
