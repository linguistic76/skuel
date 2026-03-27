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

from typing import Any, cast

from fasthtml.common import H1, H3, Div, P
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.form_helpers import (
    PrincipleFilters,
    parse_enum_safe,
    parse_principle_filters,
    safe_form_string,
)
from adapters.inbound.route_factories import (
    DashboardUIConfig,
    DashboardUIFactory,
    QuickAddConfig,
    QuickAddRouteFactory,
    parse_int_query_param,
    require_owned_entity,
)
from adapters.inbound.ui_helpers import (
    render_entity_not_found_page,
    render_safe_error_response,
)
from core.constants import QueryLimit
from core.models.enums.principle_enums import AlignmentLevel, PrincipleCategory, PrincipleStrength
from core.models.type_hints import UserUID
from core.services.principles_service import PrinciplesService
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.page_contexts import PrinciplesPageContext
from ui.patterns.empty_state import EmptyState
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


# ============================================================================
# Form Parsing Helpers (pure — no service calls, no request access)
# ============================================================================


def parse_principle_create_params(form_data: dict[str, Any]) -> dict[str, Any]:
    """Parse form data into kwargs for create_principle(). Pure function, no side effects."""
    title = safe_form_string(form_data.get("title"))
    description = safe_form_string(form_data.get("description"))
    statement = safe_form_string(form_data.get("statement")) or title
    category_str = safe_form_string(form_data.get("category")) or "personal"
    strength_str = safe_form_string(form_data.get("strength")) or "0.5"
    is_active = safe_form_string(form_data.get("is_active")) == "true"

    # Parse category
    category = parse_enum_safe(PrincipleCategory, category_str.upper(), PrincipleCategory.PERSONAL)

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

    return {
        "label": title,
        "description": statement or description,
        "category": category,
        "why_matters": description,
        "strength": strength,
        "is_active": is_active,
    }


def parse_principle_update_payload(form: Any) -> dict[str, Any]:
    """Parse edit form into an update dict. Pure function, no side effects."""
    name = safe_form_string(form.get("name"))
    description = safe_form_string(form.get("description")) or None
    statement = safe_form_string(form.get("statement")) or None
    category_str = safe_form_string(form.get("category")) or "personal"
    is_active = safe_form_string(form.get("is_active")) == "true"

    return {
        "name": name,
        "description": description,
        "statement": statement or name,
        "category": category_str.upper(),
        "is_active": is_active,
    }


def parse_reflection_params(form: Any) -> dict[str, Any]:
    """Parse reflection form into kwargs for save_reflection(). Pure function, no side effects."""
    alignment_str = safe_form_string(form.get("alignment_level")) or "partial"
    reflection_notes = safe_form_string(form.get("reflection")) or None
    evidence = safe_form_string(form.get("evidence"))

    # Trigger fields (optional)
    trigger_type = safe_form_string(form.get("trigger_type")) or "manual"
    trigger_uid = safe_form_string(form.get("trigger_uid")) or None
    trigger_context = safe_form_string(form.get("trigger_context")) or None

    # Clear trigger_uid if type is manual (no entity associated)
    if trigger_type == "manual":
        trigger_uid = None

    # Fallback evidence if not provided
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

    return {
        "alignment_level": alignment_level,
        "evidence": evidence,
        "reflection_notes": reflection_notes if reflection_notes else None,
        "trigger_type": trigger_type,
        "trigger_uid": trigger_uid,
        "trigger_context": trigger_context,
    }


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
    # DATA FETCHING HELPERS
    # ========================================================================

    def _get_principle_categories() -> list[str]:
        """Get available principle categories from PrincipleCategory enum."""
        return [c.value for c in PrincipleCategory]

    # ========================================================================
    # DASHBOARD + VIEW FRAGMENTS (via DashboardUIFactory)
    # ========================================================================

    async def fetch_principles_context(user_uid: UserUID, filters: PrincipleFilters) -> Any:
        """Fetch filtered principles context from service."""
        return await principles_service.get_filtered_context(
            user_uid, filters.category, filters.strength, filters.sort_by, filters.status
        )

    def build_principles_page_context(svc_ctx: dict[str, Any], filters: PrincipleFilters) -> Any:
        """Map service context to PrinciplesPageContext."""
        return PrinciplesPageContext(
            entities=svc_ctx["entities"],
            filters=filters.to_dict(),
            stats=svc_ctx["stats"],
            categories=svc_ctx.get("metadata", {}).get("categories", []),
        )

    async def render_principles_create(user_uid: UserUID, svc_ctx: dict[str, Any]) -> Any:
        """Render principles create view."""
        return PrinciplesViewComponents.render_create_view(
            categories=_get_principle_categories(),
        )

    async def render_principles_analytics(user_uid: UserUID, request: Any) -> Any:
        """Render principles analytics view."""
        analytics_result = await principles_service.get_analytics_summary(user_uid)
        if analytics_result.is_error:
            return render_error_banner("Failed to load analytics")
        return PrinciplesViewComponents.render_analytics_view(
            analytics_data=analytics_result.value,
        )

    def render_principles_list_fragment(entities: list[Any]) -> Any:
        """Render principle list fragment for HTMX updates."""
        items = [
            PrinciplesViewComponents._render_principle_item(principle) for principle in entities
        ]
        return Div(
            *items if items else [EmptyState(title="No principles found")],
            id="principle-list",
            cls="space-y-3",
        )

    DashboardUIFactory.register_routes(
        rt,
        DashboardUIConfig(
            domain_name="principles",
            title="Principles",
            subtitle="Define the values that guide you",
            default_view="list",
            views=("list", "create", "analytics"),
            parse_filters=parse_principle_filters,
            fetch_filtered_context=fetch_principles_context,
            render_view_tabs=PrinciplesViewComponents.render_view_tabs,
            render_list_view=PrinciplesViewComponents.render_list_view,
            render_create_view=render_principles_create,
            render_third_view=render_principles_analytics,
            build_page_context=build_principles_page_context,
            render_list_fragment=render_principles_list_fragment,
            create_page=create_principles_page,
        ),
    )

    # ========================================================================
    # QUICK ADD (must be BEFORE {uid} routes to avoid path parameter conflict)
    # ========================================================================

    async def create_principle_from_form(
        form_data: dict[str, Any], user_uid: UserUID
    ) -> Result[Any]:
        """Domain-specific principle creation logic."""
        params = parse_principle_create_params(form_data)
        return cast(
            "Result[Any]",
            await principles_service.core.create_principle(
                user_uid=user_uid,
                **params,
            ),
        )

    async def render_principle_success_view(user_uid: UserUID) -> Any:
        """Render list view after successful principle creation."""
        filtered_result = await principles_service.get_filtered_context(user_uid)

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load principles")

        ctx = filtered_result.value
        page_ctx = PrinciplesPageContext(
            entities=ctx["entities"],
            filters={"category": "all", "strength": "all", "sort_by": "strength"},
            stats=ctx["stats"],
            categories=ctx.get("metadata", {}).get("categories", []),
        )
        return PrinciplesViewComponents.render_list_view(ctx=page_ctx)

    async def render_principle_add_another_view(user_uid: UserUID) -> Any:
        """Render create view for add-another flow."""
        return PrinciplesViewComponents.render_create_view(
            categories=_get_principle_categories(),
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
        user_uid = require_authenticated_user(request)

        # Fetch principle with ownership verification
        result = await principles_service.get_for_user(uid, user_uid)

        if result.is_error or result.value is None:
            logger.error(
                f"Failed to get principle {uid}: {result.error if result.is_error else 'Not found'}"
            )
            return await render_entity_not_found_page("Principle", uid, "principles", request)

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
        from core.utils.type_converters import normalize_enum_str

        category_str = normalize_enum_str(category, "personal")

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
            reflection_cards = [EmptyState(title="No reflections recorded yet")]

        reflection_section = Card(
            Div(
                H3("Recent Reflections", cls="text-lg font-semibold"),
                Button(
                    "View All",
                    variant=ButtonT.outline,
                    size=Size.xs,
                    **{
                        "hx-get": f"/principles/{uid}/reflections",
                        "hx-target": "#view-content",
                    },
                ),
                cls="flex items-center justify-between mb-4",
            ),
            Div(*reflection_cards, cls="space-y-3"),
            cls="bg-background shadow-lg p-6 mt-4",
        )

        # Build detail content inline
        # Wrap in view-content so HTMX fragment swaps (reflections, history) have a target
        content = Div(
            # Main card
            Card(
                H1(name, cls="text-2xl font-bold mb-2"),
                Badge(strength_str.title(), variant=BadgeT.primary, cls="mr-2"),
                Badge(category_str.title(), variant=BadgeT.outline),
                Badge("Inactive", variant=BadgeT.ghost, cls="ml-2") if not is_active else "",
                # Statement
                P(statement, cls="text-lg text-muted-foreground mt-4 italic") if statement else "",
                # Description
                (
                    Div(
                        H3("Description", cls="font-semibold mt-6 mb-2"),
                        P(description or "No description provided.", cls="text-muted-foreground"),
                    )
                    if description
                    else ""
                ),
                # Why Important
                (
                    Div(
                        H3("Why This Matters", cls="font-semibold mt-6 mb-2"),
                        P(why_important or "Not specified.", cls="text-muted-foreground"),
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

        principle, error = await require_owned_entity(
            principles_service and principles_service.core, uid, user_uid, "Principle"
        )
        if error:
            return error

        return PrinciplesViewComponents.render_edit_form(principle, _get_principle_categories())

    @rt("/principles/{uid}/save", methods=["POST"])
    async def save_principle(request, uid: str) -> Any:
        """Save principle edits."""
        user_uid = require_authenticated_user(request)

        _, error = await require_owned_entity(
            principles_service and principles_service.core, uid, user_uid, "Principle"
        )
        if error:
            return error

        form = await request.form()
        updates = parse_principle_update_payload(form)

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
        filtered_result = await principles_service.get_filtered_context(user_uid)

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load principles")

        ctx = filtered_result.value
        page_ctx = PrinciplesPageContext(
            entities=ctx["entities"],
            filters={"category": "all", "strength": "all", "sort_by": "strength"},
            stats=ctx["stats"],
            categories=ctx.get("metadata", {}).get("categories", []),
        )
        return PrinciplesViewComponents.render_list_view(ctx=page_ctx)

    @rt("/principles/{uid}/reflect")
    async def reflect_principle_form(request, uid: str) -> Any:
        """Return reflection form for a principle (modal)."""
        user_uid = require_authenticated_user(request)

        principle, error = await require_owned_entity(
            principles_service and principles_service.core, uid, user_uid, "Principle"
        )
        if error:
            return error

        return PrinciplesViewComponents.render_reflect_form(principle)

    @rt("/principles/{uid}/reflections")
    async def get_principle_reflections(request, uid: str) -> Any:
        """Get reflection history for a principle."""
        user_uid = require_authenticated_user(request)

        principle, error = await require_owned_entity(
            principles_service and principles_service.core, uid, user_uid, "Principle"
        )
        if error:
            return error

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
            principle=principle,
            reflections=reflections,
        )

    @rt("/principles/{uid}/alignment-trend")
    async def get_alignment_trend(request, uid: str) -> Any:
        """Get alignment trend data for a principle."""
        user_uid = require_authenticated_user(request)

        if not principles_service:
            return Response("Service unavailable", status_code=503)

        days = parse_int_query_param(request.query_params, "days", 30, minimum=1, maximum=365)

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
        user_uid = require_authenticated_user(request)

        if not principles_service:
            return Response("Service unavailable", status_code=503)

        form = await request.form()
        params = parse_reflection_params(form)

        # Save reflection via service
        result = await principles_service.reflection.save_reflection(
            principle_uid=uid,
            user_uid=user_uid,
            **params,
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
        filtered_result = await principles_service.get_filtered_context(user_uid)

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load principles")

        ctx = filtered_result.value
        page_ctx = PrinciplesPageContext(
            entities=ctx["entities"],
            filters={"category": "all", "strength": "all", "sort_by": "strength"},
            stats=ctx["stats"],
            categories=ctx.get("metadata", {}).get("categories", []),
        )
        return PrinciplesViewComponents.render_list_view(ctx=page_ctx)

    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_principles_ui_routes"]
