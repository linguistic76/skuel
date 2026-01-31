"""
Choices UI Routes - Three-View Standalone Interface
===================================================

Three-view choice management UI with List, Create, and Analytics views.
Analytics as third tab (not Calendar - choices are not time-based).

Routes:
- GET /choices - Main dashboard with three views (standalone, no drawer)
- GET /choices/view/list - HTMX fragment for list view (default)
- GET /choices/view/create - HTMX fragment for create view
- GET /choices/view/analytics - HTMX fragment for analytics view
- GET /choices/list-fragment - HTMX filtered list (for filter updates)
- POST /choices/quick-add - Create choice via form
"""

__version__ = "2.0"

import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from fasthtml.common import H1, H2, H3, A, Form, P
from starlette.responses import Response

from components.choices_views import ChoicesViewComponents
from components.error_components import ErrorComponents
from core.auth import require_authenticated_user
from core.infrastructure.routes import QuickAddConfig, QuickAddRouteFactory
from ui.patterns.relationships import EntityRelationshipsSection
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from core.services.protocols.facade_protocols import ChoicesFacadeProtocol
from core.services.protocols.query_types import ActivityFilterSpec
from core.ui.daisy_components import (
    Button,
    ButtonT,
    Card,
    Div,
    Input,
    Label,
    Option,
    Select,
    Span,
    Textarea,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import (
    get_created_at_attr,
    get_decision_deadline,
    make_priority_string_getter,
)
from ui.choices.layout import create_choices_page

logger = get_logger("skuel.routes.choice.ui")


# ============================================================================
# TYPE PROTOCOLS
# ============================================================================


class RouteDecorator(Protocol):
    """Protocol for FastHTML route decorator."""

    def __call__(self, path: str, methods: list[str] | None = None) -> Any: ...


class Request(Protocol):
    """Protocol for Starlette Request (lightweight type hint)."""

    query_params: dict[str, str]

    async def form(self) -> dict[str, Any]: ...


# ============================================================================
# UI ROUTES
# ============================================================================


def create_choice_ui_routes(_app, rt, choices_service: ChoicesFacadeProtocol):
    """
    Create three-view choice UI routes (standalone, analytics as third tab).

    Views:
    - List: Sortable, filterable choice list (DEFAULT)
    - Create: Choice creation form
    - Analytics: Decision quality and pattern analysis

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        choices_service: Choices service
    """

    logger.info("Registering three-view choice routes (standalone, analytics)")

    # ========================================================================
    # QUERY PARAM TYPES
    # ========================================================================

    @dataclass
    class Filters:
        """Typed filters for choice list queries."""

        status: str
        sort_by: str

    # ========================================================================
    # HELPER FUNCTIONS
    # ========================================================================

    def parse_filters(request) -> Filters:
        """Extract filter parameters from request query params."""
        return Filters(
            status=request.query_params.get("filter_status", "pending"),
            sort_by=request.query_params.get("sort_by", "deadline"),
        )

    # Error rendering moved to components.error_components.ErrorComponents

    # ========================================================================
    # ERROR HANDLING
    # ========================================================================

    def render_safe_error_response(
        user_message: str,
        error_context: Any,
        logger_instance,
        log_extra: dict[str, Any],
        status_code: int = 500,
    ) -> Response:
        """
        Return sanitized error to client, log detailed error server-side.

        Args:
            user_message: Safe message for client (e.g., "Failed to update choice")
            error_context: Detailed error (logged but NOT sent to client)
            logger_instance: Logger instance for structured logging
            log_extra: Additional context for logs (user_uid, entity_uid, etc.)
            status_code: HTTP status code

        Returns:
            Response with sanitized message
        """
        # Log detailed error server-side
        logger_instance.error(
            user_message,
            extra={
                {
                    **log_extra,
                    "error_type": type(error_context).__name__,
                    "error_detail": str(error_context),
                }
            },
        )

        # Return safe message to client
        return Response(user_message, status_code=status_code)

    # ========================================================================
    # DATA FETCHING HELPERS
    # ========================================================================

    async def get_all_choices(user_uid: str) -> Result[list[Any]]:
        """Get all choices for user."""
        try:
            if choices_service:
                result = await choices_service.get_user_choices(user_uid)
                if result.is_error:
                    logger.warning(f"Failed to fetch choices: {result.error}")
                    return result  # Propagate the error
                return Result.ok(result.value or [])
            return Result.ok([])
        except Exception as e:
            logger.error(
                "Error fetching all choices",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to fetch choices: {e}"))

    def _get_enum_value(obj, attr: str, default: str = "") -> str:
        """Extract value from attribute (handles both enum and string)."""
        value = getattr(obj, attr, None)
        if value is None:
            return default
        # Handle enum with .value attribute
        if hasattr(value, "value"):
            return str(value.value).lower()
        return str(value).lower()

    def _parse_options_from_form(form) -> list[dict[str, str]]:
        """Parse options[0].title, options[0].description, etc. from form."""
        options = []
        index = 0
        while True:
            title_key = f"options[{index}].title"
            desc_key = f"options[{index}].description"
            # Check if this index exists in form
            if title_key not in form:
                break
            title = form.get(title_key, "").strip()
            desc = form.get(desc_key, "").strip()
            if title and desc:
                options.append({"title": title, "description": desc})
            index += 1
        return options

    # ========================================================================
    # PURE COMPUTATION HELPERS (Testable without mocks)
    # ========================================================================

    def validate_choice_form_data(form_data: dict[str, Any]) -> Result[None]:
        """
        Validate choice form data early.

        Pure function: returns clear error messages for UI.

        Args:
            form_data: Raw form data from request

        Returns:
            Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
        """
        # Required fields
        title = form_data.get("title", "").strip()
        if not title:
            return Result.fail(Errors.validation("Choice title is required"))

        if len(title) > 200:
            return Result.fail(Errors.validation("Choice title must be 200 characters or less"))

        return Result.ok(None)

    def compute_choice_stats(choices: list[Any]) -> dict[str, int]:
        """
        Calculate choice statistics.

        Pure function: testable without database or async.

        Args:
            choices: List of choice entities

        Returns:
            Stats dict with total, pending, decided counts
        """
        return {
            "total": len(choices),
            "pending": sum(1 for c in choices if _get_enum_value(c, "status") == "pending"),
            "decided": sum(1 for c in choices if _get_enum_value(c, "status") == "decided"),
        }

    def apply_choice_filters(
        choices: list[Any],
        status_filter: str = "pending",
    ) -> list[Any]:
        """
        Apply filter criteria to choice list.

        Pure function: testable without database or async.

        Args:
            choices: List of choice entities
            status_filter: Status filter (pending, decided, implemented, all)

        Returns:
            Filtered list of choices
        """
        # Filter: status
        if status_filter == "pending":
            return [c for c in choices if _get_enum_value(c, "status") == "pending"]
        elif status_filter == "decided":
            return [c for c in choices if _get_enum_value(c, "status") == "decided"]
        elif status_filter == "implemented":
            return [c for c in choices if _get_enum_value(c, "status") == "implemented"]
        # "all" shows everything
        return choices

    def apply_choice_sort(choices: list[Any], sort_by: str = "deadline") -> list[Any]:
        """
        Sort choices by specified field.

        Pure function: testable without database or async.

        Args:
            choices: List of choice entities
            sort_by: Sort field (deadline, priority, created_at)

        Returns:
            Sorted list of choices
        """
        if sort_by == "deadline":
            return sorted(choices, key=get_decision_deadline)
        elif sort_by == "priority":
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

            def get_choice_priority(c: Any) -> str:
                return _get_enum_value(c, "priority", "medium")

            sort_key = make_priority_string_getter(priority_order, get_choice_priority)
            return sorted(choices, key=sort_key)
        elif sort_by == "created_at":
            return sorted(choices, key=get_created_at_attr, reverse=True)
        else:
            # Default: deadline
            return sorted(choices, key=get_decision_deadline)

    async def get_filtered_choices(
        user_uid: str,
        status_filter: str = "pending",
        sort_by: str = "deadline",
    ) -> Result[tuple[list[Any], dict[str, int]]]:
        """
        Get filtered and sorted choices for user.

        Orchestrates: fetch (I/O) → stats → filter → sort.
        Pure computation delegated to testable helper functions.
        """
        try:
            # I/O: Fetch all choices
            choices_result = await get_all_choices(user_uid)
            if choices_result.is_error:
                return Result.fail(choices_result.expect_error())

            choices = choices_result.value

            # Computation: Calculate stats BEFORE filtering
            stats = compute_choice_stats(choices)

            # Computation: Apply filters
            filtered_choices = apply_choice_filters(choices, status_filter)

            # Computation: Apply sort
            sorted_choices = apply_choice_sort(filtered_choices, sort_by)

            return Result.ok((sorted_choices, stats))

        except Exception as e:
            logger.error(
                "Error filtering choices",
                extra={
                    "user_uid": user_uid,
                    "status_filter": status_filter,
                    "sort_by": sort_by,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to filter choices: {e}"))

    async def get_choice_types() -> Result[list[str]]:
        """Get available choice types."""
        return Result.ok(["binary", "multiple", "ranking", "strategic", "operational"])

    async def get_domains() -> Result[list[str]]:
        """Get available domains."""
        # Must match Domain enum values in core/models/enums/entity_enums.py
        return Result.ok(["personal", "business", "health", "finance", "social"])

    async def get_analytics_data(user_uid: str) -> Result[dict[str, Any]]:
        """Get analytics data for user."""
        try:
            choices_result = await get_all_choices(user_uid)

            # Check for errors
            if choices_result.is_error:
                logger.warning(f"Failed to fetch choices for analytics: {choices_result.error}")
                return Result.fail(choices_result.expect_error())  # Propagate the error

            choices = choices_result.value

            # Calculate analytics
            total = len(choices)
            decided_statuses = ["decided", "implemented", "evaluated"]
            decided = sum(1 for c in choices if _get_enum_value(c, "status") in decided_statuses)

            # Calculate satisfaction rate from choices with satisfaction_score (1-5 scale)
            choices_with_satisfaction = [
                c for c in choices if getattr(c, "satisfaction_score", None) is not None
            ]
            if choices_with_satisfaction:
                satisfied_count = sum(
                    1
                    for c in choices_with_satisfaction
                    if getattr(c, "satisfaction_score", 0) >= 4  # 4-5 = satisfied
                )
                satisfaction_rate = satisfied_count / len(choices_with_satisfaction)
            else:
                satisfaction_rate = 0.0

            # Calculate on-time rate from choices with deadline and decided_at
            choices_with_deadline = [
                c
                for c in choices
                if getattr(c, "decision_deadline", None) is not None
                and getattr(c, "decided_at", None) is not None
            ]
            if choices_with_deadline:
                on_time_count = sum(
                    1 for c in choices_with_deadline if c.decided_at <= c.decision_deadline
                )
                on_time_rate = on_time_count / len(choices_with_deadline)
            else:
                on_time_rate = 0.0

            # Get outcomes from evaluated choices
            outcomes = [
                {
                    "title": getattr(c, "title", "Choice"),
                    "outcome": getattr(c, "actual_outcome", ""),
                    "satisfaction": getattr(c, "satisfaction_score", None),
                    "lessons": getattr(c, "lessons_learned", ()),
                }
                for c in choices
                if getattr(c, "actual_outcome", None) is not None
            ]

            return Result.ok(
                {
                    "total_choices": total,
                    "total_decisions": decided,
                    "satisfaction_rate": satisfaction_rate,
                    "on_time_rate": on_time_rate,
                    "outcomes": outcomes,
                }
            )
        except Exception as e:
            logger.error(
                "Error getting analytics",
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

    @rt("/choices")
    async def choices_dashboard(request) -> Any:
        """Main choices dashboard with three views (standalone, no drawer)."""
        user_uid = require_authenticated_user(request)

        # Get view parameter (default to list for choices)
        view = request.query_params.get("view", "list")

        # Parse using helpers
        filters = parse_filters(request)

        # Get data with Result[T]
        filtered_result = await get_filtered_choices(user_uid, filters.status, filters.sort_by)
        choice_types_result = await get_choice_types()
        domains_result = await get_domains()

        # CHECK FOR ERRORS
        if filtered_result.is_error:
            error_content = Div(
                ChoicesViewComponents.render_view_tabs(active_view=view),
                ErrorComponents.render_error_banner("Failed to load choices"),
                cls="p-4 lg:p-8 max-w-7xl mx-auto",
            )
            return create_choices_page(error_content, request=request)

        if choice_types_result.is_error:
            error_content = Div(
                ChoicesViewComponents.render_view_tabs(active_view=view),
                ErrorComponents.render_error_banner("Failed to load choice types"),
                cls="p-4 lg:p-8 max-w-7xl mx-auto",
            )
            return create_choices_page(error_content, request=request)

        if domains_result.is_error:
            error_content = Div(
                ChoicesViewComponents.render_view_tabs(active_view=view),
                ErrorComponents.render_error_banner("Failed to load domains"),
                cls="p-4 lg:p-8 max-w-7xl mx-auto",
            )
            return create_choices_page(error_content, request=request)

        # Extract values
        choices, stats = filtered_result.value
        choice_types = choice_types_result.value
        domains = domains_result.value

        # Render the appropriate view content
        if view == "create":
            view_content = ChoicesViewComponents.render_create_view(
                choice_types=choice_types,
                domains=domains,
                user_uid=user_uid,
            )
        elif view == "analytics":
            analytics_result = await get_analytics_data(user_uid)

            # Check for errors
            if analytics_result.is_error:
                view_content = ErrorComponents.render_error_banner(
                    f"Failed to load analytics: {analytics_result.error}"
                )
            else:
                view_content = ChoicesViewComponents.render_analytics_view(
                    analytics_data=analytics_result.value,
                    user_uid=user_uid,
                )
        else:  # list (default for choices)
            view_content = ChoicesViewComponents.render_list_view(
                choices=choices,
                filters={
                    "status": filters.status,
                    "sort_by": filters.sort_by,
                },
                stats=stats,
                user_uid=user_uid,
            )

        # Build page with tabs + view content
        page_content = Div(
            ChoicesViewComponents.render_view_tabs(active_view=view),
            Div(view_content, id="view-content"),
            cls="p-4 lg:p-8 max-w-7xl mx-auto",
        )

        return create_choices_page(page_content, request=request)

    # ========================================================================
    # HTMX VIEW FRAGMENTS
    # ========================================================================

    @rt("/choices/view/list")
    async def choices_view_list(request) -> Any:
        """HTMX fragment for list view (default for choices)."""
        user_uid = require_authenticated_user(request)
        filters = parse_filters(request)

        filtered_result = await get_filtered_choices(user_uid, filters.status, filters.sort_by)

        # Handle errors
        if filtered_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load choices")

        choices, stats = filtered_result.value

        filters_dict: ActivityFilterSpec = {"status": filters.status, "sort_by": filters.sort_by}
        return ChoicesViewComponents.render_list_view(
            choices=choices,
            filters=filters_dict,
            stats=stats,
            user_uid=user_uid,
        )

    @rt("/choices/view/create")
    async def choices_view_create(request) -> Any:
        """HTMX fragment for create view."""
        user_uid = require_authenticated_user(request)
        choice_types_result = await get_choice_types()
        domains_result = await get_domains()

        # Handle errors
        if choice_types_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load choice types")

        if domains_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load domains")

        return ChoicesViewComponents.render_create_view(
            choice_types=choice_types_result.value,
            domains=domains_result.value,
            user_uid=user_uid,
        )

    @rt("/choices/view/analytics")
    async def choices_view_analytics(request) -> Any:
        """HTMX fragment for analytics view."""
        user_uid = require_authenticated_user(request)
        analytics_result = await get_analytics_data(user_uid)

        # Handle errors
        if analytics_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load analytics")

        return ChoicesViewComponents.render_analytics_view(
            analytics_data=analytics_result.value,
            user_uid=user_uid,
        )

    # ========================================================================
    # LIST FRAGMENT (for filter updates)
    # ========================================================================

    @rt("/choices/list-fragment")
    async def choices_list_fragment(request) -> Any:
        """Return filtered choice list for HTMX updates."""
        user_uid = require_authenticated_user(request)
        filters = parse_filters(request)

        filtered_result = await get_filtered_choices(user_uid, filters.status, filters.sort_by)

        # Handle errors
        if filtered_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load choices")

        choices, _stats = filtered_result.value

        # Return just the choice items
        choice_items = [
            ChoicesViewComponents._render_choice_item(choice, user_uid) for choice in choices
        ]

        return Div(
            *choice_items
            if choice_items
            else [P("No decisions found.", cls="text-gray-500 text-center py-8")],
            id="choice-list",
            cls="space-y-3",
        )

    # ========================================================================
    # QUICK ADD (via QuickAddRouteFactory)
    # ========================================================================

    def validate_choice_options(form_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate that at least 2 options are provided."""
        options = _parse_options_from_form(form_data)
        if len(options) < 2:
            return (False, "At least 2 options are required")
        return (True, "")

    async def create_choice_from_form(form_data: dict[str, Any], user_uid: str) -> Result[Any]:
        """
        Domain-specific choice creation logic.

        Handles form parsing, option parsing, enum conversion, and service call.
        """
        from core.models.choice.choice import ChoiceType
        from core.models.choice.choice_request import (
            ChoiceCreateRequest,
            ChoiceOptionCreateRequest,
        )
        from core.models.shared_enums import Domain as DomainEnum
        from core.models.shared_enums import Priority as PriorityEnum

        # VALIDATE EARLY
        validation_result = validate_choice_form_data(form_data)
        if validation_result.is_error:
            return validation_result  # Return validation error to UI

        # Extract form data
        title = form_data.get("title", "").strip()
        description = form_data.get("description", "").strip() or None
        choice_type = form_data.get("choice_type", "binary")
        domain = form_data.get("domain", "personal")
        priority = form_data.get("priority", "medium")
        deadline_str = form_data.get("decision_deadline", "")

        # Parse options from form
        options = _parse_options_from_form(form_data)

        # Parse deadline
        decision_deadline = None
        if deadline_str:
            with contextlib.suppress(ValueError):
                decision_deadline = datetime.fromisoformat(deadline_str)

        # Map string values to enums
        choice_type_enum = ChoiceType(choice_type) if choice_type else ChoiceType.MULTIPLE
        domain_enum = DomainEnum(domain) if domain else DomainEnum.PERSONAL
        priority_enum = PriorityEnum(priority) if priority else PriorityEnum.MEDIUM

        # Convert options to ChoiceOptionCreateRequest objects
        option_requests = [
            ChoiceOptionCreateRequest(title=opt["title"], description=opt["description"])
            for opt in options
        ]

        # Build request and call service
        choice_request = ChoiceCreateRequest(
            title=title,
            description=description or title,
            choice_type=choice_type_enum,
            domain=domain_enum,
            priority=priority_enum,
            decision_deadline=decision_deadline,
            options=option_requests,
        )

        return await choices_service.core.create_choice(choice_request, user_uid)

    async def render_choice_success_view(user_uid: str) -> Any:
        """Render list view after successful choice creation."""
        result = await get_filtered_choices(user_uid, "pending", "deadline")
        if result.is_error:
            return ErrorComponents.render_error_banner("Failed to load choices")
        choices, stats = result.value
        filters: ActivityFilterSpec = {"status": "pending", "sort_by": "deadline"}
        return ChoicesViewComponents.render_list_view(
            choices=choices,
            filters=filters,
            stats=stats,
            user_uid=user_uid,
        )

    async def render_choice_add_another_view(user_uid: str) -> Any:
        """Render create view for add-another flow."""
        choice_types = await get_choice_types()
        domains = await get_domains()
        return ChoicesViewComponents.render_create_view(
            choice_types=choice_types,
            domains=domains,
            user_uid=user_uid,
        )

    # Register quick-add route via factory
    choices_quick_add_config = QuickAddConfig(
        domain_name="choices",
        required_field="title",
        create_entity=create_choice_from_form,
        render_success_view=render_choice_success_view,
        render_add_another_view=render_choice_add_another_view,
        extra_validators=[validate_choice_options],
    )
    QuickAddRouteFactory.register_route(rt, choices_quick_add_config)

    # ========================================================================
    # VIEW DETAIL
    # ========================================================================

    @rt("/choices/{uid}")
    async def view_choice(request, uid: str) -> Any:
        """View choice detail page."""
        user_uid = require_authenticated_user(request)

        if not choices_service:
            return Response("Service unavailable", status_code=503)

        # Ownership verification - returns NotFound if user doesn't own this choice
        result = await choices_service.core.verify_ownership(uid, user_uid)
        if result.is_error:
            logger.warning(f"Choice access denied or not found: {uid} for user {user_uid}")
            return Response("Choice not found", status_code=404)

        choice = result.value

        # Get options if any
        options = getattr(choice, "options", []) or []

        # Status and priority display
        status = _get_enum_value(choice, "status", "pending")
        priority = _get_enum_value(choice, "priority", "medium")

        status_colors = {
            "pending": "badge-warning",
            "decided": "badge-success",
            "implemented": "badge-info",
            "evaluated": "badge-primary",
        }

        detail_content = Div(
            # Header
            Div(
                A(
                    "← Back to List",
                    href="/choices",
                    cls="text-sm text-blue-600 hover:underline mb-4 inline-block",
                ),
                Div(
                    H2(choice.title, cls="text-2xl font-bold"),
                    Span(
                        status.title(), cls=f"badge {status_colors.get(status, 'badge-ghost')} ml-2"
                    ),
                    cls="flex items-center",
                ),
                cls="mb-6",
            ),
            # Description
            Div(
                H3("Description", cls="text-lg font-semibold mb-2"),
                P(choice.description or "No description", cls="text-gray-600"),
                cls="mb-6",
            ),
            # Meta info
            Div(
                Div(
                    Span("Priority: ", cls="text-gray-500"),
                    Span(priority.title(), cls="font-semibold"),
                    cls="mr-6",
                ),
                Div(
                    Span("Domain: ", cls="text-gray-500"),
                    Span(
                        _get_enum_value(choice, "domain", "personal").title(), cls="font-semibold"
                    ),
                    cls="mr-6",
                ),
                Div(
                    Span("Type: ", cls="text-gray-500"),
                    Span(
                        _get_enum_value(choice, "choice_type", "multiple").title(),
                        cls="font-semibold",
                    ),
                ),
                cls="flex flex-wrap mb-6",
            ),
            # Options section
            Div(
                H3(f"Options ({len(options)})", cls="text-lg font-semibold mb-4"),
                Div(
                    *[
                        Div(
                            Span(
                                opt.title
                                if hasattr(opt, "title")
                                else opt.get("title", "Untitled"),
                                cls="font-medium",
                            ),
                            P(
                                opt.description
                                if hasattr(opt, "description")
                                else opt.get("description", ""),
                                cls="text-sm text-gray-500",
                            ),
                            cls="p-3 bg-base-200 rounded-lg mb-2",
                        )
                        for opt in options
                    ]
                    if options
                    else [
                        P(
                            "No options defined yet. Add options to make a decision.",
                            cls="text-gray-500",
                        )
                    ],
                ),
                cls="mb-6",
            )
            if status == "pending"
            else "",
            # Actions
            Div(
                Button(
                    "Edit",
                    variant=ButtonT.outline,
                    cls="mr-2",
                    **{"hx-get": f"/choices/{uid}/edit", "hx-target": "#modal"},
                ),
                Button(
                    "Add Option",
                    variant=ButtonT.secondary,
                    cls="mr-2",
                    **{"hx-get": f"/choices/{uid}/add-option", "hx-target": "#modal"},
                )
                if status == "pending"
                else "",
                Button(
                    "Make Decision",
                    variant=ButtonT.success,
                    **{"hx-get": f"/choices/{uid}/decide", "hx-target": "#modal"},
                )
                if status == "pending" and len(options) >= 2
                else "",
                cls="flex",
            ),
            # Modal container
            Div(id="modal"),
            cls="card bg-base-100 shadow-lg p-6",
        )

        page_content = Div(detail_content, cls="p-4 lg:p-8 max-w-4xl mx-auto")
        return create_choices_page(page_content, request=request)

    # ========================================================================
    # DECIDE MODAL
    # ========================================================================

    @rt("/choices/{uid}/decide")
    async def decide_choice_modal(request, uid: str) -> Any:
        """Show modal to make a decision on a choice."""
        user_uid = require_authenticated_user(request)

        if not choices_service:
            return Response("Service unavailable", status_code=503)

        # Ownership verification - returns NotFound if user doesn't own this choice
        result = await choices_service.core.verify_ownership(uid, user_uid)
        if result.is_error:
            return Response("Choice not found", status_code=404)

        choice = result.value
        options = getattr(choice, "options", []) or []

        if len(options) < 2:
            return Div(
                Div(
                    P("You need at least 2 options to make a decision.", cls="text-gray-600 mb-4"),
                    Button(
                        "Add Options",
                        variant=ButtonT.primary,
                        **{"hx-get": f"/choices/{uid}/add-option", "hx-target": "#modal"},
                    ),
                    Button(
                        "Close",
                        variant=ButtonT.ghost,
                        cls="ml-2",
                        **{"onclick": "this.closest('.modal').remove()"},
                    ),
                    cls="modal-box",
                ),
                cls="modal modal-open",
            )

        # Build option selection
        option_buttons = []
        for opt in options:
            opt_uid = opt.uid if hasattr(opt, "uid") else opt.get("uid", "")
            opt_title = opt.title if hasattr(opt, "title") else opt.get("title", "Untitled")
            opt_desc = (
                opt.description if hasattr(opt, "description") else opt.get("description", "")
            )
            option_buttons.append(
                Div(
                    Input(
                        type="radio",
                        name="selected_option_uid",
                        value=opt_uid,
                        cls="radio radio-primary",
                        required=True,
                    ),
                    Div(
                        Span(opt_title, cls="font-medium"),
                        P(
                            opt_desc[:100] + "..."
                            if opt_desc and len(opt_desc) > 100
                            else opt_desc,
                            cls="text-sm text-gray-500",
                        ),
                        cls="ml-3",
                    ),
                    cls="flex items-start p-3 bg-base-200 rounded-lg mb-2 cursor-pointer hover:bg-base-300",
                )
            )

        return Div(
            Div(
                H3(f"Decide: {choice.title}", cls="text-lg font-bold mb-4"),
                Form(
                    P("Select the option you've decided on:", cls="text-gray-600 mb-4"),
                    Div(*option_buttons, cls="mb-4"),
                    Div(
                        Label("Rationale (optional)", cls="label"),
                        Textarea(
                            name="decision_rationale",
                            placeholder="Why did you choose this option?",
                            rows="3",
                            cls="textarea textarea-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    Div(
                        Button("Confirm Decision", type="submit", variant=ButtonT.success),
                        Button(
                            "Cancel",
                            type="button",
                            variant=ButtonT.ghost,
                            cls="ml-2",
                            **{"onclick": "this.closest('.modal').remove()"},
                        ),
                    ),
                    **{
                        "hx-post": f"/choices/{uid}/decide",
                        "hx-target": "body",
                    },
                ),
                cls="modal-box",
            ),
            cls="modal modal-open",
        )

    @rt("/choices/{uid}/decide", methods=["POST"])
    async def submit_decision(request, uid: str) -> Any:
        """Submit the decision for a choice."""
        user_uid = require_authenticated_user(request)

        if not choices_service:
            return Response("Service unavailable", status_code=503)

        # Ownership verification before mutation
        ownership_result = await choices_service.core.verify_ownership(uid, user_uid)
        if ownership_result.is_error:
            return Response("Choice not found", status_code=404)

        form = await request.form()
        selected_option_uid = form.get("selected_option_uid")
        decision_rationale = form.get("decision_rationale", "").strip() or None

        if not selected_option_uid:
            return Response("Please select an option", status_code=400)

        result = await choices_service.core.make_decision(
            choice_uid=uid,
            selected_option_uid=selected_option_uid,
            decision_rationale=decision_rationale,
        )

        if result.is_error:
            return render_safe_error_response(
                user_message="Failed to save decision",
                error_context=result.error,
                logger_instance=logger,
                log_extra={"choice_uid": uid, "user_uid": user_uid},
                status_code=500,
            )

        # Redirect to choice detail
        return Response(headers={"HX-Redirect": f"/choices/{uid}"})

    # ========================================================================
    # EDIT MODAL
    # ========================================================================

    @rt("/choices/{uid}/edit")
    async def edit_choice_modal(request, uid: str) -> Any:
        """Show modal to edit a choice."""
        user_uid = require_authenticated_user(request)

        if not choices_service:
            return Response("Service unavailable", status_code=503)

        # Ownership verification - returns NotFound if user doesn't own this choice
        result = await choices_service.core.verify_ownership(uid, user_uid)
        if result.is_error:
            return Response("Choice not found", status_code=404)

        choice = result.value
        # Must match Domain enum values in core/models/enums/entity_enums.py
        domains = ["personal", "business", "health", "finance", "social"]
        priorities = ["critical", "high", "medium", "low"]

        return Div(
            Div(
                H3("Edit Decision", cls="text-lg font-bold mb-4"),
                Form(
                    # Title
                    Div(
                        Label("Title", cls="label"),
                        Input(
                            type="text",
                            name="title",
                            value=choice.title,
                            cls="input input-bordered w-full",
                            required=True,
                        ),
                        cls="mb-4",
                    ),
                    # Description
                    Div(
                        Label("Description", cls="label"),
                        Textarea(
                            choice.description or "",
                            name="description",
                            rows="3",
                            cls="textarea textarea-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Priority
                    Div(
                        Label("Priority", cls="label"),
                        Select(
                            *[
                                Option(
                                    p.title(),
                                    value=p,
                                    selected=_get_enum_value(choice, "priority") == p,
                                )
                                for p in priorities
                            ],
                            name="priority",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Domain
                    Div(
                        Label("Domain", cls="label"),
                        Select(
                            *[
                                Option(
                                    d.title(),
                                    value=d,
                                    selected=_get_enum_value(choice, "domain") == d,
                                )
                                for d in domains
                            ],
                            name="domain",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Buttons
                    Div(
                        Button("Save Changes", type="submit", variant=ButtonT.primary),
                        Button(
                            "Cancel",
                            type="button",
                            variant=ButtonT.ghost,
                            cls="ml-2",
                            **{"onclick": "this.closest('.modal').remove()"},
                        ),
                    ),
                    **{
                        "hx-post": f"/choices/{uid}/edit",
                        "hx-target": "body",
                    },
                ),
                cls="modal-box",
            ),
            cls="modal modal-open",
        )

    @rt("/choices/{uid}/edit", methods=["POST"])
    async def submit_edit(request, uid: str) -> Any:
        """Submit choice edits."""
        user_uid = require_authenticated_user(request)

        if not choices_service:
            return Response("Service unavailable", status_code=503)

        # Ownership verification before mutation
        ownership_result = await choices_service.core.verify_ownership(uid, user_uid)
        if ownership_result.is_error:
            return Response("Choice not found", status_code=404)

        form = await request.form()

        from core.models.choice.choice_request import ChoiceUpdateRequest
        from core.models.shared_enums import Domain as DomainEnum
        from core.models.shared_enums import Priority as PriorityEnum

        title = form.get("title", "").strip()
        description = form.get("description", "").strip() or None
        priority_str = form.get("priority", "medium")
        domain_str = form.get("domain", "personal")

        try:
            update_request = ChoiceUpdateRequest(
                title=title if title else None,
                description=description,
                priority=PriorityEnum(priority_str),
                domain=DomainEnum(domain_str),
            )

            result = await choices_service.update_choice(uid, update_request)

            if result.is_error:
                return render_safe_error_response(
                    user_message="Failed to update choice",
                    error_context=result.error,
                    logger_instance=logger,
                    log_extra={"choice_uid": uid, "user_uid": user_uid},
                    status_code=500,
                )

            # Redirect to choice detail
            return Response(headers={"HX-Redirect": f"/choices/{uid}"})

        except Exception as e:
            logger.error(f"Error updating choice: {e}")
            return Response("Error", status_code=500)

    # ========================================================================
    # ADD OPTION MODAL
    # ========================================================================

    @rt("/choices/{uid}/add-option")
    async def add_option_modal(request, uid: str) -> Any:
        """Show modal to add an option to a choice."""
        user_uid = require_authenticated_user(request)

        if not choices_service:
            return Response("Service unavailable", status_code=503)

        # Ownership verification - returns NotFound if user doesn't own this choice
        ownership_result = await choices_service.core.verify_ownership(uid, user_uid)
        if ownership_result.is_error:
            return Response("Choice not found", status_code=404)

        return Div(
            Div(
                H3("Add Option", cls="text-lg font-bold mb-4"),
                Form(
                    # Title
                    Div(
                        Label("Option Title", cls="label"),
                        Input(
                            type="text",
                            name="title",
                            placeholder="What is this option?",
                            cls="input input-bordered w-full",
                            required=True,
                        ),
                        cls="mb-4",
                    ),
                    # Description
                    Div(
                        Label("Description", cls="label"),
                        Textarea(
                            name="description",
                            placeholder="Describe this option...",
                            rows="3",
                            cls="textarea textarea-bordered w-full",
                            required=True,
                        ),
                        cls="mb-4",
                    ),
                    # Buttons
                    Div(
                        Button("Add Option", type="submit", variant=ButtonT.primary),
                        Button(
                            "Cancel",
                            type="button",
                            variant=ButtonT.ghost,
                            cls="ml-2",
                            **{"onclick": "this.closest('.modal').remove()"},
                        ),
                    ),
                    **{
                        "hx-post": f"/choices/{uid}/add-option",
                        "hx-target": "body",
                    },
                ),
                cls="modal-box",
            ),
            cls="modal modal-open",
        )

    @rt("/choices/{uid}/add-option", methods=["POST"])
    async def submit_add_option(request, uid: str) -> Any:
        """Submit new option for a choice."""
        user_uid = require_authenticated_user(request)

        if not choices_service:
            return Response("Service unavailable", status_code=503)

        # Ownership verification before mutation
        ownership_result = await choices_service.core.verify_ownership(uid, user_uid)
        if ownership_result.is_error:
            return Response("Choice not found", status_code=404)

        form = await request.form()
        title = form.get("title", "").strip()
        description = form.get("description", "").strip()

        if not title or not description:
            return Response("Title and description are required", status_code=400)

        result = await choices_service.add_option(
            choice_uid=uid,
            title=title,
            description=description,
        )

        if result.is_error:
            return render_safe_error_response(
                user_message="Failed to add option",
                error_context=result.error,
                logger_instance=logger,
                log_extra={"choice_uid": uid, "user_uid": user_uid},
                status_code=500,
            )

        # Redirect to choice detail
        return Response(headers={"HX-Redirect": f"/choices/{uid}"})

    # ========================================================================
    # CHOICE DETAIL PAGE (Phase 5)
    # ========================================================================

    @rt("/choices/{uid}")
    async def choice_detail_view(request: Any, uid: str) -> Any:
        """
        Choice detail view with full context and relationships.

        Phase 5: Shows choice details plus lateral relationships visualization.
        """
        user_uid = require_authenticated_user(request)

        # Fetch choice with ownership verification
        result = await choices_service.get_for_user(uid, user_uid)

        if result.is_error:
            logger.error(f"Failed to get choice {uid}: {result.error}")
            return BasePage(
                content=Card(
                    H2("Choice Not Found", cls="text-xl font-bold text-error mb-4"),
                    P(f"Could not find choice: {uid}", cls="text-base-content/70"),
                    Button(
                        "← Back to Choices",
                        **{"hx-get": "/choices", "hx-target": "body"},
                        variant=ButtonT.primary,
                        cls="mt-4",
                    ),
                    cls="p-6",
                ),
                title="Choice Not Found",
                page_type=PageType.STANDARD,
                request=request,
                active_page="choices",
            )

        choice = result.value

        # Render detail page
        content = Div(
            # Header Card
            Card(
                H1(f"🤔 {choice.title}", cls="text-2xl font-bold mb-2"),
                P(choice.description or "No description provided", cls="text-base-content/70 mb-4"),
                # Status and Urgency badges
                Div(
                    Span(f"Status: {choice.status.value}", cls="badge badge-info mr-2"),
                    Span(f"Urgency: {choice.urgency.value if choice.urgency else 'Not set'}", cls="badge badge-warning"),
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-6 mb-4",
            ),
            # Details Card
            Card(
                H2("📋 Choice Details", cls="text-xl font-semibold mb-4"),
                Div(
                    # Decision Deadline
                    (
                        Div(
                            P("Decision Deadline:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                            P(str(choice.decision_deadline) if choice.decision_deadline else "Not set", cls="text-base-content mb-3"),
                            cls="mb-4",
                        )
                        if choice.decision_deadline
                        else Div()
                    ),
                    # Why Important
                    (
                        Div(
                            P("Why Important:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                            P(choice.why_important or "Not specified", cls="text-base-content mb-3"),
                            cls="mb-4",
                        )
                        if choice.why_important
                        else Div()
                    ),
                    # Created Date
                    Div(
                        P("Created:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                        P(str(choice.created_at)[:10], cls="text-base-content/60 text-sm"),
                    ),
                    cls="space-y-2",
                ),
                cls="p-6 mb-4",
            ),
            # Actions Card
            Card(
                Div(
                    Button(
                        "← Back to Choices",
                        **{"hx-get": "/choices", "hx-target": "body"},
                        variant=ButtonT.ghost,
                        cls="mr-2",
                    ),
                    Button(
                        "✏️ Edit Choice",
                        **{"hx-get": f"/choices/{choice.uid}/edit", "hx-target": "#modal"},
                        variant=ButtonT.primary,
                        cls="mr-2",
                    ),
                    Button(
                        "➕ Add Option",
                        **{"hx-get": f"/choices/{choice.uid}/add-option", "hx-target": "#modal"},
                        variant=ButtonT.success,
                    ),
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-4 mb-4",
            ),
            # Phase 5: Lateral Relationships Section
            EntityRelationshipsSection(
                entity_uid=choice.uid,
                entity_type="choices",
            ),
            cls="container mx-auto p-6 max-w-4xl",
        )

        return BasePage(
            content=content,
            title=choice.title,
            page_type=PageType.STANDARD,
            request=request,
            active_page="choices",
        )

    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_choice_ui_routes"]
