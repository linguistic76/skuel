"""Habits UI routes.

Provides the read-focused habit list view at /habits and detail view at /habits/detail.
Habits enter via YAML upload OR through the create form; this UI shows them with status
controls, streaks, atomic habits, cross-domain connections, and EntityRelationshipsSection.
The detail page also HTMX-loads two fragments: /habits/insights-fragment (Atomic Habits
pattern insights via HabitsPatternService.analyze_patterns) and /habits/choices-fragment
(Habit ↔ Choice lens via INFORMS_CHOICE / IMPACTS_HABIT edges).

Also registers the create / edit forms (``GET|POST /habits/create``,
``GET|POST /habits/edit``) which use ``ui/activities/habits_form.py`` to render
:class:`~ui.patterns.form_generator.FormGenerator`. HabitCreateRequest / HabitUpdateRequest
expose no single-UID cross-domain fields, so no EntityPicker widgets are wired.
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
from adapters.inbound.route_factories import require_owned_entity
from core.models.enums.activity_enums import ConsistencyLevel
from core.models.habit.habit_request import HabitCreateRequest, HabitUpdateRequest
from core.models.type_hints import EntityUID, UserUID
from core.utils.connection_configs import HABIT_CONNECTION_CONFIG
from core.utils.entity_filters import filter_habits
from core.utils.logging import get_logger
from ui.activities.filter_bar import FILTER_CONFIGS
from ui.activities.habits_form import HabitCreateForm, HabitEditForm
from ui.activities.habits_views import (
    HabitChoicesSection,
    HabitDetailView,
    HabitInsightsSection,
    HabitList,
    HabitStatsBar,
)
from ui.activities.nav import render_activity_sidebar_page
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.ports import ConnectionFetchOperations
    from core.ports.service_protocols import OwnershipVerifier
    from core.services.habits_service import HabitsService

logger = get_logger("skuel.routes.habits_ui")


def create_habits_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    habits_service: HabitsService,
    connection_fetch_backend: ConnectionFetchOperations,
    choices_ownership: OwnershipVerifier | None = None,
) -> list[Any]:
    """Register Habits UI routes (list/detail + create/edit forms).

    ``choices_ownership`` is an owner-scoped verifier for the Habit ↔ Choice
    fragment: the INFORMS_CHOICE / IMPACTS_HABIT edges can point at choices
    owned by *other* users, so each related choice is filtered through
    ``verify_ownership`` before render (USER_OWNED 404-not-403 invariant —
    a cross-user choice is invisible, never surfaced as a title + detail link).
    """
    config = ActivityUIConfig(
        domain_name="habits",
        domain_singular="habit",
        page_title="Habits",
        filter_params=(("status", "active"), ("category", "all"), ("sort_by", "streak")),
        get_all=habits_service.get_user_habits,
        get_one=habits_service.get_habit,
        backend=connection_fetch_backend,
        filter_fn=filter_habits,
        connection_config=HABIT_CONNECTION_CONFIG,
        filter_config=FILTER_CONFIGS["habits"],
        list_component=HabitList,
        stats_component=HabitStatsBar,
        detail_component=HabitDetailView,
        create_href="/habits/create",
        dual_track_assess=habits_service.intelligence.assess_consistency_dual_track,
        dual_track_level_enum=ConsistencyLevel,
        dual_track_label="Consistency",
        list_categories=habits_service.search.list_user_categories,
    )
    base_routes = create_activity_ui_routes(app, rt, config)

    @rt("/habits/insights-fragment")
    async def habit_insights_fragment(request: Request) -> Any:
        """HTMX fragment: Atomic Habits pattern insights for one habit.

        Ownership is enforced inside analyze_patterns (verify_ownership →
        404-shaped error for habits the user doesn't own).
        """
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Div(render_error_banner("Missing habit UID"), id="habit-insights")

        result = await habits_service.patterns.analyze_patterns(uid, user_uid)
        if result.is_error:
            return Div(render_error_banner("Habit not found"), id="habit-insights")

        return HabitInsightsSection(result.value)

    async def _owned_choices(
        choices: list[dict[str, Any]], user_uid: UserUID
    ) -> list[dict[str, Any]]:
        """Drop choices the requesting user doesn't own.

        The INFORMS_CHOICE / IMPACTS_HABIT traversal returns choices by edge
        only (no owner predicate), so a habit edged to another user's choice
        would otherwise leak that choice's title + detail link. Filter each
        through ``verify_ownership`` (404-shaped error ⇒ not owned ⇒ hidden).
        If no verifier is wired (degraded boot), fail closed: surface nothing.
        """
        if choices_ownership is None:
            return []
        owned: list[dict[str, Any]] = []
        for choice in choices:
            choice_uid = str(choice.get("uid", ""))
            if not choice_uid:
                continue
            ownership = await choices_ownership.verify_ownership(choice_uid, user_uid)
            if ownership.is_ok:
                owned.append(choice)
        return owned

    @rt("/habits/choices-fragment")
    async def habit_choices_fragment(request: Request) -> Any:
        """HTMX fragment: Habit ↔ Choice lens (informed + impacting choices).

        Resolves choice titles via relationship metadata (registry fields on
        INFORMS_CHOICE / IMPACTS_HABIT include uid + title). Each related choice
        is owner-scoped to the requesting user before render — choices are
        USER_OWNED, and the edge traversal carries no owner predicate, so a
        cross-user choice must never leak (404-not-403 invariant).
        """
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Div(render_error_banner("Missing habit UID"), id="habit-choices")

        # Ownership: 404-not-403 for habits the user doesn't own. Error banner
        # (not a bare 404 Response) so HTMX swaps the placeholder out.
        _habit, error = await require_owned_entity(habits_service.core, uid, user_uid, "Habit")
        if error:
            return Div(render_error_banner("Habit not found"), id="habit-choices")

        habit_uid = EntityUID(uid)
        informed = await habits_service.relationships.get_related_with_metadata(
            "informed_choices", habit_uid
        )
        impacting = await habits_service.relationships.get_related_with_metadata(
            "impacting_choices", habit_uid
        )
        return HabitChoicesSection(
            await _owned_choices(informed.value, user_uid) if informed.is_ok else [],
            await _owned_choices(impacting.value, user_uid) if impacting.is_ok else [],
        )

    @rt("/habits/create", methods=["GET"])
    def habit_create_page(request: Request) -> Any:
        """Render the new-habit form."""
        require_authenticated_user(request)
        content = Div(PageHeader("New Habit"), HabitCreateForm(), cls="space-y-6")
        return render_activity_sidebar_page(content, active="habits", request=request)

    @rt("/habits/create", methods=["POST"])
    @csrf_protected
    async def habit_create_submit(request: Request) -> Any:
        """Validate the form, create the habit, redirect to its detail page."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_form_body(request, HabitCreateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            content = Div(
                PageHeader("New Habit"),
                render_error_banner(err.display_message),
                HabitCreateForm(),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="habits", request=request)

        result = await habits_service.create_habit(parsed.value, user_uid)
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader("New Habit"),
                render_error_banner(err.display_message),
                HabitCreateForm(),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="habits", request=request)

        return RedirectResponse(f"/habits/detail?uid={result.value.uid}", status_code=303)

    @rt("/habits/edit", methods=["GET"])
    async def habit_edit_page(request: Request) -> Any:
        """Render the edit form prefilled from an existing habit."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Missing habit UID")),
                active="habits",
                request=request,
            )

        result = await habits_service.get_habit(uid)
        if result.is_error or result.value.user_uid != user_uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Habit not found")),
                active="habits",
                request=request,
            )

        habit = result.value
        content = Div(
            PageHeader(f"Edit: {habit.title}"),
            HabitEditForm(habit),
            cls="space-y-6",
        )
        return render_activity_sidebar_page(content, active="habits", request=request)

    @rt("/habits/edit", methods=["POST"])
    @csrf_protected
    async def habit_edit_submit(request: Request) -> Any:
        """Validate the form, apply updates, redirect to the detail page."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Missing habit UID")),
                active="habits",
                request=request,
            )

        existing = await habits_service.get_habit(uid)
        if existing.is_error or existing.value.user_uid != user_uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Habit not found")),
                active="habits",
                request=request,
            )
        habit = existing.value

        parsed = await parse_form_body(request, HabitUpdateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            content = Div(
                PageHeader(f"Edit: {habit.title}"),
                render_error_banner(err.display_message),
                HabitEditForm(habit),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="habits", request=request)

        # ADR-066: build the typed HabitUpdateIntent from explicitly-set fields only
        # (model_fields_set). Fields the user left blank stay UNSET and are not written,
        # so untouched columns are never clobbered — no ad-hoc "drop None" convention.
        result = await habits_service.update_habit(uid, parsed.value.to_intent())
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader(f"Edit: {habit.title}"),
                render_error_banner(err.display_message),
                HabitEditForm(habit),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="habits", request=request)

        return RedirectResponse(f"/habits/detail?uid={uid}", status_code=303)

    return [
        *base_routes,
        habit_insights_fragment,
        habit_choices_fragment,
        habit_create_page,
        habit_create_submit,
        habit_edit_page,
        habit_edit_submit,
    ]
