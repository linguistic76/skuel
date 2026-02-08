"""
KU UI Routes — The Central Knowledge Hub
=========================================

The /ku route is SKUEL's central route. KU is the primary entity.
Everything flows through knowledge.

Layout: Custom sidebar (MOC + SEL categories) + tabs (SEL category filter).
Follows profile-hub sidebar pattern (profile_sidebar.css).
"""

from dataclasses import dataclass
from typing import Any

from fasthtml.common import H1, H2, H3, Li, Main, NotStr, P, Ul
from fasthtml.common import A as Anchor
from starlette.requests import Request
from starlette.responses import Response

from components.card_generator import CardGenerator
from components.form_generator import FormGenerator
from components.shared_ui_components import SharedUIComponents
from core.models.ku.ku_request import KuCreateRequest
from core.models.shared_enums import SELCategory
from core.ui.daisy_components import Button, ButtonT, Card, Div, Span
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.routes.ku.ui")


# ==========================================================================
# SEL CATEGORY TABS
# ==========================================================================

SEL_TABS = [
    ("All", None, "all"),
    ("Self Awareness", SELCategory.SELF_AWARENESS, "self_awareness"),
    ("Self Management", SELCategory.SELF_MANAGEMENT, "self_management"),
    ("Social Awareness", SELCategory.SOCIAL_AWARENESS, "social_awareness"),
    ("Relationship Skills", SELCategory.RELATIONSHIP_SKILLS, "relationship_skills"),
    ("Decision Making", SELCategory.RESPONSIBLE_DECISION_MAKING, "responsible_decision_making"),
]


def _ku_tabs(active_tab: str = "all") -> Any:
    """Render SEL category tabs for filtering KUs."""
    tabs = []
    for label, _category, slug in SEL_TABS:
        is_active = slug == active_tab
        tabs.append(
            Anchor(
                label,
                role="tab",
                cls=f"tab {'tab-active' if is_active else ''}",
                hx_get=f"/ku/filter?sel_category={slug}" if slug != "all" else "/ku/filter",
                hx_target="#ku-content",
                hx_swap="innerHTML",
                hx_push_url=f"/ku?sel={slug}" if slug != "all" else "/ku",
            )
        )
    return Div(
        *tabs,
        cls="tabs tabs-bordered mb-6",
        role="tablist",
        aria_label="Filter by SEL category",
    )


def _ku_sidebar(active_slug: str = "all") -> Any:
    """Build the KU sidebar with SEL categories + MOC navigation."""
    chevron_svg = NotStr(
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path d="M15 18l-6-6 6-6"></path>'
        "</svg>"
    )

    sel_items = [
        Li(
            Anchor(
                label,
                href=f"/ku?sel={slug}" if slug != "all" else "/ku",
                cls=f"{'menu-active' if slug == active_slug else ''}",
                **{
                    "hx-boost": "false",
                    "onclick": "if(window.innerWidth<=1024)toggleProfileSidebar()",
                },
            )
        )
        for label, _category, slug in SEL_TABS
    ]

    sidebar_menu = Ul(
        Li(
            Anchor(
                "Knowledge",
                href="/ku",
                cls="text-xl font-bold text-primary hover:text-primary-focus",
                id="ku-sidebar-heading",
                **{"hx-boost": "false"},
            ),
            P("Explore and Learn", cls="text-xs opacity-60 mt-1"),
            cls="px-4 py-4 sidebar-header-text",
        ),
        Li(cls="divider my-0"),
        Li(
            Span(
                "SEL Categories",
                cls="text-xs font-semibold uppercase tracking-wider opacity-60",
            ),
            cls="menu-title",
        ),
        *sel_items,
        Li(cls="divider my-0"),
        Li(
            Span(
                "Maps of Content",
                cls="text-xs font-semibold uppercase tracking-wider opacity-60",
            ),
            cls="menu-title",
        ),
        Li(
            Div(
                P("MOC navigation", cls="text-xs opacity-50"),
                id="moc-nav-list",
                hx_get="/ku/moc-nav",
                hx_trigger="load",
                hx_swap="innerHTML",
            )
        ),
        cls="menu bg-white min-h-full w-full p-4 sidebar-nav",
        id="ku-sidebar-nav",
    )

    return Div(
        Div(
            Button(
                chevron_svg,
                onclick="toggleProfileSidebar()",
                cls="sidebar-toggle",
                title="Toggle Sidebar",
                type="button",
                aria_label="Toggle Knowledge sidebar",
                aria_expanded="false",
                aria_controls="ku-sidebar-nav",
            ),
            sidebar_menu,
            cls="sidebar-inner",
        ),
        cls="profile-sidebar",
        id="profile-sidebar",
        role="dialog",
        aria_modal="false",
        aria_labelledby="ku-sidebar-heading",
    )


def _ku_page_layout(active_slug: str, content: Any) -> Any:
    """Assemble full layout: sidebar + content area."""
    return Div(
        Div(
            cls="profile-overlay",
            id="profile-overlay",
            onclick="toggleProfileSidebar()",
        ),
        _ku_sidebar(active_slug),
        Div(
            id="sidebar-sr-announcements",
            role="status",
            aria_live="polite",
            cls="sr-only",
        ),
        Div(
            Div(
                Span("☰", aria_hidden="true"),
                Span("Menu"),
                cls="btn btn-ghost mobile-menu-button mb-4",
                onclick="toggleProfileSidebar()",
                role="button",
                tabindex="0",
                aria_label="Open Knowledge navigation",
                aria_expanded="false",
                aria_controls="profile-sidebar",
            ),
            Main(
                Div(content, cls="max-w-6xl mx-auto"),
                cls="p-6 lg:p-8",
            ),
            cls="profile-content",
            id="profile-content",
        ),
        cls="profile-container",
    )


# ============================================================================
# UI COMPONENT LIBRARY - Reusable KU components
# ============================================================================


class KuUIComponents:
    """Centralized KU UI components - no more inline composition"""

    @staticmethod
    async def render_ku_dashboard(
        knowledge_units=None, stats=None, domains=None, request=None
    ) -> Any:
        """
        Main KU dashboard - REFACTORED to use SharedUIComponents.

        BEFORE: Manual composition of stats, actions, recent units, graph, all units
        AFTER: Uses SharedUIComponents.render_entity_dashboard()
        SAVINGS: ~54 lines (estimated 55% reduction in dashboard code)
        """
        knowledge_units = knowledge_units or []
        stats = stats or {}
        domains = domains or ["technology", "science", "business", "personal", "health"]

        # Transform stats to shared format
        stats_formatted = {
            "total": {
                "label": "Knowledge Units",
                "value": stats.get("total_units", 0),
                "color": "blue",
            },
            "connections": {
                "label": "Connections",
                "value": stats.get("total_connections", 0),
                "color": "green",
            },
            "domains": {
                "label": "Domains",
                "value": stats.get("domains_count", 0),
                "color": "purple",
            },
            "paths": {
                "label": "Learning Paths",
                "value": stats.get("learning_paths", 0),
                "color": "orange",
            },
        }

        # Define quick actions
        quick_actions = [
            {
                "label": "➕ New Knowledge",
                "hx_get": "/ku/create",
                "hx_target": "#modal",
                "class": "btn-primary",
            },
            {
                "label": "🔍 Discovery",
                "hx_get": "/ku/discovery",
                "hx_target": "#main-content",
                "class": "btn-secondary",
            },
            {
                "label": "📊 Analytics",
                "hx_get": "/ku/analytics",
                "hx_target": "#main-content",
                "class": "btn-outline",
            },
            {
                "label": "🕸️ Graph View",
                "hx_get": "/ku/graph",
                "hx_target": "#main-content",
                "class": "btn-ghost",
            },
        ]

        # Use shared dashboard component
        return await SharedUIComponents.render_entity_dashboard(
            title="🧠 Knowledge Base",
            stats=stats_formatted,
            entities=knowledge_units,
            entity_renderer=KuUIComponents.render_ku_card,
            quick_actions=quick_actions,
            categories=domains,
            filter_endpoint="/ku/filter",
            request=request,
            active_page="knowledge",
        )

    # NOTE: render_knowledge_stats(), render_action_buttons(), render_recent_knowledge(),
    # render_knowledge_graph_overview(), and render_all_knowledge() have been REMOVED.
    # These are now handled by SharedUIComponents.render_entity_dashboard().
    # Removed ~140 lines of duplicate code.

    @staticmethod
    def render_ku_card(unit, compact=False) -> Any:
        """
        Individual KU card component.

        ✅ USES CardGenerator for 100% dynamic display generation.
        Expects Ku dataclass instances (follows "Models define structure → UI auto-generates").
        """
        uid = unit.uid

        # Custom renderer for connections count (computed field not in Ku dataclass)
        def render_connections(value) -> Any:
            return Span(
                f"🔗 {value} connections" if value > 0 else "🔗 No connections",
                cls="text-sm text-blue-600",
            )

        # Display fields based on compact mode
        display_fields = (
            ["title", "domain", "tags"]
            if compact
            else ["title", "content", "domain", "tags", "complexity"]
        )

        # Generate card using CardGenerator (100% dynamic architecture)
        card = CardGenerator.from_dataclass(
            unit,
            display_fields=display_fields,
            field_renderers={
                # If connections_count was a field, would render it here
                # For now, we'll add it manually after card generation
            },
            card_attrs={"id": f"knowledge-{uid}", "cls": "border-l-4 border-blue-500 p-4"},
        )

        # Action buttons
        buttons = [
            Button(
                "👁️ View",
                variant=ButtonT.outline,
                cls="btn-sm",
                hx_get=f"/ku/{uid}/details",
                hx_target="#modal" if compact else "#main-content",
            ),
            Button(
                "✏️ Edit",
                variant=ButtonT.ghost,
                cls="btn-sm",
                hx_get=f"/ku/{uid}/edit",
                hx_target="#modal",
            ),
        ]

        if not compact:
            buttons.append(
                Button(
                    "🕸️ Graph",
                    variant=ButtonT.secondary,
                    cls="btn-sm",
                    hx_get=f"/ku/{uid}/graph",
                    hx_target="#main-content",
                )
            )

        # Wrap card with action buttons
        return Card(Div(card, Div(*buttons, cls="flex gap-2 mt-3"), cls="p-4"))

    @staticmethod
    def render_create_ku_form() -> Any:
        """
        Create KU form component.

        ✅ MIGRATED: Now uses FormGenerator for 100% dynamic form generation.
        Previously: 72 lines of manual form composition.
        Now: 15 lines using introspection-based generation.
        """
        return Card(
            H2("🧠 Create Knowledge Unit", cls="text-xl font-bold mb-4"),
            FormGenerator.from_model(
                KuCreateRequest,
                action="/api/ku",
                method="POST",
                include_fields=[
                    "title",
                    "content",
                    "domain",
                    "tags",
                    "prerequisites",
                    "complexity",
                ],
                form_attrs={
                    "hx_post": "/api/ku",
                    "hx_target": "#knowledge-container",
                    "hx_swap": "outerHTML",
                },
                submit_label="Create Knowledge",
            ),
            cls="p-6 max-w-2xl mx-auto",
        )

    @staticmethod
    def render_ku_discovery_dashboard() -> Any:
        """KU discovery dashboard component"""
        return Div(
            H1("🔍 Knowledge Discovery", cls="text-2xl font-bold mb-6"),
            # Discovery tools
            Card(
                H3("🎯 Discovery Tools", cls="text-lg font-semibold mb-4"),
                Div(
                    Button("🔗 Find Connections", variant=ButtonT.primary, cls="btn-sm mr-2"),
                    Button("📈 Trending Topics", variant=ButtonT.secondary, cls="btn-sm mr-2"),
                    Button("🕳️ Knowledge Gaps", variant=ButtonT.outline, cls="btn-sm"),
                ),
                cls="p-6 mb-6",
            ),
            # Recommended knowledge
            Card(
                H3("💡 Recommended for You", cls="text-lg font-semibold mb-4"),
                P("Personalized knowledge recommendations will appear here", cls="text-gray-500"),
                cls="p-6 mb-6",
            ),
            # Knowledge paths
            Card(
                H3("🛤️ Learning Paths", cls="text-lg font-semibold mb-4"),
                P("Suggested learning paths based on your interests", cls="text-gray-500"),
                cls="p-6",
            ),
            cls="container mx-auto p-6",
        )

    @staticmethod
    def render_ku_analytics_dashboard() -> Any:
        """KU analytics dashboard component"""
        return Div(
            H1("📊 Knowledge Analytics", cls="text-2xl font-bold mb-6"),
            # Growth metrics
            Card(
                H3("📈 Growth Metrics", cls="text-lg font-semibold mb-4"),
                P("Knowledge base growth and usage analytics", cls="text-gray-500"),
                cls="p-6 mb-6",
            ),
            # Connection analysis
            Card(
                H3("🕸️ Connection Analysis", cls="text-lg font-semibold mb-4"),
                P("Knowledge graph connectivity and relationship insights", cls="text-gray-500"),
                cls="p-6 mb-6",
            ),
            # Domain insights
            Card(
                H3("🎯 Domain Insights", cls="text-lg font-semibold mb-4"),
                P("Knowledge distribution and domain expertise mapping", cls="text-gray-500"),
                cls="p-6",
            ),
            cls="container mx-auto p-6",
        )


# ============================================================================
# PURE COMPUTATION HELPERS (Testable without mocks)
# ============================================================================


def validate_ku_form_data(form_data: dict[str, Any]) -> Result[None]:
    """
    Validate KU form data early.

    Pure function: returns clear error messages for UI.

    Args:
        form_data: Raw form data from request

    Returns:
        Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
    """
    from core.models.shared_enums import Domain
    from core.utils.result_simplified import Errors, Result

    # Required: title
    title = form_data.get("title", "").strip()
    if not title:
        return Result.fail(Errors.validation("KU title is required"))
    if len(title) > 200:
        return Result.fail(Errors.validation("Title must be 200 characters or less"))

    # Required: content
    content = form_data.get("content", "").strip()
    if not content:
        return Result.fail(Errors.validation("KU content is required"))

    # Required: domain
    domain = form_data.get("domain", "").strip()
    if not domain:
        return Result.fail(Errors.validation("KU domain is required"))

    # Validate domain is valid enum value
    try:
        Domain(domain)
    except ValueError:
        valid_domains = [d.value for d in Domain]
        return Result.fail(
            Errors.validation(f"Invalid domain. Must be one of: {', '.join(valid_domains)}")
        )

    # Optional: complexity (if provided, must be valid)
    complexity = form_data.get("complexity", "").strip()
    if complexity and complexity not in ["basic", "medium", "advanced"]:
        return Result.fail(Errors.validation("Complexity must be 'basic', 'medium', or 'advanced'"))

    return Result.ok(None)


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


@dataclass
class KuFilters:
    """Typed filters for KU list queries."""

    domain: str


def parse_ku_filters(request: Request) -> KuFilters:
    """
    Extract KU filter parameters from request query params.

    Args:
        request: Starlette request object

    Returns:
        Typed KuFilters with defaults applied
    """
    return KuFilters(
        domain=request.query_params.get("domain", "all"),
    )


# ============================================================================
# CLEAN UI ROUTES - Component-based rendering only
# ============================================================================


def create_ku_ui_routes(_app, rt, ku_service):
    """
    Create clean UI routes using component composition.

    Each route renders components, no inline HTML composition.
    """

    logger.info("KU UI routes registered (component-based)")

    # ========================================================================
    # MAIN UI PAGES
    # ========================================================================

    @rt("/ku")
    async def ku_dashboard(request) -> Any:
        """Main KU hub — tabs + sidebar + KU cards."""
        from ui.layouts.base_page import BasePage
        from ui.layouts.page_types import PageType
        from ui.patterns.page_header import PageHeader

        # Determine active SEL tab from query param
        sel_param = request.query_params.get("sel", "all")

        content = Div(
            PageHeader(
                "Knowledge",
                subtitle="Explore, learn, and grow across SEL competencies",
            ),
            # Journey progress (loaded via HTMX)
            Div(
                Div(
                    P(
                        "Loading your learning journey...",
                        cls="text-center py-4 text-base-content/70",
                    ),
                    cls="animate-pulse",
                ),
                hx_get="/api/ku/journey-html",
                hx_trigger="load",
                hx_swap="innerHTML",
                id="ku-journey",
                cls="mb-6",
            ),
            # SEL category tabs
            _ku_tabs(active_tab=sel_param),
            # KU cards (loaded via HTMX, filtered by tab)
            Div(
                Div(
                    P("Loading knowledge units...", cls="text-center py-8 text-base-content/70"),
                    cls="animate-pulse",
                ),
                hx_get=f"/ku/filter?sel_category={sel_param}"
                if sel_param != "all"
                else "/ku/filter",
                hx_trigger="load",
                hx_swap="innerHTML",
                id="ku-content",
            ),
        )

        page_layout = _ku_page_layout(sel_param, content)

        return await BasePage(
            page_layout,
            title="Knowledge",
            page_type=PageType.STANDARD,
            request=request,
            active_page="knowledge",
            extra_css=["/static/css/profile_sidebar.css"],
        )

    @rt("/ku/create")
    async def knowledge_create_form(_request) -> Any:
        """Create knowledge form - pure component"""
        return KuUIComponents.render_create_ku_form()

    @rt("/ku/discovery")
    async def knowledge_discovery_dashboard(_request) -> Any:
        """Discovery dashboard - pure component"""
        return KuUIComponents.render_ku_discovery_dashboard()

    @rt("/ku/analytics")
    async def knowledge_analytics_dashboard(_request) -> Any:
        """Analytics dashboard - pure component"""
        return KuUIComponents.render_ku_analytics_dashboard()

    @rt("/ku/graph")
    async def knowledge_graph_page(_request) -> Any:
        """Knowledge graph page - pure component"""
        return Card(
            H1("🕸️ Knowledge Graph", cls="text-2xl font-bold mb-6"),
            P(
                "Interactive knowledge graph visualization will be implemented here",
                cls="text-gray-500",
            ),
            cls="p-6 container mx-auto",
        )

    # ========================================================================
    # HTMX FRAGMENT ENDPOINTS
    # ========================================================================

    @rt("/ku/filter")
    async def knowledge_filter_fragment(request) -> Any:
        """Return filtered KU cards — supports domain and sel_category filters."""
        from ui.patterns.error_banner import render_error_banner

        # Parse filters
        filters = parse_ku_filters(request)
        sel_category = request.query_params.get("sel_category", "")

        # Fetch knowledge from service
        if (
            ku_service
            and getattr(ku_service, "core", None)
            and getattr(ku_service.core, "backend", None)
        ):
            # If SEL category filter, use backend.find_by
            if sel_category and sel_category != "all":
                result = await ku_service.core.backend.find_by(sel_category=sel_category)
            else:
                result = await ku_service.core.list(limit=50)

            if result.is_error:
                return render_error_banner("Unable to load knowledge units.", result.error.message)

            knowledge = result.value if result.value else []

            # Apply domain filter if specified
            if filters.domain and filters.domain != "all":
                knowledge = [
                    k
                    for k in knowledge
                    if str(getattr(k, "domain", "")).upper() == filters.domain.upper()
                ]
        else:
            knowledge = []

        return (
            Div(
                *[KuUIComponents.render_ku_card(unit) for unit in knowledge],
                cls="grid grid-cols-1 md:grid-cols-2 gap-4",
            )
            if knowledge
            else P("No knowledge units found", cls="text-center text-base-content/70 py-8")
        )

    @rt("/ku/moc-nav")
    async def moc_nav_fragment(request) -> Any:
        """HTMX: Load MOC navigation list for sidebar."""
        # Placeholder — will be populated when MOCs exist
        return P("No Maps of Content yet", cls="text-xs opacity-50 px-2")

    @rt("/ku/{uid}/details")
    async def knowledge_details_modal(_request, uid: str) -> Any:
        """Knowledge details modal fragment"""
        return Card(
            H2("🧠 Knowledge Details", cls="text-xl font-bold mb-4"),
            P(
                f"Detailed view for knowledge unit {uid} will be implemented here",
                cls="text-gray-500",
            ),
            cls="p-6",
        )

    @rt("/ku/{uid}/edit")
    async def knowledge_edit_form(_request, uid: str) -> Any:
        """Edit knowledge form fragment"""
        return Card(
            H2("✏️ Edit Knowledge", cls="text-xl font-bold mb-4"),
            P(f"Edit form for knowledge unit {uid} will be implemented here", cls="text-gray-500"),
            cls="p-6",
        )

    @rt("/ku/{uid}/graph")
    async def knowledge_graph_view(_request, uid: str) -> Any:
        """Knowledge graph view centered on specific unit"""
        return Card(
            H2("🕸️ Knowledge Graph", cls="text-xl font-bold mb-4"),
            P(
                f"Graph view centered on knowledge unit {uid} will be implemented here",
                cls="text-gray-500",
            ),
            cls="p-6",
        )

    # ========================================================================
    # JAVASCRIPT INTEGRATION
    # ========================================================================

    @rt("/static/js/knowledge.js")
    async def knowledge_javascript(_request) -> Any:
        """Serve knowledge-specific JavaScript"""
        js_content = """
        // Knowledge UI JavaScript - no more inline scripts in routes!

        function closeModal() {
            document.getElementById('modal').innerHTML = '';
        }

        function refreshKnowledge() {
            htmx.trigger('#knowledge-container', 'refresh');
        }

        function expandKnowledgeCard(uid) {
            htmx.ajax('GET', `/ku/${uid}/details`, '#knowledge-details');
        }

        // HTMX event handlers
        document.addEventListener('htmx:afterSwap', function(evt) {
            if (evt.detail.target.id === 'knowledge-list') {
                console.log('Knowledge list updated');
            }
        });

        console.log('Knowledge UI JavaScript loaded');
        """

        return Response(js_content, media_type="application/javascript")

    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_ku_ui_routes"]
