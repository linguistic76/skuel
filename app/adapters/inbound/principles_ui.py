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
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_form_body
from core.models.principle.principle_request import PrincipleCreateRequest, PrincipleUpdateRequest
from core.utils.connection_fetcher import PRINCIPLE_CONNECTION_CONFIG
from core.utils.entity_filters import filter_principles
from core.utils.logging import get_logger
from ui.activities.filter_bar import FILTER_CONFIGS
from ui.activities.nav import render_activity_sidebar_page
from ui.activities.principles_form import PrincipleCreateForm, PrincipleEditForm
from ui.activities.principles_views import PrincipleDetailView, PrincipleList, PrincipleStatsBar
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.principles_service import PrinciplesService

logger = get_logger("skuel.routes.principles_ui")


def create_principles_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    principles_service: PrinciplesService,
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
        backend=principles_service.core.backend,
        filter_fn=filter_principles,
        connection_config=PRINCIPLE_CONNECTION_CONFIG,
        filter_config=FILTER_CONFIGS["principles"],
        list_component=PrincipleList,
        stats_component=PrincipleStatsBar,
        detail_component=PrincipleDetailView,
        create_href="/principles/create",
    )
    base_routes = create_activity_ui_routes(app, rt, config)

    @rt("/principles/create")
    async def principle_create_page(request: Request) -> Any:
        """Render the new-principle form."""
        require_authenticated_user(request)
        content = Div(PageHeader("New Principle"), PrincipleCreateForm(), cls="space-y-6")
        return await render_activity_sidebar_page(content, active="principles", request=request)

    @rt("/principles/create", methods=["POST"])
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
            return await render_activity_sidebar_page(content, active="principles", request=request)

        result = await principles_service.create_principle(parsed.value, user_uid)
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader("New Principle"),
                render_error_banner(err.display_message),
                PrincipleCreateForm(),
                cls="space-y-6",
            )
            return await render_activity_sidebar_page(content, active="principles", request=request)

        return RedirectResponse(f"/principles/detail?uid={result.value.uid}", status_code=303)

    @rt("/principles/edit")
    async def principle_edit_page(request: Request) -> Any:
        """Render the edit form prefilled from an existing principle."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing principle UID")),
                active="principles",
                request=request,
            )

        result = await principles_service.get_principle(uid)
        if result.is_error or result.value.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Principle not found")),
                active="principles",
                request=request,
            )

        principle = result.value
        content = Div(
            PageHeader(f"Edit: {principle.title}"),
            PrincipleEditForm(principle),
            cls="space-y-6",
        )
        return await render_activity_sidebar_page(content, active="principles", request=request)

    @rt("/principles/edit", methods=["POST"])
    async def principle_edit_submit(request: Request) -> Any:
        """Validate the form, apply updates, redirect to the detail page."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing principle UID")),
                active="principles",
                request=request,
            )

        existing = await principles_service.get_principle(uid)
        if existing.is_error or existing.value.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Principle not found")),
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
            return await render_activity_sidebar_page(content, active="principles", request=request)

        # Drop None values and translate request field names to the domain model:
        # request uses ``category``/``source``; the Principle model uses
        # ``principle_category``/``principle_source``. ``why_important`` has no
        # dedicated field on the model — appended to description.
        raw = {k: v for k, v in parsed.value.model_dump().items() if v is not None}
        why_important = raw.pop("why_important", None)
        rename = {"category": "principle_category", "source": "principle_source"}
        updates: dict[str, Any] = {rename.get(k, k): v for k, v in raw.items()}
        if why_important:
            base = updates.get("description") or principle.description or ""
            updates["description"] = (
                f"{base}\n\nWhy this matters:\n{why_important}" if base else why_important
            )

        result = await principles_service.update_principle(uid, updates)
        if result.is_error:
            err = result.expect_error()
            content = Div(
                PageHeader(f"Edit: {principle.title}"),
                render_error_banner(err.display_message),
                PrincipleEditForm(principle),
                cls="space-y-6",
            )
            return await render_activity_sidebar_page(content, active="principles", request=request)

        return RedirectResponse(f"/principles/detail?uid={uid}", status_code=303)

    return [
        *base_routes,
        principle_create_page,
        principle_create_submit,
        principle_edit_page,
        principle_edit_submit,
    ]
