"""Principles UI routes.

Provides the read-focused principle list view at /principles and detail view
at /principles/detail. The detail page and the cards list the principle's links in
both directions, under the principle's names for them (the registry's page views,
ADR-090 §2). The detail page also HTMX-loads /principles/choice-outcomes: how the
choices the principle informs turned out (``PrincipleChoiceOutcomes``).

Also registers the create / edit forms (``GET|POST /principles/create``,
``GET|POST /principles/edit``) which use ``ui/activities/principles_form.py`` to
render :class:`~ui.patterns.form_generator.FormGenerator`. Cross-domain UID
fields on Principle are list-typed and assigned via the detail-page relationship
picker, so no EntityPicker widgets are wired here.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from fasthtml.common import FT, Div, FtResponse
from starlette.responses import RedirectResponse

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_form_body
from adapters.inbound.route_factories import refuse, refuse_not_found
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.principle_enums import AlignmentLevel
from core.models.principle.principle_request import PrincipleCreateRequest, PrincipleUpdateRequest
from core.utils.entity_filters import filter_principles
from core.utils.logging import get_logger
from ui.activities.filter_bar import FILTER_CONFIGS
from ui.activities.nav import (
    render_activity_sidebar_error,
    render_activity_sidebar_page,
)
from ui.activities.principles_form import PrincipleCreateForm, PrincipleEditForm
from ui.activities.principles_views import (
    CHOICE_OUTCOMES_SLOT,
    PrincipleChoiceOutcomesSection,
    PrincipleDetailView,
    PrincipleList,
    PrincipleStatsBar,
)
from ui.layouts.base_page import HtmlDocument
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner, render_slot_error

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import RouteDecorator
    from core.ports import ConnectionFetchOperations
    from core.services.principles_service import PrinciplesService

logger = get_logger("skuel.routes.principles_ui")


def create_principles_ui_routes(
    rt: RouteDecorator,
    principles_service: PrinciplesService,
    connection_fetch_backend: ConnectionFetchOperations,
) -> None:
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
        get_owned=principles_service.verify_ownership,
        backend=connection_fetch_backend,
        filter_fn=filter_principles,
        link_label=NeoLabel.PRINCIPLE,
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
    create_activity_ui_routes(rt, config)

    @rt("/principles/choice-outcomes")
    async def principle_choice_outcomes_fragment(request: Request) -> FT | FtResponse:
        """HTMX fragment: how the choices one principle informs turned out.

        A foreign or missing principle answers the slot's 404, a failed read its own
        status (``refuse``).
        """
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        slot = partial(render_slot_error, CHOICE_OUTCOMES_SLOT)
        if not uid:
            return refuse_not_found(slot("Missing principle UID"))

        owned = await principles_service.verify_ownership(uid, user_uid)
        if owned.is_error:
            return refuse(owned.expect_error(), slot, "Principle")

        outcomes = await principles_service.get_choice_guidance_effectiveness(uid, user_uid)
        if outcomes.is_error:
            return refuse(outcomes.expect_error(), slot, "Principle")
        return PrincipleChoiceOutcomesSection(outcomes.value)

    @rt("/principles/create", methods=["GET"])
    def principle_create_page(request: Request) -> HtmlDocument:
        """Render the new-principle form."""
        require_authenticated_user(request)
        content = Div(PageHeader("New Principle"), PrincipleCreateForm(), cls="space-y-6")
        return render_activity_sidebar_page(content, active="principles", request=request)

    @rt("/principles/create", methods=["POST"])
    @csrf_protected
    async def principle_create_submit(request: Request) -> HtmlDocument | RedirectResponse:
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
    async def principle_edit_page(request: Request) -> HtmlDocument | FtResponse:
        """Render the edit form prefilled from an existing principle."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_error(
                "Missing principle UID",
                active="principles",
                request=request,
            )

        owned = await principles_service.verify_ownership(uid, user_uid)
        if owned.is_error:
            return refuse(
                owned.expect_error(),
                partial(render_activity_sidebar_error, active="principles", request=request),
                "Principle",
            )
        principle = owned.value

        content = Div(
            PageHeader(f"Edit: {principle.title}"),
            PrincipleEditForm(principle),
            cls="space-y-6",
        )
        return render_activity_sidebar_page(content, active="principles", request=request)

    @rt("/principles/edit", methods=["POST"])
    @csrf_protected
    async def principle_edit_submit(
        request: Request,
    ) -> HtmlDocument | FtResponse | RedirectResponse:
        """Validate the form, apply updates, redirect to the detail page."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_error(
                "Missing principle UID",
                active="principles",
                request=request,
            )

        owned = await principles_service.verify_ownership(uid, user_uid)
        if owned.is_error:
            return refuse(
                owned.expect_error(),
                partial(render_activity_sidebar_error, active="principles", request=request),
                "Principle",
            )
        principle = owned.value

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
