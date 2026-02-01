"""
Knowledge UI Routes - Clean Component-Based UI
==============================================

UI/HTMX routes using pure component composition for knowledge management.

Thin routes that:
- Render components
- Handle HTMX interactions
- Return HTML fragments

No JSON API logic, no manual UI composition in routes.
"""

__version__ = "1.0"


from typing import Any

from fasthtml.common import H1, H2, H3, P
from starlette.responses import Response

from components.card_generator import CardGenerator
from components.form_generator import FormGenerator
from components.shared_ui_components import SharedUIComponents
from core.models.ku.ku_request import KuCreateRequest
from core.ui.daisy_components import Button, ButtonT, Card, Div, Span
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.knowledge.ui")


# ============================================================================
# UI COMPONENT LIBRARY - Reusable knowledge components
# ============================================================================


class KnowledgeUIComponents:
    """Centralized knowledge UI components - no more inline composition"""

    @staticmethod
    def render_knowledge_dashboard(
        knowledge_units=None, stats=None, domains=None, request=None
    ) -> Any:
        """
        Main knowledge dashboard - REFACTORED to use SharedUIComponents.

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
                "hx_get": "/knowledge/create",
                "hx_target": "#modal",
                "class": "btn-primary",
            },
            {
                "label": "🔍 Discovery",
                "hx_get": "/knowledge/discovery",
                "hx_target": "#main-content",
                "class": "btn-secondary",
            },
            {
                "label": "📊 Analytics",
                "hx_get": "/knowledge/analytics",
                "hx_target": "#main-content",
                "class": "btn-outline",
            },
            {
                "label": "🕸️ Graph View",
                "hx_get": "/knowledge/graph",
                "hx_target": "#main-content",
                "class": "btn-ghost",
            },
        ]

        # Use shared dashboard component
        return SharedUIComponents.render_entity_dashboard(
            title="🧠 Knowledge Base",
            stats=stats_formatted,
            entities=knowledge_units,
            entity_renderer=KnowledgeUIComponents.render_knowledge_card,
            quick_actions=quick_actions,
            categories=domains,
            filter_endpoint="/knowledge/filter",
            request=request,
            active_page="knowledge",
        )

    # NOTE: render_knowledge_stats(), render_action_buttons(), render_recent_knowledge(),
    # render_knowledge_graph_overview(), and render_all_knowledge() have been REMOVED.
    # These are now handled by SharedUIComponents.render_entity_dashboard().
    # Removed ~140 lines of duplicate code.

    @staticmethod
    def render_knowledge_card(unit, compact=False) -> Any:
        """
        Individual knowledge unit card component.

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
                hx_get=f"/knowledge/{uid}/details",
                hx_target="#modal" if compact else "#main-content",
            ),
            Button(
                "✏️ Edit",
                variant=ButtonT.ghost,
                cls="btn-sm",
                hx_get=f"/knowledge/{uid}/edit",
                hx_target="#modal",
            ),
        ]

        if not compact:
            buttons.append(
                Button(
                    "🕸️ Graph",
                    variant=ButtonT.secondary,
                    cls="btn-sm",
                    hx_get=f"/knowledge/{uid}/graph",
                    hx_target="#main-content",
                )
            )

        # Wrap card with action buttons
        return Card(Div(card, Div(*buttons, cls="flex gap-2 mt-3"), cls="p-4"))

    @staticmethod
    def render_create_knowledge_form() -> Any:
        """
        Create knowledge form component.

        ✅ MIGRATED: Now uses FormGenerator for 100% dynamic form generation.
        Previously: 72 lines of manual form composition.
        Now: 15 lines using introspection-based generation.
        """
        return Card(
            H2("🧠 Create Knowledge Unit", cls="text-xl font-bold mb-4"),
            FormGenerator.from_model(
                KuCreateRequest,
                action="/api/knowledge",
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
                    "hx_post": "/api/knowledge",
                    "hx_target": "#knowledge-container",
                    "hx_swap": "outerHTML",
                },
                submit_label="Create Knowledge",
            ),
            cls="p-6 max-w-2xl mx-auto",
        )

    @staticmethod
    def render_knowledge_discovery_dashboard() -> Any:
        """Knowledge discovery dashboard component"""
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
    def render_knowledge_analytics_dashboard() -> Any:
        """Knowledge analytics dashboard component"""
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


def validate_ku_form_data(form_data: dict[str, Any]) -> "Result[None]":
    """
    Validate knowledge unit form data early.

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
        return Result.fail(Errors.validation("Knowledge title is required"))
    if len(title) > 200:
        return Result.fail(Errors.validation("Title must be 200 characters or less"))

    # Required: content
    content = form_data.get("content", "").strip()
    if not content:
        return Result.fail(Errors.validation("Knowledge content is required"))

    # Required: domain
    domain = form_data.get("domain", "").strip()
    if not domain:
        return Result.fail(Errors.validation("Knowledge domain is required"))

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
        return Result.fail(
            Errors.validation("Complexity must be 'basic', 'medium', or 'advanced'")
        )

    return Result.ok(None)


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


from dataclasses import dataclass
from starlette.requests import Request


@dataclass
class KnowledgeFilters:
    """Typed filters for knowledge unit list queries."""

    domain: str


def parse_knowledge_filters(request: Request) -> KnowledgeFilters:
    """
    Extract knowledge filter parameters from request query params.

    Args:
        request: Starlette request object

    Returns:
        Typed KnowledgeFilters with defaults applied
    """
    return KnowledgeFilters(
        domain=request.query_params.get("domain", "all"),
    )


# ============================================================================
# CLEAN UI ROUTES - Component-based rendering only
# ============================================================================


def create_knowledge_ui_routes(_app, rt, ku_service):
    """
    Create clean UI routes using component composition.

    Each route renders components, no inline HTML composition.
    """

    logger.info("Knowledge UI routes registered (component-based)")

    # ========================================================================
    # MAIN UI PAGES
    # ========================================================================

    @rt("/knowledge")
    async def knowledge_dashboard(request) -> Any:
        """Main knowledge dashboard - pure component rendering"""
        from ui.layouts.base_page import BasePage
        from ui.patterns.error_banner import render_error_banner

        # Fetch real knowledge units from service
        # KU is shared curriculum content (not user-owned)
        if ku_service and hasattr(ku_service, "core") and hasattr(ku_service.core, "backend"):
            result = await ku_service.core.list(limit=50)

            # Check for errors FIRST, show user-friendly message
            if result.is_error:
                return BasePage(
                    content=render_error_banner(
                        "Unable to load knowledge units. Please try again later.",
                        result.error.message
                    ),
                    title="Knowledge",
                    request=request
                )

            knowledge = result.value if result.value else []
        else:
            knowledge = []

        # Calculate stats from real data
        domains = set(getattr(k, "domain", None) for k in knowledge if getattr(k, "domain", None))
        stats = {
            "total_units": len(knowledge),
            "total_connections": 0,
            "domains_count": len(domains),
            "learning_paths": 0,
        }

        return KnowledgeUIComponents.render_knowledge_dashboard(
            knowledge_units=knowledge, stats=stats, request=request
        )

    @rt("/knowledge/create")
    async def knowledge_create_form(_request) -> Any:
        """Create knowledge form - pure component"""
        return KnowledgeUIComponents.render_create_knowledge_form()

    @rt("/knowledge/discovery")
    async def knowledge_discovery_dashboard(_request) -> Any:
        """Discovery dashboard - pure component"""
        return KnowledgeUIComponents.render_knowledge_discovery_dashboard()

    @rt("/knowledge/analytics")
    async def knowledge_analytics_dashboard(_request) -> Any:
        """Analytics dashboard - pure component"""
        return KnowledgeUIComponents.render_knowledge_analytics_dashboard()

    @rt("/knowledge/graph")
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

    @rt("/knowledge/filter")
    async def knowledge_filter_fragment(request) -> Any:
        """Return filtered knowledge fragment for HTMX updates"""
        from ui.patterns.error_banner import render_error_banner

        # Parse typed filters
        filters = parse_knowledge_filters(request)

        # Fetch real knowledge from service
        if ku_service and hasattr(ku_service, "core") and hasattr(ku_service.core, "backend"):
            result = await ku_service.core.list(limit=50)

            # Check for errors FIRST, show user-friendly message
            if result.is_error:
                return render_error_banner(
                    "Unable to load knowledge units. Please try again later.",
                    result.error.message
                )

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
                *[KnowledgeUIComponents.render_knowledge_card(unit) for unit in knowledge],
                cls="space-y-3",
            )
            if knowledge
            else P("No knowledge units found for this domain", cls="text-center text-gray-500 py-8")
        )

    @rt("/knowledge/{uid}/details")
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

    @rt("/knowledge/{uid}/edit")
    async def knowledge_edit_form(_request, uid: str) -> Any:
        """Edit knowledge form fragment"""
        return Card(
            H2("✏️ Edit Knowledge", cls="text-xl font-bold mb-4"),
            P(f"Edit form for knowledge unit {uid} will be implemented here", cls="text-gray-500"),
            cls="p-6",
        )

    @rt("/knowledge/{uid}/graph")
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
            htmx.ajax('GET', `/knowledge/${uid}/details`, '#knowledge-details');
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
__all__ = ["create_knowledge_ui_routes"]
