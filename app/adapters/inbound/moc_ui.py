"""
MOC (Map of Content) UI Routes - Non-Linear Knowledge Navigation
================================================================

UI/HTMX routes for Map of Content browsing, creation, and management.

MOC provides non-linear knowledge organization complementing linear Learning Paths.
Think of MOC as "Wikipedia-style" navigation vs LP's "course-style" learning.

Key Features:
- Hierarchical section navigation
- Cross-domain content bridges
- Practice recommendations per section
- Template library for common knowledge structures

Design Philosophy:
- LP is linear: "Step 1 -> Step 2 -> Step 3"
- MOC is non-linear: "Browse everything about Python by topic"
- MOC and LP are complementary, not competing
"""

__version__ = "1.0"

from typing import TYPE_CHECKING, Any

from fasthtml.common import H1, H2, H3, A, Li, P, Ul
from starlette.responses import Response

from components.shared_ui_components import SharedUIComponents
from core.auth import get_current_user_or_default, require_authenticated_user
from core.ui.daisy_components import Button, Card, Div, Span
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.services.moc_service import MOCService

logger = get_logger("skuel.routes.moc.ui")


# ============================================================================
# UI COMPONENT LIBRARY - Reusable MOC components
# ============================================================================


class MOCUIComponents:
    """Centralized MOC UI components for consistent rendering."""

    @staticmethod
    def render_moc_dashboard(
        mocs: list | None = None, stats: dict | None = None, request=None
    ) -> Any:
        """
        Main MOC dashboard - browse all user's Maps of Content.

        Shows:
        - Stats overview
        - Quick actions (create, templates, discovery)
        - List of user's MOCs with section counts
        """
        mocs = mocs or []
        stats = stats or {}

        # Transform stats to shared format
        stats_formatted = {
            "total": {
                "label": "Maps of Content",
                "value": stats.get("total_mocs", 0),
                "color": "blue",
            },
            "sections": {
                "label": "Total Sections",
                "value": stats.get("total_sections", 0),
                "color": "green",
            },
            "knowledge": {
                "label": "Knowledge Units",
                "value": stats.get("total_knowledge", 0),
                "color": "purple",
            },
            "domains": {
                "label": "Domains Covered",
                "value": stats.get("domains_count", 0),
                "color": "orange",
            },
        }

        # Quick actions
        quick_actions = [
            {
                "label": "+ New MOC",
                "hx_get": "/moc/create",
                "hx_target": "#modal",
                "class": "btn-primary",
            },
            {
                "label": "Templates",
                "hx_get": "/moc/templates",
                "hx_target": "#main-content",
                "class": "btn-secondary",
            },
            {
                "label": "Discovery",
                "hx_get": "/moc/discovery",
                "hx_target": "#main-content",
                "class": "btn-outline",
            },
        ]

        return SharedUIComponents.render_entity_dashboard(
            title="Maps of Content",
            stats=stats_formatted,
            entities=mocs,
            entity_renderer=MOCUIComponents.render_moc_card,
            quick_actions=quick_actions,
            categories=[],  # MOCs don't have fixed categories
            filter_endpoint="/moc/filter",
            request=request,
            active_page="moc",
        )

    @staticmethod
    def render_moc_card(moc: Any, compact: bool = False) -> Any:
        """
        Individual MOC card showing title, domain, and section overview.

        Args:
            moc: MapOfContent instance or dict with MOC data
            compact: If True, show minimal info
        """
        # Handle both dict and object
        if isinstance(moc, dict):
            uid = moc.get("uid", "")
            title = moc.get("title", "Untitled MOC")
            description = moc.get("description", "")
            domain = moc.get("domain", "")
            section_count = len(moc.get("sections", []))
            is_template = moc.get("is_template", False)
        else:
            uid = getattr(moc, "uid", "")
            title = getattr(moc, "title", "Untitled MOC")
            description = getattr(moc, "description", "")
            domain = getattr(moc, "domain", "")
            sections = getattr(moc, "sections", ())
            section_count = len(sections) if sections else 0
            is_template = getattr(moc, "is_template", False)

        # Domain display
        domain_display = str(domain).replace("Domain.", "") if domain else "General"

        # Template badge
        template_badge = (
            Span("Template", cls="badge badge-secondary text-xs ml-2") if is_template else None
        )

        if compact:
            return Card(
                Div(
                    H3(title, cls="font-semibold text-lg"),
                    template_badge,
                    cls="flex items-center",
                ),
                Div(
                    Span(f"{section_count} sections", cls="text-sm text-gray-500"),
                    Span(" | ", cls="text-gray-300"),
                    Span(domain_display, cls="text-sm text-blue-600"),
                ),
                hx_get=f"/moc/{uid}",
                hx_target="#main-content",
                cls="p-4 cursor-pointer hover:bg-gray-50",
            )

        return Card(
            Div(
                Div(
                    H3(title, cls="font-semibold text-lg"),
                    template_badge,
                    cls="flex items-center",
                ),
                P(
                    description[:150] + "..." if len(description) > 150 else description,
                    cls="text-gray-600 mt-2",
                )
                if description
                else None,
                Div(
                    Span(f"{section_count} sections", cls="text-sm text-gray-500 mr-4"),
                    Span(domain_display, cls="badge badge-outline"),
                    cls="flex items-center mt-3",
                ),
                cls="p-4",
            ),
            Div(
                Button(
                    "View",
                    hx_get=f"/moc/{uid}",
                    hx_target="#main-content",
                    cls="btn btn-sm btn-primary",
                ),
                Button(
                    "Edit",
                    hx_get=f"/moc/{uid}/edit",
                    hx_target="#modal",
                    cls="btn btn-sm btn-outline ml-2",
                ),
                cls="px-4 pb-4",
            ),
            cls="border rounded-lg hover:shadow-md transition-shadow",
        )

    @staticmethod
    def render_moc_detail(moc: Any) -> Any:
        """
        Detailed MOC view with hierarchical section navigation.

        Shows:
        - MOC header with stats
        - Hierarchical section tree
        - Content items per section
        - Cross-domain bridges
        """
        # Handle both dict and object
        if isinstance(moc, dict):
            uid = moc.get("uid", "")
            title = moc.get("title", "Untitled MOC")
            description = moc.get("description", "")
            domain = moc.get("domain", "")
            sections = moc.get("sections", [])
        else:
            uid = getattr(moc, "uid", "")
            title = getattr(moc, "title", "Untitled MOC")
            description = getattr(moc, "description", "")
            domain = getattr(moc, "domain", "")
            sections = getattr(moc, "sections", ())

        domain_display = str(domain).replace("Domain.", "") if domain else "General"

        # Build section tree
        section_items = []
        for section in sections:
            section_title = (
                section.get("title", "")
                if isinstance(section, dict)
                else getattr(section, "title", "")
            )
            section_uid = (
                section.get("uid", "") if isinstance(section, dict) else getattr(section, "uid", "")
            )

            section_items.append(
                Li(
                    A(
                        section_title,
                        hx_get=f"/moc/{uid}/section/{section_uid}",
                        hx_target="#section-content",
                        cls="cursor-pointer hover:text-blue-600",
                    ),
                    cls="py-2 border-b last:border-0",
                )
            )

        return Div(
            # Header
            Div(
                Div(
                    Button(
                        "< Back",
                        hx_get="/moc",
                        hx_target="#main-content",
                        cls="btn btn-sm btn-ghost",
                    ),
                    H1(title, cls="text-2xl font-bold ml-4"),
                    cls="flex items-center",
                ),
                P(description, cls="text-gray-600 mt-2") if description else None,
                Div(
                    Span(domain_display, cls="badge badge-primary"),
                    Span(f"{len(sections)} sections", cls="text-sm text-gray-500 ml-4"),
                    cls="flex items-center mt-4",
                ),
                cls="mb-6",
            ),
            # Two-column layout: sections tree + content
            Div(
                # Left sidebar: Section tree
                Div(
                    H3("Sections", cls="font-semibold text-lg mb-4"),
                    Ul(*section_items, cls="space-y-1")
                    if section_items
                    else P("No sections yet", cls="text-gray-500"),
                    Button(
                        "+ Add Section",
                        hx_get=f"/moc/{uid}/section/create",
                        hx_target="#modal",
                        cls="btn btn-sm btn-outline mt-4 w-full",
                    ),
                    cls="w-1/3 pr-6 border-r",
                ),
                # Right content: Selected section content
                Div(
                    id="section-content",
                    cls="w-2/3 pl-6",
                )(
                    P(
                        "Select a section to view its content",
                        cls="text-gray-500 text-center py-12",
                    )
                ),
                cls="flex",
            ),
            cls="container mx-auto p-6",
        )

    @staticmethod
    def render_moc_create_form() -> Any:
        """Create MOC form."""
        from core.models.shared_enums import Domain

        domain_options = [
            (d.value, d.value.replace("_", " ").title())
            for d in Domain
            if d not in (Domain.ALL, Domain.SYSTEM, Domain.CROSS_DOMAIN)
        ]

        return Card(
            H2("Create Map of Content", cls="text-xl font-bold mb-6"),
            Div(
                # Title
                Div(
                    Span("Title", cls="label-text"),
                    cls="label",
                ),
                Div(
                    tag="input",
                    type="text",
                    name="title",
                    placeholder="e.g., Python Programming Guide",
                    cls="input input-bordered w-full",
                ),
                # Description
                Div(
                    Span("Description", cls="label-text"),
                    cls="label mt-4",
                ),
                Div(
                    tag="textarea",
                    name="description",
                    placeholder="Brief description of what this MOC covers...",
                    cls="textarea textarea-bordered w-full",
                    rows="3",
                ),
                # Domain
                Div(
                    Span("Domain", cls="label-text"),
                    cls="label mt-4",
                ),
                Div(
                    tag="select",
                    name="domain",
                    cls="select select-bordered w-full",
                )(*[Div(tag="option", value=value)(label) for value, label in domain_options]),
                # Template toggle
                Div(
                    Div(
                        tag="input",
                        type="checkbox",
                        name="is_template",
                        cls="checkbox checkbox-primary",
                    ),
                    Span("Make this a template (others can copy)", cls="label-text ml-2"),
                    cls="flex items-center mt-6",
                ),
                # Submit
                Div(
                    Button(
                        "Cancel",
                        type="button",
                        onclick="closeModal()",
                        cls="btn btn-ghost mr-2",
                    ),
                    Button(
                        "Create MOC",
                        type="submit",
                        cls="btn btn-primary",
                    ),
                    cls="flex justify-end mt-6",
                ),
                tag="form",
                hx_post="/api/moc",
                hx_target="#main-content",
                hx_swap="innerHTML",
            ),
            cls="p-6",
        )

    @staticmethod
    def render_template_library(templates: list | None = None) -> Any:
        """Template library for browsing and instantiating MOC templates."""
        templates = templates or []

        return Div(
            H1("MOC Template Library", cls="text-2xl font-bold mb-6"),
            P(
                "Browse and use pre-built Maps of Content to organize your knowledge.",
                cls="text-gray-600 mb-6",
            ),
            Div(
                *[MOCUIComponents.render_moc_card(t, compact=False) for t in templates],
                cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
            )
            if templates
            else P(
                "No templates available yet. Create a MOC and mark it as a template to share!",
                cls="text-gray-500 text-center py-12",
            ),
            cls="container mx-auto p-6",
        )


# ============================================================================
# ROUTE FACTORY
# ============================================================================


def create_moc_ui_routes(app, rt, moc_service: "MOCService"):
    """
    Create MOC UI routes using component composition.

    Routes:
    - /moc - Dashboard listing all user MOCs
    - /moc/create - Create new MOC form
    - /moc/templates - Template library
    - /moc/discovery - Related MOC discovery
    - /moc/{uid} - MOC detail view with sections
    - /moc/{uid}/edit - Edit MOC form
    - /moc/{uid}/section/{section_uid} - Section content view
    """

    logger.info("Registering MOC UI routes (component-based)")

    # ========================================================================
    # MAIN UI PAGES
    # ========================================================================

    @rt("/moc")
    async def moc_dashboard(request) -> Any:
        """Main MOC dashboard - list all user's MOCs."""
        _user_uid = require_authenticated_user(request)  # Auth required; filtering TODO

        # Fetch real MOCs from service
        mocs = []
        if moc_service:
            result = await moc_service.list_root_mocs()
            if result.is_ok:
                mocs = result.value

        # Calculate stats from real data
        total_sections = sum(len(getattr(m, "sections", [])) for m in mocs)
        domains = set(getattr(m, "domain", None) for m in mocs if getattr(m, "domain", None))
        stats = {
            "total_mocs": len(mocs),
            "total_sections": total_sections,
            "total_knowledge": 0,
            "domains_count": len(domains),
        }

        return MOCUIComponents.render_moc_dashboard(mocs=mocs, stats=stats, request=request)

    @rt("/moc/create")
    async def moc_create_form(request) -> Any:
        """Create MOC form modal."""
        return MOCUIComponents.render_moc_create_form()

    @rt("/moc/templates")
    async def moc_template_library(request) -> Any:
        """Template library page."""
        # TODO: Template functionality not yet implemented in MOCService
        templates: list[Any] = []

        return MOCUIComponents.render_template_library(templates=templates)

    @rt("/moc/discovery")
    async def moc_discovery_page(request) -> Any:
        """Discovery page for finding related MOCs."""
        return Card(
            H1("MOC Discovery", cls="text-2xl font-bold mb-6"),
            P(
                "Find MOCs related to your knowledge and learning paths.",
                cls="text-gray-500",
            ),
            P("Discovery features coming soon...", cls="text-gray-400 mt-4"),
            cls="p-6 container mx-auto",
        )

    @rt("/moc/{uid}")
    async def moc_detail(request, uid: str) -> Any:
        """MOC detail view with section navigation."""
        user_uid = get_current_user_or_default(request)

        try:
            # Fetch MOC from service
            moc_result = await moc_service.get(uid, user_uid)

            # Handle service errors
            if moc_result.is_error:
                logger.warning(f"Failed to load MOC {uid}: {moc_result.expect_error().message}")
                return Div(
                    H1("📚 Map of Content", cls="text-3xl font-bold mb-6"),
                    Card(
                        P(
                            f"Failed to load MOC: {moc_result.expect_error().message}",
                            cls="text-error",
                        ),
                        Button(
                            "< Back",
                            hx_get="/moc",
                            hx_target="#main-content",
                            cls="btn btn-sm btn-ghost mt-4",
                        ),
                        cls="p-6",
                    ),
                    cls="container mx-auto p-6",
                )

            moc = moc_result.value

            # Transform to dict if needed (service returns domain model)
            moc_dict = {
                "uid": moc.uid,
                "title": moc.title,
                "description": moc.description or "",
                "domain": getattr(moc, "domain", "GENERAL"),
                "sections": [],  # GRAPH-NATIVE: sections stored as ORGANIZES relationships
            }

            # TODO: Fetch sections via relationship query
            # sections_result = await moc_service.get_organized_content(uid, user_uid)

            return MOCUIComponents.render_moc_detail(moc=moc_dict)

        except Exception as e:
            logger.error(f"Unexpected error loading MOC {uid}: {e}")
            return Div(
                H1("📚 Map of Content", cls="text-3xl font-bold mb-6"),
                Card(
                    P(f"Unexpected error: {e!s}", cls="text-error"),
                    Button(
                        "< Back",
                        hx_get="/moc",
                        hx_target="#main-content",
                        cls="btn btn-sm btn-ghost mt-4",
                    ),
                    cls="p-6",
                ),
                cls="container mx-auto p-6",
            )

    @rt("/moc/{uid}/edit")
    async def moc_edit_form(request, uid: str) -> Any:
        """Edit MOC form modal."""
        return Card(
            H2("Edit MOC", cls="text-xl font-bold mb-4"),
            P(f"Edit form for MOC {uid} will be implemented here", cls="text-gray-500"),
            cls="p-6",
        )

    @rt("/moc/{uid}/section/{section_uid}")
    async def moc_section_content(request, uid: str, section_uid: str) -> Any:
        """Section content view - shows knowledge units in this section."""
        return Div(
            H3("Section Content", cls="font-semibold text-lg mb-4"),
            P(f"Content for section {section_uid} in MOC {uid}", cls="text-gray-600 mb-4"),
            # Would show actual knowledge units here
            Div(
                Card(
                    H3("Python Variables", cls="font-medium"),
                    P("Understanding variable types and scope.", cls="text-gray-600 text-sm"),
                    cls="p-3 border-l-4 border-blue-500",
                ),
                Card(
                    H3("Python Functions", cls="font-medium"),
                    P(
                        "Function definitions, arguments, and return values.",
                        cls="text-gray-600 text-sm",
                    ),
                    cls="p-3 border-l-4 border-blue-500 mt-3",
                ),
                cls="space-y-2",
            ),
            Button(
                "+ Add Content",
                hx_get=f"/moc/{uid}/section/{section_uid}/add-content",
                hx_target="#modal",
                cls="btn btn-sm btn-outline mt-4",
            ),
        )

    @rt("/moc/{uid}/section/create")
    async def moc_section_create_form(request, uid: str) -> Any:
        """Create section form modal."""
        return Card(
            H2("Add Section", cls="text-xl font-bold mb-4"),
            Div(
                Div(
                    Span("Section Title", cls="label-text"),
                    cls="label",
                ),
                Div(
                    tag="input",
                    type="text",
                    name="title",
                    placeholder="e.g., Advanced Concepts",
                    cls="input input-bordered w-full",
                ),
                Div(
                    Span("Description (optional)", cls="label-text"),
                    cls="label mt-4",
                ),
                Div(
                    tag="textarea",
                    name="description",
                    placeholder="What this section covers...",
                    cls="textarea textarea-bordered w-full",
                    rows="2",
                ),
                Div(
                    Button(
                        "Cancel", type="button", onclick="closeModal()", cls="btn btn-ghost mr-2"
                    ),
                    Button("Add Section", type="submit", cls="btn btn-primary"),
                    cls="flex justify-end mt-6",
                ),
                tag="form",
                hx_post=f"/api/moc/{uid}/sections",
                hx_target="#main-content",
            ),
            cls="p-6",
        )

    @rt("/moc/filter")
    async def moc_filter_fragment(request) -> Any:
        """Filter MOCs by domain (HTMX fragment)."""
        params = dict(request.query_params)
        params.get("domain", "all")

        # Would filter from service
        return P("Filtered MOCs will appear here", cls="text-gray-500")

    # ========================================================================
    # JAVASCRIPT
    # ========================================================================

    @rt("/static/js/moc.js")
    async def moc_javascript(request) -> Any:
        """MOC-specific JavaScript."""
        js_content = """
        // MOC UI JavaScript

        function closeModal() {
            document.getElementById('modal').innerHTML = '';
        }

        function refreshMOC() {
            htmx.trigger('#moc-container', 'refresh');
        }

        console.log('MOC UI JavaScript loaded');
        """
        return Response(js_content, media_type="application/javascript")

    logger.info("MOC UI routes registered successfully")

    return []


# Export
__all__ = ["MOCUIComponents", "create_moc_ui_routes"]
