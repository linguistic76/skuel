"""
Principles UI Routes - Three-View Standalone Interface
======================================================

Three-view principle management UI with List, Create, and Analytics views.
Analytics as third tab (not Calendar - principles are not time-based).

Routes (order matters for path parameter matching):
- GET /principles - Main dashboard with three views (standalone, no drawer)
- GET /principles/view/list - HTMX fragment for list view (default)
- GET /principles/view/create - HTMX fragment for create view
- GET /principles/view/analytics - HTMX fragment for analytics view
- GET /principles/list-fragment - HTMX filtered list (for filter updates)
- POST /principles/quick-add - Create principle via form (MUST be before {uid} routes)
- GET /principles/{uid} - View single principle (parameterized route - last)

NOTE: The /principles/quick-add route MUST be registered BEFORE /principles/{uid}
to avoid the path parameter matching "quick-add" as a uid value.
"""

__version__ = "2.0"

from dataclasses import dataclass
from typing import Any, cast

from fasthtml.common import H1, H2, H3, Div, P, Span
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.route_factories import QuickAddConfig, QuickAddRouteFactory
from adapters.inbound.ui_helpers import render_safe_error_response
from core.constants import QueryLimit
from core.ports.query_types import PrinciplesFilterSpec
from core.services.principles_service import PrinciplesService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_created_at_attr, get_title_or_name_lower
from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.error_banner import render_error_banner
from ui.patterns.relationships import EntityRelationshipsSection
from ui.principles.layout import create_principles_page
from ui.principles.views import PrinciplesViewComponents
from ui.tokens import Container, Spacing

logger = get_logger("skuel.routes.principles.ui")


# RouteDecorator and Request imported from adapters.inbound.fasthtml_types

# ============================================================================
# UI ROUTES
# ============================================================================


def create_principles_ui_routes(
    _app, rt, principles_service: PrinciplesService, services: Any = None
):
    """
    Create three-view principle UI routes (standalone, analytics as third tab).

    Views:
    - List: Sortable, filterable principle list (DEFAULT)
    - Create: Principle creation form
    - Analytics: Principle adherence and impact analysis

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        principles_service: Principles service
        services: Full services container (unused, kept for API compatibility)
    """

    logger.info("Registering three-view principle routes (standalone, analytics)")

    # ========================================================================
    # QUERY PARAM TYPES
    # ========================================================================

    @dataclass
    class Filters:
        """Typed filters for principle list queries."""

        category: str
        strength: str
        sort_by: str

    # ========================================================================
    # HELPER FUNCTIONS
    # ========================================================================

    def parse_filters(request) -> Filters:
        """Extract filter parameters from request query params."""
        return Filters(
            category=request.query_params.get("filter_category", "all"),
            strength=request.query_params.get("filter_strength", "all"),
            sort_by=request.query_params.get("sort_by", "strength"),
        )

    # ========================================================================
    # DATA FETCHING HELPERS
    # ========================================================================

    async def get_all_principles(user_uid: str) -> Result[list[Any]]:
        """Get all principles for user from service."""
        try:
            if principles_service:
                result = await principles_service.get_user_principles(user_uid)
                if result.is_error:
                    logger.warning(f"Failed to fetch principles: {result.error}")
                    return result  # Propagate the error
                return Result.ok(result.value or [])
            return Result.ok([])
        except Exception as e:
            logger.error(
                "Error fetching all principles",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to fetch principles: {e}"))

    # ========================================================================
    # PURE COMPUTATION HELPERS (Testable without mocks)
    # ========================================================================

    def validate_principle_form_data(form_data: dict[str, Any]) -> Result[None]:
        """
        Validate principle form data early.

        Pure function: returns clear error messages for UI.

        Args:
            form_data: Raw form data from request

        Returns:
            Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
        """
        # Required fields
        title = form_data.get("title", "").strip()
        if not title:
            return Result.fail(Errors.validation("Principle title is required"))

        if len(title) > 200:
            return Result.fail(Errors.validation("Principle title must be 200 characters or less"))

        return Result.ok(None)

    def get_strength_value(p, strength_order: dict[Any, int]) -> int:
        """
        Get numeric strength value for comparison.

        Pure function: testable without database or async.

        Args:
            p: Principle entity
            strength_order: Mapping of PrincipleStrength to numeric values

        Returns:
            Numeric strength value (1-5)
        """
        from core.models.enums.principle_enums import PrincipleStrength

        s = getattr(p, "strength", PrincipleStrength.MODERATE)
        if isinstance(s, PrincipleStrength):
            result: int = strength_order.get(s, 3)
            return result
        # Handle string values
        if isinstance(s, str):
            s_upper = s.upper()
            for enum_val in PrincipleStrength:
                if enum_val.value == s or enum_val.name == s_upper:
                    result2: int = strength_order.get(enum_val, 3)
                    return result2
        return 3  # Default to moderate

    def compute_principle_stats(principles: list[Any], strength_order: dict) -> dict[str, int]:
        """
        Calculate principle statistics.

        Pure function: testable without database or async.

        Args:
            principles: List of principle entities
            strength_order: Mapping of PrincipleStrength to numeric values

        Returns:
            Stats dict with total, core, active counts
        """

        def get_strength(p) -> int:
            return get_strength_value(p, strength_order)

        return {
            "total": len(principles),
            "core": sum(1 for p in principles if get_strength(p) >= 5),
            "active": sum(1 for p in principles if getattr(p, "is_active", True)),
        }

    def apply_principle_filters(
        principles: list[Any],
        category_filter: str = "all",
        strength_filter: str = "all",
        strength_order: dict | None = None,
    ) -> list[Any]:
        """
        Apply filter criteria to principle list.

        Pure function: testable without database or async.

        Args:
            principles: List of principle entities
            category_filter: Category filter (all, or specific category)
            strength_filter: Strength filter (all, core, strong, developing, aspirational)
            strength_order: Mapping of PrincipleStrength to numeric values

        Returns:
            Filtered list of principles
        """

        def get_strength(p) -> int:
            return get_strength_value(p, strength_order or {})

        # Filter: category
        if category_filter != "all":
            principles = [
                p
                for p in principles
                if str(getattr(p, "category", "")).lower().replace("principlecategory.", "")
                == category_filter.lower()
            ]

        # Filter: strength
        if strength_filter == "core":
            principles = [p for p in principles if get_strength(p) >= 5]
        elif strength_filter == "strong":
            principles = [p for p in principles if get_strength(p) == 4]
        elif strength_filter == "developing":
            principles = [p for p in principles if get_strength(p) in (2, 3)]
        elif strength_filter == "aspirational":
            principles = [p for p in principles if get_strength(p) <= 1]
        # "all" shows everything

        return principles

    def apply_principle_sort(
        principles: list[Any], sort_by: str = "strength", strength_order: dict | None = None
    ) -> list[Any]:
        """
        Sort principles by specified field.

        Pure function: testable without database or async.

        Args:
            principles: List of principle entities
            sort_by: Sort field (strength, title, created_at)
            strength_order: Mapping of PrincipleStrength to numeric values

        Returns:
            Sorted list of principles
        """

        def get_strength(p) -> int:
            return get_strength_value(p, strength_order or {})

        if sort_by == "strength":
            return sorted(principles, key=get_strength, reverse=True)
        elif sort_by == "title":
            return sorted(principles, key=get_title_or_name_lower)
        elif sort_by == "created_at":
            return sorted(principles, key=get_created_at_attr, reverse=True)
        else:
            # Default: strength
            return sorted(principles, key=get_strength, reverse=True)

    async def get_filtered_principles(
        user_uid: str,
        category_filter: str = "all",
        strength_filter: str = "all",
        sort_by: str = "strength",
    ) -> Result[tuple[list[Any], dict[str, int]]]:
        """
        Get filtered and sorted principles for user.

        Orchestrates: fetch (I/O) → stats → filter → sort.
        Pure computation delegated to testable helper functions.
        """
        from core.models.enums.principle_enums import PrincipleStrength

        # Map PrincipleStrength enum to numeric values for sorting/filtering
        strength_order = {
            PrincipleStrength.CORE: 5,
            PrincipleStrength.STRONG: 4,
            PrincipleStrength.MODERATE: 3,
            PrincipleStrength.DEVELOPING: 2,
            PrincipleStrength.EXPLORING: 1,
        }

        try:
            # I/O: Fetch all principles
            principles_result = await get_all_principles(user_uid)
            if principles_result.is_error:
                return Result.fail(principles_result)

            principles = principles_result.value

            # Computation: Calculate stats BEFORE filtering
            stats = compute_principle_stats(principles, strength_order)

            # Computation: Apply filters
            filtered_principles = apply_principle_filters(
                principles, category_filter, strength_filter, strength_order
            )

            # Computation: Apply sort
            sorted_principles = apply_principle_sort(filtered_principles, sort_by, strength_order)

            return Result.ok((sorted_principles, stats))

        except Exception as e:
            logger.error(
                "Error filtering principles",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to filter principles: {e}"))

    async def get_categories() -> Result[list[str]]:
        """Get available principle categories."""
        try:
            return Result.ok(
                [
                    "spiritual",
                    "ethical",
                    "relational",
                    "personal",
                    "professional",
                    "intellectual",
                    "health",
                    "creative",
                ]
            )
        except Exception as e:
            logger.error(
                "Error fetching categories",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to fetch categories: {e}"))

    async def get_analytics_data(user_uid: str) -> Result[dict[str, Any]]:
        """Get analytics data for user."""
        try:
            principles_result = await get_all_principles(user_uid)

            # Check for errors
            if principles_result.is_error:
                logger.warning(f"Failed to get principles for analytics: {principles_result.error}")
                return Result.fail(principles_result)  # Propagate the error

            principles = principles_result.value

            # Calculate analytics
            total = len(principles)
            core_count = sum(1 for p in principles if getattr(p, "strength", 0) >= 0.9)
            active_count = sum(1 for p in principles if getattr(p, "is_active", True))

            # Calculate average adherence from alignment service if available
            overall_adherence = 0.0
            alignment = (
                getattr(principles_service, "alignment", None) if principles_service else None
            )
            if alignment:
                try:
                    adherence_result = await alignment.calculate_average_alignment(user_uid)
                    if not adherence_result.is_error:
                        overall_adherence = adherence_result.value
                except Exception as e:
                    logger.warning(f"Could not calculate adherence: {e}")

            # Get recent reflections from reflection service
            recent_reflections: list = []
            reflection = (
                getattr(principles_service, "reflection", None) if principles_service else None
            )
            if reflection:
                try:
                    reflections_result = await reflection.get_recent_reflections(
                        user_uid, days=7, limit=10
                    )
                    if not reflections_result.is_error:
                        recent_reflections = reflections_result.value
                except Exception as e:
                    logger.warning(f"Could not get recent reflections: {e}")

            return Result.ok(
                {
                    "total_principles": total,
                    "overall_adherence": overall_adherence,
                    "core_count": core_count,
                    "active_count": active_count,
                    "reflections": recent_reflections,
                }
            )
        except Exception as e:
            logger.error(
                "Error getting analytics data",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to get analytics: {e}"))

    # ========================================================================
    # MAIN DASHBOARD (Standalone Three-View, List First)
    # ========================================================================

    @rt("/principles")
    async def principles_dashboard(request) -> Any:
        """Main principles dashboard with three views (standalone, no drawer)."""
        user_uid = require_authenticated_user(request)

        # Get view parameter (default to list for principles)
        view = request.query_params.get("view", "list")

        # Parse filters using helper
        filters = parse_filters(request)

        # Render the appropriate view content
        if view == "create":
            categories_result = await get_categories()

            # Check for errors
            if categories_result.is_error:
                error_content = Div(
                    PrinciplesViewComponents.render_view_tabs(active_view=view),
                    render_error_banner("Failed to load categories"),
                    cls=f"{Spacing.PAGE} {Container.WIDE}",
                )
                return await create_principles_page(error_content, request=request)

            view_content = PrinciplesViewComponents.render_create_view(
                categories=categories_result.value,
            )
        elif view == "analytics":
            analytics_result = await get_analytics_data(user_uid)

            # Check for errors
            if analytics_result.is_error:
                error_content = Div(
                    PrinciplesViewComponents.render_view_tabs(active_view=view),
                    render_error_banner("Failed to load analytics"),
                    cls=f"{Spacing.PAGE} {Container.WIDE}",
                )
                return await create_principles_page(error_content, request=request)

            view_content = PrinciplesViewComponents.render_analytics_view(
                analytics_data=analytics_result.value,
            )
        else:  # list (default for principles)
            filtered_result = await get_filtered_principles(
                user_uid, filters.category, filters.strength, filters.sort_by
            )

            # Check for errors
            if filtered_result.is_error:
                error_content = Div(
                    PrinciplesViewComponents.render_view_tabs(active_view=view),
                    render_error_banner("Failed to load principles"),
                    cls=f"{Spacing.PAGE} {Container.WIDE}",
                )
                return await create_principles_page(error_content, request=request)

            principles, stats = filtered_result.value
            categories_result = await get_categories()

            # Check categories error
            if categories_result.is_error:
                error_content = Div(
                    PrinciplesViewComponents.render_view_tabs(active_view=view),
                    render_error_banner("Failed to load categories"),
                    cls=f"{Spacing.PAGE} {Container.WIDE}",
                )
                return await create_principles_page(error_content, request=request)

            view_content = PrinciplesViewComponents.render_list_view(
                principles=principles,
                filters={
                    "category": filters.category,
                    "strength": filters.strength,
                    "sort_by": filters.sort_by,
                },
                stats=stats,
                categories=categories_result.value,
            )

        # Build page with tabs + view content
        page_content = Div(
            PrinciplesViewComponents.render_view_tabs(active_view=view),
            Div(view_content, id="view-content", role="tabpanel"),
            cls=f"{Spacing.PAGE} {Container.WIDE}",
        )

        return await create_principles_page(page_content, request=request)

    # ========================================================================
    # HTMX VIEW FRAGMENTS
    # ========================================================================

    @rt("/principles/view/list")
    async def principles_view_list(request) -> Any:
        """HTMX fragment for list view (default for principles)."""
        user_uid = require_authenticated_user(request)

        # Parse filters using helper
        filters = parse_filters(request)

        filtered_result = await get_filtered_principles(
            user_uid, filters.category, filters.strength, filters.sort_by
        )

        # Handle errors (return banner directly for HTMX swap)
        if filtered_result.is_error:
            return render_error_banner("Failed to load principles")

        principles, stats = filtered_result.value
        categories_result = await get_categories()

        # Handle categories error
        if categories_result.is_error:
            return render_error_banner("Failed to load categories")

        filter_spec: PrinciplesFilterSpec = {
            "category": filters.category,
            "strength": filters.strength,
            "sort_by": filters.sort_by,
        }
        return PrinciplesViewComponents.render_list_view(
            principles=principles,
            filters=filter_spec,
            stats=stats,
            categories=categories_result.value,
        )

    @rt("/principles/view/create")
    async def principles_view_create(request) -> Any:
        """HTMX fragment for create view."""
        require_authenticated_user(request)
        categories_result = await get_categories()

        # Handle errors (return banner directly for HTMX swap)
        if categories_result.is_error:
            return render_error_banner("Failed to load categories")

        return PrinciplesViewComponents.render_create_view(
            categories=categories_result.value,
        )

    @rt("/principles/view/analytics")
    async def principles_view_analytics(request) -> Any:
        """HTMX fragment for analytics view."""
        user_uid = require_authenticated_user(request)
        analytics_result = await get_analytics_data(user_uid)

        # Handle errors (return banner directly for HTMX swap)
        if analytics_result.is_error:
            return render_error_banner("Failed to load analytics")

        return PrinciplesViewComponents.render_analytics_view(
            analytics_data=analytics_result.value,
        )

    # ========================================================================
    # LIST FRAGMENT (for filter updates)
    # ========================================================================

    @rt("/principles/list-fragment")
    async def principles_list_fragment(request) -> Any:
        """Return filtered principle list for HTMX updates."""
        user_uid = require_authenticated_user(request)

        # Parse filters using helper
        filters = parse_filters(request)

        filtered_result = await get_filtered_principles(
            user_uid, filters.category, filters.strength, filters.sort_by
        )

        # Handle errors (return banner directly for HTMX swap)
        if filtered_result.is_error:
            return render_error_banner("Failed to load principles")

        principles, _stats = filtered_result.value

        # Return just the principle items
        principle_items = [
            PrinciplesViewComponents._render_principle_item(principle) for principle in principles
        ]

        return Div(
            *principle_items
            if principle_items
            else [P("No principles found.", cls="text-base-content/60 text-center py-8")],
            id="principle-list",
            cls="space-y-3",
        )

    # ========================================================================
    # QUICK ADD (must be BEFORE {uid} routes to avoid path parameter conflict)
    # ========================================================================

    async def create_principle_from_form(form_data: dict[str, Any], user_uid: str) -> Result[Any]:
        """
        Domain-specific principle creation logic.

        Handles form parsing, enum conversion, and service call with named parameters.
        """
        from core.models.enums.principle_enums import PrincipleCategory, PrincipleStrength

        # VALIDATE EARLY
        validation_result = validate_principle_form_data(form_data)
        if validation_result.is_error:
            return validation_result  # Return validation error to UI

        # Extract form data
        title = form_data.get("title", "").strip()
        description = form_data.get("description", "").strip() or ""
        statement = form_data.get("statement", "").strip() or title
        category_str = form_data.get("category", "personal")
        strength_str = form_data.get("strength", "0.5")
        is_active = form_data.get("is_active", "") == "true"

        # Parse category
        try:
            category = PrincipleCategory(category_str.upper())
        except ValueError:
            category = PrincipleCategory.PERSONAL

        # Parse strength (convert float to enum)
        try:
            strength_val = float(strength_str)
            if strength_val >= 0.9:
                strength = PrincipleStrength.CORE
            elif strength_val >= 0.7:
                strength = PrincipleStrength.STRONG
            elif strength_val >= 0.4:
                strength = PrincipleStrength.MODERATE
            else:
                strength = PrincipleStrength.DEVELOPING
        except ValueError:
            strength = PrincipleStrength.MODERATE

        # Call service with named parameters
        return cast(
            "Result[Any]",
            await principles_service.core.create_principle(
                label=title,
                description=statement or description,
                category=category,
                why_matters=description,
                user_uid=user_uid,
                strength=strength,
                is_active=is_active,
            ),
        )

    async def render_principle_success_view(user_uid: str) -> Any:
        """Render list view after successful principle creation."""
        filtered_result = await get_filtered_principles(user_uid, "all", "all", "strength")

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load principles")

        principles, stats = filtered_result.value
        categories_result = await get_categories()

        # Handle categories error
        if categories_result.is_error:
            return render_error_banner("Failed to load categories")

        filters: PrinciplesFilterSpec = {
            "category": "all",
            "strength": "all",
            "sort_by": "strength",
        }
        return PrinciplesViewComponents.render_list_view(
            principles=principles,
            filters=filters,
            stats=stats,
            categories=categories_result.value,
        )

    async def render_principle_add_another_view(user_uid: str) -> Any:
        """Render create view for add-another flow."""
        categories_result = await get_categories()

        # Handle errors
        if categories_result.is_error:
            return render_error_banner("Failed to load categories")

        return PrinciplesViewComponents.render_create_view(
            categories=categories_result.value,
        )

    # Register quick-add route via factory
    # NOTE: Must be registered BEFORE {uid} routes to avoid path parameter conflict
    principles_quick_add_config = QuickAddConfig(
        domain_name="principles",
        required_field="title",
        create_entity=create_principle_from_form,
        render_success_view=render_principle_success_view,
        render_add_another_view=render_principle_add_another_view,
    )
    QuickAddRouteFactory.register_route(rt, principles_quick_add_config)

    # ========================================================================
    # INDIVIDUAL PRINCIPLE ROUTES
    # ========================================================================

    @rt("/principles/{uid}")
    async def view_principle(request, uid: str) -> Any:
        """View a single principle with recent reflections."""
        from core.models.enums.principle_enums import PrincipleStrength

        user_uid = require_authenticated_user(request)

        # Fetch principle with ownership verification
        result = await principles_service.get_for_user(uid, user_uid)

        if result.is_error or result.value is None:
            logger.error(
                f"Failed to get principle {uid}: {result.error if result.is_error else 'Not found'}"
            )
            return await BasePage(
                content=Card(
                    H2("Principle Not Found", cls="text-xl font-bold text-error mb-4"),
                    P(f"Could not find principle: {uid}", cls="text-base-content/70"),
                    Button(
                        "← Back to Principles",
                        **{"hx-get": "/principles", "hx-target": "body"},
                        variant=ButtonT.primary,
                        cls="mt-4",
                    ),
                    cls="p-6",
                ),
                title="Principle Not Found",
                page_type=PageType.STANDARD,
                request=request,
                active_page="principles",
            )

        principle = result.value

        # Extract principle fields
        name = getattr(principle, "name", "Untitled")
        statement = getattr(principle, "statement", "")
        description = getattr(principle, "description", "")
        why_important = getattr(principle, "why_important", "")
        category = getattr(principle, "category", "personal")
        strength = getattr(principle, "strength", PrincipleStrength.MODERATE)
        is_active = getattr(principle, "is_active", True)

        strength_str = (
            strength.value if isinstance(strength, PrincipleStrength) else str(strength).lower()
        )
        category_str = str(category).lower().replace("principlecategory.", "")

        # Fetch recent reflections for this principle
        recent_reflections = []
        reflections_result = await principles_service.reflection.get_reflections_for_principle(
            principle_uid=uid,
            user_uid=user_uid,
            limit=5,
        )
        if not reflections_result.is_error:
            recent_reflections = reflections_result.value

        # Build reflection section
        reflection_section = None
        if recent_reflections:
            reflection_cards = [
                PrinciplesViewComponents._render_reflection_card(r) for r in recent_reflections[:3]
            ]
        else:
            reflection_cards = [
                P("No reflections recorded yet.", cls="text-base-content/60 text-center py-4")
            ]

        reflection_section = Div(
            Div(
                H3("Recent Reflections", cls="text-lg font-semibold"),
                Button(
                    "View All",
                    cls="btn btn-xs btn-outline",
                    **{
                        "hx-get": f"/principles/{uid}/reflections",
                        "hx-target": "#view-content",
                    },
                ),
                cls="flex items-center justify-between mb-4",
            ),
            Div(*reflection_cards, cls="space-y-3"),
            cls="card bg-base-100 shadow-lg p-6 mt-4",
        )

        # Build detail content inline
        # Wrap in view-content so HTMX fragment swaps (reflections, history) have a target
        content = Div(
            # Main card
            Card(
                H1(name, cls="text-2xl font-bold mb-2"),
                Span(strength_str.title(), cls="badge badge-primary mr-2"),
                Span(category_str.title(), cls="badge badge-outline"),
                Span("Inactive", cls="badge badge-ghost ml-2") if not is_active else "",
                # Statement
                P(statement, cls="text-lg text-base-content/70 mt-4 italic") if statement else "",
                # Description
                (
                    Div(
                        H3("Description", cls="font-semibold mt-6 mb-2"),
                        P(description or "No description provided.", cls="text-base-content/70"),
                    )
                    if description
                    else ""
                ),
                # Why Important
                (
                    Div(
                        H3("Why This Matters", cls="font-semibold mt-6 mb-2"),
                        P(why_important or "Not specified.", cls="text-base-content/70"),
                    )
                    if why_important
                    else ""
                ),
                cls="p-6 mb-4",
            ),
            # Actions Card
            Card(
                Div(
                    Button(
                        "← Back to Principles",
                        **{"hx-get": "/principles", "hx-target": "body"},
                        variant=ButtonT.ghost,
                        cls="mr-2",
                    ),
                    Button(
                        "✏️ Edit",
                        **{"hx-get": f"/principles/{uid}/edit", "hx-target": "#modal"},
                        variant=ButtonT.primary,
                        cls="mr-2",
                    ),
                    (
                        Button(
                            "🪞 Reflect",
                            **{"hx-get": f"/principles/{uid}/reflect", "hx-target": "#modal"},
                            variant=ButtonT.success,
                            cls="mr-2",
                        )
                        if is_active
                        else ""
                    ),
                    Button(
                        "📜 View History",
                        **{
                            "hx-get": f"/principles/{uid}/reflections",
                            "hx-target": "#view-content",
                        },
                        variant=ButtonT.info,
                    ),
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-4 mb-4",
            ),
            # Recent reflections section
            reflection_section,
            # Lateral Relationships Section
            EntityRelationshipsSection(
                entity_uid=uid,
                entity_type="principles",
            ),
            id="view-content",
            cls=f"{Container.STANDARD} {Spacing.PAGE}",
        )

        return await BasePage(
            content=content,
            title=name,
            page_type=PageType.STANDARD,
            request=request,
            active_page="principles",
        )

    @rt("/principles/{uid}/edit")
    async def edit_principle_form(request, uid: str) -> Any:
        """Return edit form for a principle (modal)."""
        user_uid = require_authenticated_user(request)

        if not principles_service:
            return Response("Service unavailable", status_code=503)

        # Ownership verification - returns NotFound if user doesn't own this principle
        result = await principles_service.core.verify_ownership(uid, user_uid)
        if result.is_error:
            return Response(f"Principle not found: {uid}", status_code=404)

        principle = result.value
        categories_result = await get_categories()

        # Handle categories error
        if categories_result.is_error:
            return render_error_banner("Failed to load categories")

        return PrinciplesViewComponents.render_edit_form(principle, categories_result.value)

    @rt("/principles/{uid}/save", methods=["POST"])
    async def save_principle(request, uid: str) -> Any:
        """Save principle edits."""
        user_uid = require_authenticated_user(request)

        if not principles_service:
            return Response("Service unavailable", status_code=503)

        # Ownership verification before mutation
        ownership_result = await principles_service.core.verify_ownership(uid, user_uid)
        if ownership_result.is_error:
            return Response(f"Principle not found: {uid}", status_code=404)

        form = await request.form()

        # Extract form data
        name = form.get("name", "").strip()
        description = form.get("description", "").strip() or None
        statement = form.get("statement", "").strip() or None
        category_str = form.get("category", "personal")
        is_active = form.get("is_active", "") == "true"

        # Build updates dict
        updates = {
            "name": name,
            "description": description,
            "statement": statement or name,
            "category": category_str.upper(),
            "is_active": is_active,
        }

        result = await principles_service.core.update_principle(uid, updates)
        if result.is_error:
            return render_safe_error_response(
                user_message="Failed to update principle",
                error_context=result.error,
                logger_instance=logger,
                log_extra={"principle_uid": uid, "user_uid": user_uid},
                status_code=500,
            )

        # Return updated list view
        filtered_result = await get_filtered_principles(user_uid, "all", "all", "strength")

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load principles")

        principles, stats = filtered_result.value
        categories_result = await get_categories()

        # Handle categories error
        if categories_result.is_error:
            return render_error_banner("Failed to load categories")

        filters: PrinciplesFilterSpec = {
            "category": "all",
            "strength": "all",
            "sort_by": "strength",
        }
        return PrinciplesViewComponents.render_list_view(
            principles=principles,
            filters=filters,
            stats=stats,
            categories=categories_result.value,
        )

    @rt("/principles/{uid}/reflect")
    async def reflect_principle_form(request, uid: str) -> Any:
        """Return reflection form for a principle (modal)."""
        user_uid = require_authenticated_user(request)

        if not principles_service:
            return Response("Service unavailable", status_code=503)

        # Ownership verification - returns NotFound if user doesn't own this principle
        result = await principles_service.core.verify_ownership(uid, user_uid)
        if result.is_error:
            return Response(f"Principle not found: {uid}", status_code=404)

        principle = result.value
        return PrinciplesViewComponents.render_reflect_form(principle)

    @rt("/principles/{uid}/reflections")
    async def get_principle_reflections(request, uid: str) -> Any:
        """Get reflection history for a principle."""
        user_uid = require_authenticated_user(request)

        if not principles_service:
            return Response("Service unavailable", status_code=503)

        # Ownership verification - returns NotFound if user doesn't own this principle
        principle_result = await principles_service.core.verify_ownership(uid, user_uid)
        if principle_result.is_error:
            return Response(f"Principle not found: {uid}", status_code=404)

        # Get reflections
        result = await principles_service.reflection.get_reflections_for_principle(
            principle_uid=uid,
            user_uid=user_uid,
            limit=QueryLimit.DEFAULT,
        )

        if result.is_error:
            return render_safe_error_response(
                user_message="Failed to get reflections",
                error_context=result.error,
                logger_instance=logger,
                log_extra={"principle_uid": uid, "user_uid": user_uid},
                status_code=500,
            )

        reflections = result.value

        # Return reflection history component
        return PrinciplesViewComponents.render_reflection_history(
            principle=principle_result.value,
            reflections=reflections,
        )

    @rt("/principles/{uid}/alignment-trend")
    async def get_alignment_trend(request, uid: str) -> Any:
        """Get alignment trend data for a principle."""
        user_uid = require_authenticated_user(request)

        if not principles_service:
            return Response("Service unavailable", status_code=503)

        days = int(request.query_params.get("days", "30"))

        result = await principles_service.reflection.calculate_alignment_trend(
            principle_uid=uid,
            user_uid=user_uid,
            days=days,
        )

        if result.is_error:
            return render_safe_error_response(
                user_message="Failed to get trend",
                error_context=result.error,
                logger_instance=logger,
                log_extra={"principle_uid": uid, "user_uid": user_uid},
                status_code=500,
            )

        trend = result.value

        # Return trend component
        return PrinciplesViewComponents.render_alignment_trend(trend)

    @rt("/principles/{uid}/reflect/save", methods=["POST"])
    async def save_reflection(request, uid: str) -> Any:
        """Save a reflection on a principle (persisted to graph)."""
        from core.models.enums.principle_enums import AlignmentLevel

        user_uid = require_authenticated_user(request)

        if not principles_service:
            return Response("Service unavailable", status_code=503)

        form = await request.form()
        alignment_str = form.get("alignment_level", "partial")
        reflection_notes = form.get("reflection", "").strip() or None
        evidence = form.get("evidence", "").strip()

        # Trigger fields (optional)
        trigger_type = form.get("trigger_type", "manual").strip() or "manual"
        trigger_uid = form.get("trigger_uid", "").strip() or None
        trigger_context = form.get("trigger_context", "").strip() or None

        # Clear trigger_uid if type is manual (no entity associated)
        if trigger_type == "manual":
            trigger_uid = None

        # Fallback evidence if not provided (shouldn't happen with required field)
        if not evidence:
            evidence = reflection_notes[:100] if reflection_notes else "Reflection recorded"

        # Parse alignment level
        alignment_map = {
            "aligned": AlignmentLevel.ALIGNED,
            "mostly_aligned": AlignmentLevel.MOSTLY_ALIGNED,
            "partial": AlignmentLevel.PARTIAL,
            "partially_aligned": AlignmentLevel.PARTIAL,
            "misaligned": AlignmentLevel.MISALIGNED,
            "unknown": AlignmentLevel.UNKNOWN,
        }
        alignment_level = alignment_map.get(alignment_str.lower(), AlignmentLevel.PARTIAL)

        # Save reflection via service
        result = await principles_service.reflection.save_reflection(
            principle_uid=uid,
            user_uid=user_uid,
            alignment_level=alignment_level,
            evidence=evidence,
            reflection_notes=reflection_notes if reflection_notes else None,
            trigger_type=trigger_type,
            trigger_uid=trigger_uid,
            trigger_context=trigger_context,
        )

        if result.is_error:
            return render_safe_error_response(
                user_message="Failed to save reflection",
                error_context=result.error,
                logger_instance=logger,
                log_extra={"principle_uid": uid, "user_uid": user_uid},
                status_code=500,
            )

        logger.info(f"Reflection saved: {result.value.uid} for principle {uid}")

        # Return to list view
        filtered_result = await get_filtered_principles(user_uid, "all", "all", "strength")

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load principles")

        principles, stats = filtered_result.value
        categories_result = await get_categories()

        # Handle categories error
        if categories_result.is_error:
            return render_error_banner("Failed to load categories")

        filters: PrinciplesFilterSpec = {
            "category": "all",
            "strength": "all",
            "sort_by": "strength",
        }
        return PrinciplesViewComponents.render_list_view(
            principles=principles,
            filters=filters,
            stats=stats,
            categories=categories_result.value,
        )

    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_principles_ui_routes"]
