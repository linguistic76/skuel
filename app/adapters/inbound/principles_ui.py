"""Principles UI routes.

Provides the read-focused principle list view at /principles and detail view
at /principles/detail. Principles are a gravity well — they show incoming
relationships from tasks, habits, choices, events, and goals.

Also registers the create / edit forms (``GET|POST /principles/create``,
``GET|POST /principles/edit``) which use ``ui/activities/principles_form.py`` to
render :class:`~ui.patterns.form_generator.FormGenerator`. Cross-domain UID
fields on Principle are list-typed and assigned via the detail-page relationship
picker, so no EntityPicker widgets are wired here.
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
from core.models.enums.principle_enums import AlignmentLevel
from core.models.principle.principle_request import PrincipleCreateRequest, PrincipleUpdateRequest
from core.utils.connection_configs import PRINCIPLE_CONNECTION_CONFIG
from core.utils.entity_filters import filter_principles
from core.utils.logging import get_logger
from ui.activities.filter_bar import FILTER_CONFIGS
from ui.activities.nav import (
    render_activity_sidebar_error,
    render_activity_sidebar_page,
)
from ui.activities.principles_form import PrincipleCreateForm, PrincipleEditForm
from ui.activities.principles_views import PrincipleDetailView, PrincipleList, PrincipleStatsBar
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.ports import ConnectionFetchOperations
    from core.services.principles_service import PrinciplesService

logger = get_logger("skuel.routes.principles_ui")


def create_principles_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    principles_service: PrinciplesService,
    connection_fetch_backend: ConnectionFetchOperations,
) -> list[Any]:
    """Register Principles UI routes (list/detail + create/edit forms)."""
    config = ActivityUIConfig(
        domain_name="principles",
        domain_singular="principle",
        page_title="Principles",
        filter_params=(
            ("status", "active"),
            ("category", "all"),
            ("strength", "all"),
            ("sort_by", "strength"),
        ),
        get_all=principles_service.get_user_principles,
        get_one=principles_service.get_principle,
        backend=connection_fetch_backend,
        filter_fn=filter_principles,
        connection_config=PRINCIPLE_CONNECTION_CONFIG,
        filter_config=FILTER_CONFIGS["principles"],
        list_component=PrincipleList,
        stats_component=PrincipleStatsBar,
        detail_component=PrincipleDetailView,
        create_href="/principles/create",
        dual_track_assess=principles_service.intelligence.assess_alignment_dual_track,
        dual_track_level_enum=AlignmentLevel,
        dual_track_label="Alignment",
        list_categories=principles_service.search.list_user_categories,
    )
    base_routes = create_activity_ui_routes(app, rt, config)

    @rt("/principles/create", methods=["GET"])
    def principle_create_page(request: Request) -> Any:
        """Render the new-principle form."""
        require_authenticated_user(request)
        content = Div(PageHeader("New Principle"), PrincipleCreateForm(), cls="space-y-6")
        return render_activity_sidebar_page(content, active="principles", request=request)

    @rt("/principles/create", methods=["POST"])
    @csrf_protected
    async def principle_create_submit(request: Request) -> Any:
        """Validate the form, create the principle, redirect to its detail page."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_form_body(request, PrincipleCreateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            content = Div(
                PageHeader("New Principle"),
                render_error_banner(err.display_message),
                PrincipleCreateForm(),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="principles", request=request)

        result = await principles_service.create_principle(parsed.value, user_uid)
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader("New Principle"),
                render_error_banner(err.display_message),
                PrincipleCreateForm(),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="principles", request=request)

        return RedirectResponse(f"/principles/detail?uid={result.value.uid}", status_code=303)

    @rt("/principles/edit", methods=["GET"])
    async def principle_edit_page(request: Request) -> Any:
        """Render the edit form prefilled from an existing principle."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_error(
                "Missing principle UID",
                active="principles",
                request=request,
            )

        result = await principles_service.get_principle(uid)
        if result.is_error or result.value.user_uid != user_uid:
            return render_activity_sidebar_error(
                "Principle not found",
                active="principles",
                request=request,
            )

        principle = result.value
        content = Div(
            PageHeader(f"Edit: {principle.title}"),
            PrincipleEditForm(principle),
            cls="space-y-6",
        )
        return render_activity_sidebar_page(content, active="principles", request=request)

    @rt("/principles/edit", methods=["POST"])
    @csrf_protected
    async def principle_edit_submit(request: Request) -> Any:
        """Validate the form, apply updates, redirect to the detail page."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_error(
                "Missing principle UID",
                active="principles",
                request=request,
            )

        existing = await principles_service.get_principle(uid)
        if existing.is_error or existing.value.user_uid != user_uid:
            return render_activity_sidebar_error(
                "Principle not found",
                active="principles",
                request=request,
            )
        principle = existing.value

        parsed = await parse_form_body(request, PrincipleUpdateRequest)
        if parsed.is_error:
            err = parsed.expect_error()
            content = Div(
                PageHeader(f"Edit: {principle.title}"),
                render_error_banner(err.display_message),
                PrincipleEditForm(principle),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="principles", request=request)

        # ADR-066: build the typed PrincipleUpdateIntent from explicitly-set fields only
        # (model_fields_set). Fields the user left blank stay UNSET and are not written, so
        # untouched columns are never clobbered — no ad-hoc "drop None" convention.
        intent = parsed.value.to_intent()

        result = await principles_service.update_principle(uid, intent)
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader(f"Edit: {principle.title}"),
                render_error_banner(err.display_message),
                PrincipleEditForm(principle),
                cls="space-y-6",
            )
            return render_activity_sidebar_page(content, active="principles", request=request)

        return RedirectResponse(f"/principles/detail?uid={uid}", status_code=303)

    return [
        *base_routes,
        principle_create_page,
        principle_create_submit,
        principle_edit_page,
        principle_edit_submit,
    ]
