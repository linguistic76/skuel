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
from enum import StrEnum
from functools import partial
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlencode

from fasthtml.common import FT, Div, FtResponse, HttpHeader

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories import refuse, refuse_not_found
from core.models.enums.neo_labels import NeoLabel
from core.utils.result_simplified import Result
from ui.activities._shared import CurriculumOriginField
from ui.activities.filter_bar import ActivityFilterBar, with_user_categories
from ui.activities.nav import render_activity_sidebar_page
from ui.components import ButtonT
from ui.dual_track_card import render_dual_track_result
from ui.layouts.base_page import HtmlDocument
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner, render_slot_error
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.personal_header import personal_header_placeholder
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from adapters.inbound.fasthtml_types import RouteDecorator
    from core.models.shared.dual_track import DualTrackResult
    from core.models.type_hints import UserUID
    from core.ports import ConnectionFetchOperations
    from core.ports.query_types import EntityConnection
    from ui.activities.filter_bar import FilterBarConfig


# ============================================================================
# Configuration
# ============================================================================


class ActivityEntity(Protocol):
    """What the factory reads off an activity: its uid and its curriculum origin."""

    @property
    def uid(self) -> str: ...

    @property
    def source_path_step_uid(self) -> str | None: ...


class DualTrackAssess[L: StrEnum](Protocol):
    """A facade's per-entity dual-track assessment, as the results route calls it:
    the entity, its owner, the learner's level on the domain's scale, the reflection."""

    async def __call__(
        self, uid: str, user_uid: UserUID, level: L, /, *, user_evidence: str
    ) -> Result[DualTrackResult[L]]: ...


@dataclass(frozen=True)
class ActivityUIConfig[E: ActivityEntity, L: StrEnum = StrEnum]:
    """Configuration for a single Activity Domain's UI routes.

    Generic over the domain's entity ``E`` (``Task``, ``Goal``…) — every service
    method and component the config names is checked against it — and the level
    scale ``L`` the dual-track route rates on (``ProgressLevel``…; the default
    for domains without one).

    Captures all per-domain differences so the factory can generate
    identical route structures with domain-specific behavior.

    Attributes:
        domain_name: URL path segment, e.g. "tasks"
        domain_singular: Singular form for IDs/messages, e.g. "task"
        page_title: Display title, e.g. "Tasks"
        filter_params: Ordered (param_name, default) pairs extracted from query string.
            Passed positionally (after items) to filter_fn.
        get_all: Service method (user_uid) -> Result[list[Entity]]
        get_owned: The facade's owner-checked read (uid, user_uid) -> Result[Entity] —
            the entity when the caller owns it, NOT_FOUND otherwise (ADR-085);
            ``verify_ownership``, or ``get_for_user`` where the facade hydrates
            derived fields the detail page shows (Habits)
        backend: ConnectionFetchOperations port for connection / source-PathStep fetching
        filter_fn: Domain filter function (items, *param_values) -> filtered
        link_label: the domain's label — its page views in the relationship
            registry are the links the list card and the detail page show (ADR-090 §2)
        filter_config: The FilterBarConfig ActivityFilterBar renders
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
    get_all: Callable[[UserUID], Awaitable[Result[list[E]]]]
    get_owned: Callable[[str, UserUID], Awaitable[Result[E]]]
    backend: ConnectionFetchOperations
    filter_fn: Callable[..., list[E]]
    link_label: NeoLabel
    filter_config: FilterBarConfig
    list_component: Callable[[list[E], dict[str, list[EntityConnection]]], FT]
    stats_component: Callable[[list[E]], FT]
    detail_component: Callable[[E, list[EntityConnection]], FT]
    create_href: str | None = None
    create_label: str | None = None
    # Dual-track per-entity self-assessment (ADR-030) — optional
    dual_track_assess: DualTrackAssess[L] | None = None
    dual_track_level_enum: type[L] | None = None
    dual_track_label: str = ""
    # Live category options for the filter bar — optional
    list_categories: Callable[[UserUID], Awaitable[Result[list[str]]]] | None = None


@dataclass(frozen=True)
class _FilteredView[E]:
    """One read of a domain's list page: every item, the filtered slice, the
    slice's page links, and the filter values the request asked for."""

    all_items: list[E]
    filtered: list[E]
    connections_map: dict[str, list[EntityConnection]]
    param_values: dict[str, str]


# ============================================================================
# Route factory
# ============================================================================


def _bare_banner(message: str) -> FT:
    """The dual-track result slot's refusal body — a banner with no slot id (the card
    re-renders in place)."""
    return Div(render_error_banner(message))


def create_activity_ui_routes[E: ActivityEntity, L: StrEnum](
    rt: RouteDecorator,
    config: ActivityUIConfig[E, L],
) -> None:
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

    async def _fetch_filtered(request: Request) -> Result[_FilteredView[E]]:
        """Auth, fetch all items, filter, fetch connections."""
        user_uid = require_authenticated_user(request)

        result = await config.get_all(user_uid)
        if result.is_error:
            return Result.fail(result)

        all_items = result.value

        param_values = {
            name: request.query_params.get(name, default) for name, default in config.filter_params
        }
        filter_args = [param_values[name] for name, _ in config.filter_params]
        filtered = config.filter_fn(all_items, *filter_args)

        uids = [item.uid for item in filtered]
        connections_map = await config.backend.fetch_entity_connections(config.link_label, uids)

        return Result.ok(_FilteredView(all_items, filtered, connections_map, param_values))

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
    def page(request: Request) -> HtmlDocument:
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
            cls="space-y-6",
        )
        return render_activity_sidebar_page(content, active=domain, request=request)

    # ------------------------------------------------------------------
    # 2. Content fragment: /{domain}/content
    # ------------------------------------------------------------------

    @rt(f"/{domain}/content")
    async def content_fragment(request: Request) -> FT:
        """HTMX fragment: filter bar + list + stats bar."""
        read = await _fetch_filtered(request)
        if read.is_error:
            return Div(
                render_error_banner(read.expect_error().display_message),
                id=f"{domain}-content",
            )
        view = read.value

        filter_config = config.filter_config
        if config.list_categories is not None:
            user_uid = require_authenticated_user(request)
            categories_result = await config.list_categories(user_uid)
            filter_config = with_user_categories(
                filter_config,
                categories_result.value if categories_result.is_ok else None,
            )

        return Div(
            ActivityFilterBar(filter_config, view.param_values),
            config.list_component(view.filtered, view.connections_map),
            config.stats_component(view.all_items),
            id=f"{domain}-content",
            cls="space-y-4",
        )

    # ------------------------------------------------------------------
    # 3. List fragment: /{domain}/list-fragment
    # ------------------------------------------------------------------

    @rt(f"/{domain}/list-fragment")
    async def list_fragment(request: Request) -> FT | tuple[FT, HttpHeader]:
        """HTMX fragment: filtered list only (for filter bar updates)."""
        read = await _fetch_filtered(request)
        if read.is_error:
            return Div(
                render_error_banner(read.expect_error().display_message),
                id=f"{singular}-list",
            )
        view = read.value

        # Sync the browser URL with the applied filters so a filtered view is
        # bookmarkable and survives refresh (the page shell re-forwards the
        # params). Default-valued params are omitted to keep the URL canonical.
        non_default = {
            name: view.param_values[name]
            for name, default in config.filter_params
            if view.param_values[name] != default
        }
        page_url = f"/{domain}?{urlencode(non_default)}" if non_default else f"/{domain}"
        return (
            config.list_component(view.filtered, view.connections_map),
            HttpHeader("HX-Push-Url", page_url),
        )

    # ------------------------------------------------------------------
    # 4. Detail shell: /{domain}/detail
    # ------------------------------------------------------------------

    @rt(f"/{domain}/detail")
    def detail_page(request: Request) -> HtmlDocument:
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
    async def detail_content_fragment(request: Request) -> FT | FtResponse:
        """HTMX fragment: entity detail with connections."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        slot = partial(render_slot_error, f"{singular}-detail-content")

        if not uid:
            return refuse_not_found(slot(f"Missing {singular} UID"))

        # The one read on the detail page: the shell only echoes the uid into this
        # URL. A foreign uid and a missing one answer the same rendered 404; a
        # backend failure keeps its own status.
        owned = await config.get_owned(uid, user_uid)
        if owned.is_error:
            return refuse(owned.expect_error(), slot, singular.capitalize())
        entity = owned.value

        connections_map = await config.backend.fetch_entity_connections(
            config.link_label, [entity.uid]
        )
        connections = connections_map.get(entity.uid, [])

        body = config.detail_component(entity, connections)

        # Surface curriculum origin: activities spawned by engaging a PathStep
        # carry source_path_step_uid. User-created activities leave it None.
        if entity.source_path_step_uid:
            source_ps = await config.backend.fetch_source_pathstep(
                entity.source_path_step_uid, user_uid
            )
            if source_ps:
                return Div(CurriculumOriginField(source_ps["uid"], source_ps["title"]), body)

        return body

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
        async def dual_track_results(request: Request) -> FT | FtResponse:
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

            if not uid:
                return refuse_not_found(Div(render_error_banner(f"Missing {singular} UID")))

            # Ownership: the refusal renders in the slot at the status it earns.
            owned = await config.get_owned(uid, user_uid)
            if owned.is_error:
                return refuse(owned.expect_error(), _bare_banner, singular.capitalize())

            try:
                level = level_enum(level_raw)
            except ValueError:
                return Div(render_error_banner("Please choose a rating first."))

            assess_result = await dual_track_assess(uid, user_uid, level, user_evidence=reflection)
            if assess_result.is_error:
                return Div(render_error_banner(assess_result.expect_error().display_message))

            # Re-fetch so the trend includes the just-stored check-in.
            refreshed = await config.get_owned(uid, user_uid)
            checkins = (
                getattr(refreshed.value, "dual_track_checkins", ()) if refreshed.is_ok else ()
            )
            return render_dual_track_result(config.dual_track_label, assess_result.value, checkins)
