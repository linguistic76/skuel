"""Generic Activity Domain UI route factory.

All 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles)
share the same 5-route pattern:

    /{domain}                — Page shell with HTMX loading placeholder
    /{domain}/content        — HTMX fragment: filter bar + list + stats bar
    /{domain}/list-fragment  — HTMX fragment: filtered list only (for filter updates)
    /{domain}/detail         — Detail page shell with HTMX loading placeholder
    /{domain}/detail/content — HTMX fragment: entity detail with connections

This factory generates all 5 routes from a config dataclass, eliminating
~80% code duplication across those 6 files.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from fasthtml.common import Div, HttpHeader

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from ui.activities._shared import CurriculumOriginField
from ui.activities.filter_bar import ActivityFilterBar, with_user_categories
from ui.activities.nav import render_activity_sidebar_page
from ui.components import ButtonT
from ui.dual_track_card import render_dual_track_result
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.personal_header import personal_header_placeholder
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.models.type_hints import UserUID
    from core.ports import ConnectionFetchOperations


# ============================================================================
# Configuration
# ============================================================================


@dataclass(frozen=True)
class ActivityUIConfig:
    """Configuration for a single Activity Domain's UI routes.

    Captures all per-domain differences so the factory can generate
    identical route structures with domain-specific behavior.

    Attributes:
        domain_name: URL path segment, e.g. "tasks"
        domain_singular: Singular form for IDs/messages, e.g. "task"
        page_title: Display title, e.g. "Tasks"
        filter_params: Ordered (param_name, default) pairs extracted from query string.
            Passed positionally (after items) to filter_fn.
        get_all: Service method (user_uid) -> Result[list[Entity]]
        get_one: Service method (uid) -> Result[Entity]
        backend: ConnectionFetchOperations port for connection / source-PathStep fetching
        filter_fn: Domain filter function (items, *param_values) -> filtered
        connection_config: ConnectionConfig for fetch_entity_connections
        filter_config: FilterConfig for ActivityFilterBar
        list_component: (filtered, connections_map) -> FT
        stats_component: (all_items) -> FT
        detail_component: (entity, connections) -> FT
        dual_track_assess: Per-entity dual-track assessment method, e.g.
            goals_service.intelligence.assess_progress_dual_track. When set, the
            factory registers POST /{domain}/dual-track/results (ADR-030). Called
            as (uid, user_uid, level, user_evidence=...). None for domains
            without a per-entity dual-track dimension (Tasks/Events/Choices are
            user-level — surfaced on the Self Check-In page instead).
        dual_track_level_enum: The StrEnum the user self-rates with (ProgressLevel
            / ConsistencyLevel / AlignmentLevel).
        dual_track_label: Card title noun, e.g. "Progress".
        list_categories: Search sub-service method (user_uid) -> Result[list[str]]
            returning the user's distinct category values (e.g.
            ``goals_service.search.list_user_categories``). When set, the content
            route rebuilds the filter bar's Category dropdown from live data via
            ``with_user_categories`` (dropped at 0-1 categories). None keeps the
            static filter config as-is.
    """

    domain_name: str
    domain_singular: str
    page_title: str
    filter_params: tuple[tuple[str, str], ...]
    get_all: Callable[[UserUID], Awaitable[Any]]
    get_one: Callable[[str], Awaitable[Any]]
    backend: ConnectionFetchOperations
    filter_fn: Callable[..., list[Any]]
    connection_config: Any
    filter_config: Any
    list_component: Callable[..., Any]
    stats_component: Callable[..., Any]
    detail_component: Callable[..., Any]
    create_href: str | None = None
    create_label: str | None = None
    # Dual-track per-entity self-assessment (ADR-030) — optional
    dual_track_assess: Callable[..., Awaitable[Any]] | None = None
    dual_track_level_enum: type | None = None
    dual_track_label: str = ""
    # Live category options for the filter bar — optional
    list_categories: Callable[[UserUID], Awaitable[Any]] | None = None


# ============================================================================
# Route factory
# ============================================================================


def create_activity_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    config: ActivityUIConfig,
) -> list[Any]:
    """Generate the standard 5-route UI pattern for an Activity Domain.

    The generated routes follow the shell-first pattern: page routes return
    immediately with a loading placeholder, then HTMX fragments load the
    actual content asynchronously.
    """
    domain = config.domain_name
    singular = config.domain_singular
    title = config.page_title

    # ------------------------------------------------------------------
    # Shared data-loading helper (used by content + list-fragment routes)
    # ------------------------------------------------------------------

    async def _fetch_filtered(
        request: Request,
    ) -> tuple[Any, list[Any], list[Any], dict[str, Any], dict[str, str]]:
        """Auth, fetch all items, filter, fetch connections.

        Returns (error_or_none, all_items, filtered, connections_map, param_values).
        On error, only the first element is set; the rest are empty.
        """
        user_uid = require_authenticated_user(request)

        result = await config.get_all(user_uid)
        if result.is_error:
            return result.expect_error(), [], [], {}, {}

        all_items = result.value

        param_values = {
            name: request.query_params.get(name, default) for name, default in config.filter_params
        }
        filter_args = [param_values[name] for name, _ in config.filter_params]
        filtered = config.filter_fn(all_items, *filter_args)

        uids = [item.uid for item in filtered]
        connections_map = await config.backend.fetch_entity_connections(
            config.connection_config, uids
        )

        return None, all_items, filtered, connections_map, param_values

    # ------------------------------------------------------------------
    # 1. Page shell: /{domain}
    # ------------------------------------------------------------------

    header_actions = (
        ButtonLink(
            config.create_label or f"+ New {singular.title()}",
            href=config.create_href,
            cls=ButtonT.primary,
        )
        if config.create_href
        else None
    )

    @rt(f"/{domain}")
    def page(request: Request) -> Any:
        """Main page shell — content loads via HTMX."""
        require_authenticated_user(request)
        # The shell and its content fragment are two separate HTTP requests:
        # filter params in the page URL (stat-card links, bookmarks, the
        # HX-Push-Url below) must be explicitly re-forwarded or they are
        # silently dropped and the fragment renders with defaults.
        forwarded = {
            name: request.query_params[name]
            for name, _default in config.filter_params
            if name in request.query_params
        }
        fragment_url = f"/{domain}/content"
        if forwarded:
            fragment_url = f"{fragment_url}?{urlencode(forwarded)}"
        content = Div(
            PageHeader(title, actions=header_actions),
            content_loading_placeholder(fragment_url, f"{domain}-content"),
            personal_header_placeholder(),
        )
        return render_activity_sidebar_page(content, active=domain, request=request)

    # ------------------------------------------------------------------
    # 2. Content fragment: /{domain}/content
    # ------------------------------------------------------------------

    @rt(f"/{domain}/content")
    async def content_fragment(request: Request) -> Any:
        """HTMX fragment: filter bar + list + stats bar."""
        error, all_items, filtered, connections_map, param_values = await _fetch_filtered(request)
        if error is not None:
            return Div(
                render_error_banner(error.display_message),
                id=f"{domain}-content",
            )

        filter_config = config.filter_config
        if config.list_categories is not None:
            user_uid = require_authenticated_user(request)
            categories_result = await config.list_categories(user_uid)
            filter_config = with_user_categories(
                filter_config,
                categories_result.value if categories_result.is_ok else None,
            )

        return Div(
            ActivityFilterBar(filter_config, param_values),
            config.list_component(filtered, connections_map),
            config.stats_component(all_items),
            id=f"{domain}-content",
        )

    # ------------------------------------------------------------------
    # 3. List fragment: /{domain}/list-fragment
    # ------------------------------------------------------------------

    @rt(f"/{domain}/list-fragment")
    async def list_fragment(request: Request) -> Any:
        """HTMX fragment: filtered list only (for filter bar updates)."""
        error, _all_items, filtered, connections_map, param_values = await _fetch_filtered(request)
        if error is not None:
            return Div(
                render_error_banner(error.display_message),
                id=f"{singular}-list",
            )

        # Sync the browser URL with the applied filters so a filtered view is
        # bookmarkable and survives refresh (the page shell re-forwards the
        # params). Default-valued params are omitted to keep the URL canonical.
        non_default = {
            name: param_values[name]
            for name, default in config.filter_params
            if param_values[name] != default
        }
        page_url = f"/{domain}?{urlencode(non_default)}" if non_default else f"/{domain}"
        return config.list_component(filtered, connections_map), HttpHeader("HX-Push-Url", page_url)

    # ------------------------------------------------------------------
    # 4. Detail shell: /{domain}/detail
    # ------------------------------------------------------------------

    @rt(f"/{domain}/detail")
    def detail_page(request: Request) -> Any:
        """Detail page shell — content loads via HTMX."""
        require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return render_activity_sidebar_page(
                Div(render_error_banner(f"Missing {singular} UID")),
                active=domain,
                request=request,
            )
        content = Div(
            content_loading_placeholder(
                f"/{domain}/detail/content?uid={uid}", f"{singular}-detail-content"
            ),
        )
        return render_activity_sidebar_page(content, active=domain, request=request)

    # ------------------------------------------------------------------
    # 5. Detail content fragment: /{domain}/detail/content
    # ------------------------------------------------------------------

    @rt(f"/{domain}/detail/content")
    async def detail_content_fragment(request: Request) -> Any:
        """HTMX fragment: entity detail with connections."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        not_found_label = f"{singular.capitalize()} not found"

        if not uid:
            return Div(
                render_error_banner(f"Missing {singular} UID"),
                id=f"{singular}-detail-content",
            )

        entity_result = await config.get_one(uid)
        if entity_result.is_error:
            return Div(render_error_banner(not_found_label), id=f"{singular}-detail-content")

        entity = entity_result.value
        if entity.user_uid != user_uid:
            return Div(render_error_banner(not_found_label), id=f"{singular}-detail-content")

        connections_map = await config.backend.fetch_entity_connections(
            config.connection_config, [entity.uid]
        )
        connections = connections_map.get(entity.uid, [])

        body = config.detail_component(entity, connections)

        # Surface curriculum origin: activities spawned by engaging a PathStep
        # carry source_path_step_uid. User-created activities leave it None.
        if entity.source_path_step_uid:
            source_ps = await config.backend.fetch_source_pathstep(entity.source_path_step_uid)
            if source_ps:
                return Div(CurriculumOriginField(source_ps["uid"], source_ps["title"]), body)

        return body

    routes = [page, content_fragment, list_fragment, detail_page, detail_content_fragment]

    # ------------------------------------------------------------------
    # 6. Dual-track results fragment: /{domain}/dual-track/results (ADR-030)
    #    Registered only for domains with a per-entity dual-track dimension
    #    (Goals/Habits/Principles). Computes + persists a perception-gap
    #    check-in, then swaps in the gap card + refreshed trend.
    # ------------------------------------------------------------------

    if config.dual_track_assess is not None and config.dual_track_level_enum is not None:
        dual_track_assess = config.dual_track_assess
        level_enum = config.dual_track_level_enum

        @rt(f"/{domain}/dual-track/results", methods=["POST"])
        @csrf_protected
        async def dual_track_results(request: Request) -> Any:
            """HTMX POST: run + persist a per-entity dual-track assessment.

            POST (not GET) because it mutates — the assessment appends a check-in
            to the entity's dual_track_checkins. CSRF-protected so a check-in
            can't be written via a plain link / prefetch; skuel.js attaches the
            X-CSRF-Token header to every HTMX request.
            """
            user_uid = require_authenticated_user(request)
            uid = request.query_params.get("uid", "")
            form = await request.form()
            level_raw = str(form.get("level", ""))
            reflection = str(form.get("reflection", ""))
            not_found_label = f"{singular.capitalize()} not found"

            if not uid:
                return Div(render_error_banner(f"Missing {singular} UID"))

            # Ownership: 404-not-403 for entities the user doesn't own.
            owned = await config.get_one(uid)
            if owned.is_error or owned.value.user_uid != user_uid:
                return Div(render_error_banner(not_found_label))

            try:
                level = level_enum(level_raw)
            except ValueError:
                return Div(render_error_banner("Please choose a rating first."))

            assess_result = await dual_track_assess(uid, user_uid, level, user_evidence=reflection)
            if assess_result.is_error:
                return Div(render_error_banner(assess_result.expect_error().display_message))

            # Re-fetch so the trend includes the just-stored check-in.
            refreshed = await config.get_one(uid)
            checkins = (
                getattr(refreshed.value, "dual_track_checkins", ()) if refreshed.is_ok else ()
            )
            return render_dual_track_result(config.dual_track_label, assess_result.value, checkins)

        routes.append(dual_track_results)

    return routes
