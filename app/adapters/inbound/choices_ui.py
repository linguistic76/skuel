"""Choices UI routes.

Provides the read-focused choice list view at /choices and detail view at /choices/detail.
Choices enter via YAML upload OR the create form; this UI shows them with status controls,
decision framework, options, cross-domain connections, and EntityRelationshipsSection.

Also registers the create / edit forms (``GET|POST /choices/create``,
``GET|POST /choices/edit``) which use ``ui/activities/choices_form.py`` to render
:class:`~ui.patterns.form_generator.FormGenerator`. ChoiceCreateRequest exposes no
single-UID cross-domain fields; nested options and list fields are added on the
detail page rather than at create time.
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
from core.models.choice.choice_request import ChoiceCreateRequest, ChoiceUpdateRequest
from core.utils.connection_configs import CHOICE_CONNECTION_CONFIG
from core.utils.entity_filters import filter_choices
from core.utils.logging import get_logger
from ui.activities.choices_form import ChoiceCreateForm, ChoiceEditForm
from ui.activities.choices_views import ChoiceDetailView, ChoiceList, ChoiceStatsBar
from ui.activities.filter_bar import FILTER_CONFIGS
from ui.activities.nav import render_activity_sidebar_page
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.ports import ConnectionFetchOperations
    from core.services.choices_service import ChoicesService

logger = get_logger("skuel.routes.choices_ui")


def create_choices_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    choices_service: ChoicesService,
    connection_fetch_backend: ConnectionFetchOperations,
) -> list[Any]:
    """Register Choices UI routes (list/detail + create/edit forms)."""
    config = ActivityUIConfig(
        domain_name="choices",
        domain_singular="choice",
        page_title="Choices",
        filter_params=(("status", "pending"), ("sort_by", "deadline")),
        get_all=choices_service.get_user_choices,
        get_one=choices_service.get_choice,
        backend=connection_fetch_backend,
        filter_fn=filter_choices,
        connection_config=CHOICE_CONNECTION_CONFIG,
        filter_config=FILTER_CONFIGS["choices"],
        list_component=ChoiceList,
        stats_component=ChoiceStatsBar,
        detail_component=ChoiceDetailView,
        create_href="/choices/create",
    )
    base_routes = create_activity_ui_routes(app, rt, config)

    @rt("/choices/create", methods=["GET"])
    def choice_create_page(request: Request) -> Any:
        """Render the new-choice form."""
        require_authenticated_user(request)
        content = Div(PageHeader("New Choice"), ChoiceCreateForm(), cls="space-y-6")
        return render_activity_sidebar_page(content, active="choices", request=request)

    @rt("/choices/create", methods=["POST"])
    @csrf_protected
    async def choice_create_submit(request: Request) -> Any:
        """Validate the form, create the choice, redirect to its detail page."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_form_body(request, ChoiceCreateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            content = Div(
                PageHeader("New Choice"),
                render_error_banner(err.display_message),
                ChoiceCreateForm(),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="choices", request=request)

        result = await choices_service.create_choice(parsed.value, user_uid)
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader("New Choice"),
                render_error_banner(err.display_message),
                ChoiceCreateForm(),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="choices", request=request)

        return RedirectResponse(f"/choices/detail?uid={result.value.uid}", status_code=303)

    @rt("/choices/edit", methods=["GET"])
    async def choice_edit_page(request: Request) -> Any:
        """Render the edit form prefilled from an existing choice."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Missing choice UID")),
                active="choices",
                request=request,
            )

        result = await choices_service.get_choice(uid)
        if result.is_error or result.value.user_uid != user_uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Choice not found")),
                active="choices",
                request=request,
            )

        choice = result.value
        content = Div(
            PageHeader(f"Edit: {choice.title}"),
            ChoiceEditForm(choice),
            cls="space-y-6",
        )
        return render_activity_sidebar_page(content, active="choices", request=request)

    @rt("/choices/edit", methods=["POST"])
    @csrf_protected
    async def choice_edit_submit(request: Request) -> Any:
        """Validate the form, apply updates, redirect to the detail page."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Missing choice UID")),
                active="choices",
                request=request,
            )

        existing = await choices_service.get_choice(uid)
        if existing.is_error or existing.value.user_uid != user_uid:
            return render_activity_sidebar_page(
                Div(render_error_banner("Choice not found")),
                active="choices",
                request=request,
            )
        choice = existing.value

        parsed = await parse_form_body(request, ChoiceUpdateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            content = Div(
                PageHeader(f"Edit: {choice.title}"),
                render_error_banner(err.display_message),
                ChoiceEditForm(choice),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="choices", request=request)

        # ADR-066: build the typed ChoiceUpdateIntent from explicitly-set fields only
        # (model_fields_set). Fields the user left blank stay UNSET and are not written,
        # so untouched columns are never clobbered — no ad-hoc "drop None" convention.
        result = await choices_service.update_choice(uid, parsed.value.to_intent())
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader(f"Edit: {choice.title}"),
                render_error_banner(err.display_message),
                ChoiceEditForm(choice),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="choices", request=request)

        return RedirectResponse(f"/choices/detail?uid={uid}", status_code=303)

    return [
        *base_routes,
        choice_create_page,
        choice_create_submit,
        choice_edit_page,
        choice_edit_submit,
    ]
