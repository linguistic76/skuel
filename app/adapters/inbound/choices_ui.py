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
from typing import Any, cast

from fasthtml.common import H1, H2, H3, Div, Form, Option, P, Span
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.route_factories import (
    QuickAddConfig,
    QuickAddRouteFactory,
    require_owned_entity,
)
from adapters.inbound.ui_helpers import render_safe_error_response
from core.ports.query_types import ActivityFilterSpec
from core.services.choices_service import ChoicesService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.type_converters import get_enum_attr_str
from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.choices.layout import create_choices_page
from ui.choices.views import ChoicesViewComponents
from ui.forms import Input, Label, Select, Textarea
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.error_banner import render_error_banner
from ui.patterns.relationships import EntityRelationshipsSection
from ui.tokens import Container, Spacing

logger = get_logger("skuel.routes.choice.ui")


# RouteDecorator and Request imported from adapters.inbound.fasthtml_types


@dataclass
class Filters:
    """Typed filters for choice list queries."""

    status: str
    sort_by: str


def parse_filters(request) -> Filters:
    """Extract filter parameters from request query params."""
    return Filters(
        status=request.query_params.get("filter_status", "pending"),
        sort_by=request.query_params.get("sort_by", "deadline"),
    )


# ============================================================================
# UI ROUTES
# ============================================================================


def create_choices_ui_routes(_app, rt, choices_service: ChoicesService, services: Any = None):
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
        services: Full services container (unused, kept for API compatibility)
    """

    logger.info("Registering three-view choice routes (standalone, analytics)")

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
            decided = sum(1 for c in choices if get_enum_attr_str(c, "status") in decided_statuses)

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
        filtered_result = await choices_service.get_filtered_context(
            user_uid, filters.status, filters.sort_by
        )
        choice_types_result = await get_choice_types()
        domains_result = await get_domains()

        # CHECK FOR ERRORS
        if filtered_result.is_error:
            error_content = Div(
                ChoicesViewComponents.render_view_tabs(active_view=view),
                render_error_banner("Failed to load choices"),
                cls=f"{Spacing.PAGE} {Container.WIDE}",
            )
            return await create_choices_page(error_content, request=request)

        if choice_types_result.is_error:
            error_content = Div(
                ChoicesViewComponents.render_view_tabs(active_view=view),
                render_error_banner("Failed to load choice types"),
                cls=f"{Spacing.PAGE} {Container.WIDE}",
            )
            return await create_choices_page(error_content, request=request)

        if domains_result.is_error:
            error_content = Div(
                ChoicesViewComponents.render_view_tabs(active_view=view),
                render_error_banner("Failed to load domains"),
                cls=f"{Spacing.PAGE} {Container.WIDE}",
            )
            return await create_choices_page(error_content, request=request)

        # Extract values
        ctx = filtered_result.value
        choices, stats = ctx["entities"], ctx["stats"]
        choice_types = choice_types_result.value
        domains = domains_result.value

        # Render the appropriate view content
        if view == "create":
            view_content = ChoicesViewComponents.render_create_view(
                choice_types=choice_types,
                domains=domains,
            )
        elif view == "analytics":
            analytics_result = await get_analytics_data(user_uid)

            # Check for errors
            if analytics_result.is_error:
                view_content = render_error_banner(
                    f"Failed to load analytics: {analytics_result.error}"
                )
            else:
                view_content = ChoicesViewComponents.render_analytics_view(
                    analytics_data=analytics_result.value,
                )
        else:  # list (default for choices)
            view_content = ChoicesViewComponents.render_list_view(
                choices=choices,
                filters={
                    "status": filters.status,
                    "sort_by": filters.sort_by,
                },
                stats=stats,
            )

        # Build page with tabs + view content
        page_content = Div(
            ChoicesViewComponents.render_view_tabs(active_view=view),
            Div(view_content, id="view-content", role="tabpanel"),
            cls=f"{Spacing.PAGE} {Container.WIDE}",
        )

        return await create_choices_page(page_content, request=request)

    # ========================================================================
    # HTMX VIEW FRAGMENTS
    # ========================================================================

    @rt("/choices/view/list")
    async def choices_view_list(request) -> Any:
        """HTMX fragment for list view (default for choices)."""
        user_uid = require_authenticated_user(request)
        filters = parse_filters(request)

        filtered_result = await choices_service.get_filtered_context(
            user_uid, filters.status, filters.sort_by
        )

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load choices")

        ctx = filtered_result.value
        choices, stats = ctx["entities"], ctx["stats"]

        filters_dict: ActivityFilterSpec = {"status": filters.status, "sort_by": filters.sort_by}
        return ChoicesViewComponents.render_list_view(
            choices=choices,
            filters=filters_dict,
            stats=stats,
        )

    @rt("/choices/view/create")
    async def choices_view_create(request) -> Any:
        """HTMX fragment for create view."""
        require_authenticated_user(request)
        choice_types_result = await get_choice_types()
        domains_result = await get_domains()

        # Handle errors
        if choice_types_result.is_error:
            return render_error_banner("Failed to load choice types")

        if domains_result.is_error:
            return render_error_banner("Failed to load domains")

        return ChoicesViewComponents.render_create_view(
            choice_types=choice_types_result.value,
            domains=domains_result.value,
        )

    @rt("/choices/view/analytics")
    async def choices_view_analytics(request) -> Any:
        """HTMX fragment for analytics view."""
        user_uid = require_authenticated_user(request)
        analytics_result = await get_analytics_data(user_uid)

        # Handle errors
        if analytics_result.is_error:
            return render_error_banner("Failed to load analytics")

        return ChoicesViewComponents.render_analytics_view(
            analytics_data=analytics_result.value,
        )

    # ========================================================================
    # LIST FRAGMENT (for filter updates)
    # ========================================================================

    @rt("/choices/list-fragment")
    async def choices_list_fragment(request) -> Any:
        """Return filtered choice list for HTMX updates."""
        user_uid = require_authenticated_user(request)
        filters = parse_filters(request)

        filtered_result = await choices_service.get_filtered_context(
            user_uid, filters.status, filters.sort_by
        )

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load choices")

        ctx = filtered_result.value
        choices = ctx["entities"]

        # Return just the choice items
        choice_items = [ChoicesViewComponents._render_choice_item(choice) for choice in choices]

        return Div(
            *choice_items
            if choice_items
            else [P("No decisions found.", cls="text-muted-foreground text-center py-8")],
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
        from core.models.choice.choice_request import (
            ChoiceCreateRequest,
            ChoiceOptionCreateRequest,
        )
        from core.models.enums import Domain as DomainEnum
        from core.models.enums import Priority as PriorityEnum
        from core.models.enums.choice_enums import ChoiceType

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

        return cast(
            "Result[Any]", await choices_service.core.create_choice(choice_request, user_uid)
        )

    async def render_choice_success_view(user_uid: str) -> Any:
        """Render list view after successful choice creation."""
        result = await choices_service.get_filtered_context(user_uid)
        if result.is_error:
            return render_error_banner("Failed to load choices")
        ctx = result.value
        choices, stats = ctx["entities"], ctx["stats"]
        filters: ActivityFilterSpec = {"status": "pending", "sort_by": "deadline"}
        return ChoicesViewComponents.render_list_view(
            choices=choices,
            filters=filters,
            stats=stats,
        )

    async def render_choice_add_another_view(user_uid: str) -> Any:
        """Render create view for add-another flow."""
        choice_types = await get_choice_types()
        domains = await get_domains()
        return ChoicesViewComponents.render_create_view(
            choice_types=choice_types,
            domains=domains,
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
    # DECIDE MODAL
    # ========================================================================

    @rt("/choices/{uid}/decide")
    async def decide_choice_modal(request, uid: str) -> Any:
        """Show modal to make a decision on a choice."""
        user_uid = require_authenticated_user(request)

        choice, error = await require_owned_entity(
            choices_service and choices_service.core, uid, user_uid, "Choice"
        )
        if error:
            return error
        assert choice is not None  # guaranteed by require_owned_entity when no error

        options = getattr(choice, "options", []) or []

        if len(options) < 2:
            return Div(
                Div(
                    P(
                        "You need at least 2 options to make a decision.",
                        cls="text-muted-foreground mb-4",
                    ),
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
        from core.models.choice.choice_option import ChoiceOption

        option_buttons = []
        for opt in options:
            if isinstance(opt, ChoiceOption):
                opt_uid = opt.uid
                opt_title = opt.title
                opt_desc = opt.description
            else:
                opt_uid = opt.get("uid", "")
                opt_title = opt.get("title", "Untitled")
                opt_desc = opt.get("description", "")
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
                            cls="text-sm text-muted-foreground",
                        ),
                        cls="ml-3",
                    ),
                    cls="flex items-start p-3 bg-muted rounded-lg mb-2 cursor-pointer hover:bg-secondary",
                )
            )

        return Div(
            Div(
                H3(f"Decide: {choice.title}", cls="text-lg font-bold mb-4"),
                Form(
                    P("Select the option you've decided on:", cls="text-muted-foreground mb-4"),
                    Div(*option_buttons, cls="mb-4"),
                    Div(
                        Label("Rationale (optional)", cls="label"),
                        Textarea(
                            name="decision_rationale",
                            placeholder="Why did you choose this option?",
                            rows="3",
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

        _, error = await require_owned_entity(
            choices_service and choices_service.core, uid, user_uid, "Choice"
        )
        if error:
            return error

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

        choice, error = await require_owned_entity(
            choices_service and choices_service.core, uid, user_uid, "Choice"
        )
        if error:
            return error
        assert choice is not None  # guaranteed by require_owned_entity when no error

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
                                    selected=get_enum_attr_str(choice, "priority") == p,
                                )
                                for p in priorities
                            ],
                            name="priority",
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
                                    selected=get_enum_attr_str(choice, "domain") == d,
                                )
                                for d in domains
                            ],
                            name="domain",
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

        _, error = await require_owned_entity(
            choices_service and choices_service.core, uid, user_uid, "Choice"
        )
        if error:
            return error

        form = await request.form()

        from core.models.entity_requests import EntityUpdateRequest
        from core.models.enums import Domain as DomainEnum
        from core.models.enums import Priority as PriorityEnum

        title = form.get("title", "").strip()
        description = form.get("description", "").strip() or None
        priority_str = form.get("priority", "medium")
        domain_str = form.get("domain", "personal")

        try:
            update_request = EntityUpdateRequest(
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

        _, error = await require_owned_entity(
            choices_service and choices_service.core, uid, user_uid, "Choice"
        )
        if error:
            return error

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

        _, error = await require_owned_entity(
            choices_service and choices_service.core, uid, user_uid, "Choice"
        )
        if error:
            return error

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
    # CHOICE DETAIL PAGE
    # ========================================================================

    @rt("/choices/{uid}")
    async def choice_detail_view(request: Any, uid: str) -> Any:
        """
        Choice detail view with full context and relationships.

        Shows choice details plus lateral relationships visualization.
        """
        user_uid = require_authenticated_user(request)

        # Fetch choice with ownership verification
        result = await choices_service.get_for_user(uid, user_uid)

        if result.is_error or result.value is None:
            logger.error(
                f"Failed to get choice {uid}: {result.error if result.is_error else 'Not found'}"
            )
            return await BasePage(
                content=Card(
                    H2("Choice Not Found", cls="text-xl font-bold text-error mb-4"),
                    P(f"Could not find choice: {uid}", cls="text-muted-foreground"),
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

        # Extract metadata for display
        status = get_enum_attr_str(choice, "status", "pending")
        priority = get_enum_attr_str(choice, "priority", "medium")
        domain = get_enum_attr_str(choice, "domain", "personal")
        choice_type = get_enum_attr_str(choice, "choice_type", "multiple")
        options = getattr(choice, "options", []) or []

        # Render detail page
        content = Div(
            # Header Card
            Card(
                H1(f"🤔 {choice.title}", cls="text-2xl font-bold mb-2"),
                P(choice.description or "No description provided", cls="text-muted-foreground mb-4"),
                # Status and Urgency badges
                Div(
                    Span(f"Status: {choice.status.value}", cls="badge badge-info mr-2"),
                    Span(f"Priority: {priority.title()}", cls="badge badge-ghost mr-2"),
                    Span(f"Domain: {domain.title()}", cls="badge badge-outline mr-2"),
                    Span(f"Type: {choice_type.title()}", cls="badge badge-outline"),
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
                            P(
                                "Decision Deadline:",
                                cls="text-sm font-semibold text-muted-foreground mb-1",
                            ),
                            P(
                                str(getattr(choice, "decision_deadline", None))
                                if getattr(choice, "decision_deadline", None)
                                else "Not set",
                                cls="text-foreground mb-3",
                            ),
                            cls="mb-4",
                        )
                        if getattr(choice, "decision_deadline", None)
                        else Div()
                    ),
                    # Created Date
                    Div(
                        P("Created:", cls="text-sm font-semibold text-muted-foreground mb-1"),
                        P(str(choice.created_at)[:10], cls="text-muted-foreground text-sm"),
                    ),
                    cls="space-y-2",
                ),
                cls="p-6 mb-4",
            ),
            # Options Card (only when pending)
            (
                Card(
                    H2(f"📝 Options ({len(options)})", cls="text-xl font-semibold mb-4"),
                    Div(
                        *[
                            Div(
                                Span(
                                    getattr(opt, "title", "Untitled"),
                                    cls="font-medium",
                                ),
                                P(
                                    getattr(opt, "description", ""),
                                    cls="text-sm text-muted-foreground",
                                ),
                                cls="p-3 bg-muted rounded-lg mb-2",
                            )
                            for opt in options
                        ]
                        if options
                        else [
                            P(
                                "No options defined yet. Add options to make a decision.",
                                cls="text-muted-foreground",
                            )
                        ],
                    ),
                    cls="p-6 mb-4",
                )
                if status == "pending"
                else Div()
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
                    (
                        Button(
                            "➕ Add Option",
                            **{
                                "hx-get": f"/choices/{choice.uid}/add-option",
                                "hx-target": "#modal",
                            },
                            variant=ButtonT.secondary,
                            cls="mr-2",
                        )
                        if status == "pending"
                        else ""
                    ),
                    (
                        Button(
                            "✅ Make Decision",
                            **{"hx-get": f"/choices/{choice.uid}/decide", "hx-target": "#modal"},
                            variant=ButtonT.success,
                        )
                        if status == "pending" and len(options) >= 2
                        else ""
                    ),
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-4 mb-4",
            ),
            # Lateral Relationships Section
            EntityRelationshipsSection(
                entity_uid=choice.uid,
                entity_type="choices",
            ),
            cls=f"{Container.STANDARD} {Spacing.PAGE}",
        )

        return await BasePage(
            content=content,
            title=choice.title,
            page_type=PageType.STANDARD,
            request=request,
            active_page="choices",
        )

    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_choices_ui_routes"]
