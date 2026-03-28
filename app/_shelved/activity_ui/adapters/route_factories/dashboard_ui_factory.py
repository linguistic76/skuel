"""
Dashboard UI Route Factory — Configuration-Driven Activity Domain Dashboards
=============================================================================

Consolidates ~845 lines of duplicate dashboard route handling across 6 activity
domain UI files into a single factory.

Core Pattern Consolidated:
1. Main dashboard with view switching (list/create/calendar or analytics)
2. HTMX view fragments for tab switching
3. Filtered list fragment for filter updates

Each domain provides callables for its specific behavior (filter parsing,
service calls, rendering). The factory handles the shared boilerplate:
authentication, error handling, view dispatch, and page wrapping.

Usage:
    from adapters.inbound.route_factories.dashboard_ui_factory import (
        DashboardUIConfig,
        DashboardUIFactory,
    )

    # Define domain-specific callables (named functions, not lambdas — SKUEL012)
    def fetch_choices_context(user_uid, filters):
        return choices_service.get_filtered_context(user_uid, filters.status, filters.sort_by)

    config = DashboardUIConfig(
        domain_name="choices",
        title="Choices",
        subtitle="Make and track important decisions",
        ...
    )
    DashboardUIFactory.register_routes(rt, config)

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from core.utils.result_simplified import Result

from adapters.inbound.auth.session import require_authenticated_user
from adapters.inbound.ui_helpers import render_dashboard_error_page
from core.utils.logging import get_logger
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader
from ui.tokens import Container, Spacing

logger = get_logger(__name__)


# Type aliases for callable signatures
FilterParser = "Callable[[Any], Any]"
ContextFetcher = "Callable[[str, Any], Awaitable[Result[dict[str, Any]]]]"
ViewRenderer = "Callable[[dict[str, Any]], Any]"
AsyncViewRenderer = "Callable[[str, Any], Awaitable[Any]]"
PageCreator = "Callable[..., Awaitable[Any]]"
ListItemRenderer = "Callable[[list[Any]], Any]"
PageContextBuilder = "Callable[[dict[str, Any], Any], dict[str, Any]]"


@dataclass(frozen=True)
class DashboardUIConfig:
    """Configuration for dashboard UI route generation.

    Captures all variation points across the 6 activity domain dashboards.
    Callables handle domain-specific behavior; the factory handles the
    shared auth/error/wrapping boilerplate.

    Attributes:
        domain_name: URL slug and identifier (e.g., "tasks", "choices")
        title: Human-readable page title (e.g., "Tasks")
        subtitle: Page subtitle shown in PageHeader
        default_view: Which view to show by default ("list" or "calendar")
        views: Ordered tuple of available views, e.g. ("list", "create", "calendar")
        parse_filters: Extracts filter params from request -> domain-specific filters
        fetch_filtered_context: Async service call: (user_uid, filters) -> Result[dict]
        render_view_tabs: Renders the view tab bar: (active_view) -> FT
        render_list_view: Renders list view from page context: (page_ctx) -> FT
        render_create_view: Async render of create form: (user_uid, svc_ctx) -> FT
        render_third_view: Async render of third view (calendar/analytics):
            (user_uid, request) -> FT. None if domain has only 2 views.
        build_page_context: Maps service context + filters to PageContext dict
        render_list_fragment: Renders the complete list fragment including container:
            (entities) -> FT. Returns wrapping Div with id and empty state handling.
        create_page: Page wrapper: async (content, *, request) -> Response
    """

    # Identity
    domain_name: str
    title: str
    subtitle: str

    # View structure
    default_view: str
    views: tuple[str, ...]

    # Data fetching
    parse_filters: Callable[[Any], Any]
    fetch_filtered_context: Callable[[str, Any], Awaitable[Result[dict[str, Any]]]]

    # View rendering
    render_view_tabs: Callable[..., Any]
    render_list_view: Callable[[dict[str, Any]], Any]
    render_create_view: Callable[[str, dict[str, Any]], Awaitable[Any]]
    render_third_view: Callable[[str, Any], Awaitable[Any]] | None

    # Context building
    build_page_context: Callable[[dict[str, Any], Any], Any]

    # List fragment — returns the complete fragment including container wrapper
    render_list_fragment: Callable[[list[Any]], Any]

    # Page wrapper
    create_page: Callable[..., Awaitable[Any]]

    @property
    def third_view_name(self) -> str | None:
        """Derive the third view name (not 'list' or 'create') from views tuple."""
        for v in self.views:
            if v not in ("list", "create"):
                return v
        return None


class DashboardUIFactory:
    """Factory that generates 5 dashboard routes from a DashboardUIConfig.

    Generated routes:
    - GET /{domain} — main dashboard with view switching
    - GET /{domain}/view/list — HTMX list view fragment
    - GET /{domain}/view/create — HTMX create view fragment
    - GET /{domain}/view/{third_view} — HTMX third view fragment
    - GET /{domain}/list-fragment — HTMX filtered list for filter updates

    Follows the same pattern as QuickAddRouteFactory: frozen config + static
    registration method.
    """

    @staticmethod
    def register_routes(rt: Any, config: DashboardUIConfig) -> None:
        """Register all dashboard routes for a domain."""
        DashboardUIFactory._register_dashboard(rt, config)
        DashboardUIFactory._register_list_view(rt, config)
        DashboardUIFactory._register_create_view(rt, config)
        if config.render_third_view is not None and config.third_view_name is not None:
            DashboardUIFactory._register_third_view(rt, config)
        DashboardUIFactory._register_list_fragment(rt, config)

        logger.debug(
            f"Registered dashboard routes for /{config.domain_name} "
            f"(views: {', '.join(config.views)})"
        )

    @staticmethod
    def _register_dashboard(rt: Any, config: DashboardUIConfig) -> None:
        """Register the main dashboard route with view switching."""

        async def dashboard_handler(request: Any) -> Any:
            user_uid = require_authenticated_user(request)
            view = request.query_params.get("view", config.default_view)
            filters = config.parse_filters(request)

            filtered_result = await config.fetch_filtered_context(user_uid, filters)

            if filtered_result.is_error:
                return await render_dashboard_error_page(
                    config.title,
                    config.subtitle,
                    f"Failed to load {config.domain_name}",
                    view,
                    config.render_view_tabs,
                    config.create_page,
                    request,
                )

            svc_ctx = filtered_result.value

            third_view = config.third_view_name

            if view == "create":
                view_content = await config.render_create_view(user_uid, svc_ctx)
            elif config.render_third_view is not None and view == third_view:
                view_content = await config.render_third_view(user_uid, request)
            else:
                page_ctx = config.build_page_context(svc_ctx, filters)
                view_content = config.render_list_view(page_ctx)

            page_content = Div(
                PageHeader(config.title, subtitle=config.subtitle),
                config.render_view_tabs(active_view=view),
                Div(view_content, id="view-content", role="tabpanel"),
                cls=f"{Spacing.PAGE} {Container.WIDE}",
            )

            return await config.create_page(page_content, request=request)

        rt(f"/{config.domain_name}")(dashboard_handler)

    @staticmethod
    def _register_list_view(rt: Any, config: DashboardUIConfig) -> None:
        """Register the HTMX list view fragment route."""

        async def list_view_handler(request: Any) -> Any:
            user_uid = require_authenticated_user(request)
            filters = config.parse_filters(request)

            filtered_result = await config.fetch_filtered_context(user_uid, filters)

            if filtered_result.is_error:
                return render_error_banner(f"Failed to load {config.domain_name}")

            svc_ctx = filtered_result.value
            page_ctx = config.build_page_context(svc_ctx, filters)
            return config.render_list_view(page_ctx)

        rt(f"/{config.domain_name}/view/list")(list_view_handler)

    @staticmethod
    def _register_create_view(rt: Any, config: DashboardUIConfig) -> None:
        """Register the HTMX create view fragment route."""

        async def create_view_handler(request: Any) -> Any:
            user_uid = require_authenticated_user(request)

            # Fetch context so create view can access metadata if needed
            filters = config.parse_filters(request)
            filtered_result = await config.fetch_filtered_context(user_uid, filters)

            svc_ctx = filtered_result.value if not filtered_result.is_error else {}
            return await config.render_create_view(user_uid, svc_ctx)

        rt(f"/{config.domain_name}/view/create")(create_view_handler)

    @staticmethod
    def _register_third_view(rt: Any, config: DashboardUIConfig) -> None:
        """Register the HTMX third view fragment route (calendar or analytics)."""
        assert config.render_third_view is not None
        assert config.third_view_name is not None
        third_view_name = config.third_view_name

        async def third_view_handler(request: Any) -> Any:
            user_uid = require_authenticated_user(request)
            return await config.render_third_view(user_uid, request)  # type: ignore[misc]

        rt(f"/{config.domain_name}/view/{third_view_name}")(third_view_handler)

    @staticmethod
    def _register_list_fragment(rt: Any, config: DashboardUIConfig) -> None:
        """Register the HTMX filtered list fragment route."""

        async def list_fragment_handler(request: Any) -> Any:
            user_uid = require_authenticated_user(request)
            filters = config.parse_filters(request)

            filtered_result = await config.fetch_filtered_context(user_uid, filters)

            if filtered_result.is_error:
                return render_error_banner(f"Failed to load {config.domain_name}")

            svc_ctx = filtered_result.value
            return config.render_list_fragment(svc_ctx["entities"])

        rt(f"/{config.domain_name}/list-fragment")(list_fragment_handler)


__all__ = ["DashboardUIConfig", "DashboardUIFactory"]
