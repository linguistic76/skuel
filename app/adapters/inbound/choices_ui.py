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

from typing import Any, cast

from fasthtml.common import H1, H2, H3, Div, Form, Option, P, Span
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.form_helpers import (
    ActivityFilters,
    parse_activity_filters,
    parse_datetime_safe,
    parse_enum_safe,
    safe_form_string,
)
from adapters.inbound.route_factories import (
    DashboardUIConfig,
    DashboardUIFactory,
    QuickAddConfig,
    QuickAddRouteFactory,
    require_owned_entity,
)
from adapters.inbound.ui_helpers import (
    render_entity_not_found_page,
    render_safe_error_response,
)
from core.models.choice.choice_request import (
    ChoiceCreateRequest,
    ChoiceOptionCreateRequest,
)
from core.models.entity_requests import EntityUpdateRequest
from core.models.enums import Domain as DomainEnum
from core.models.enums import Priority as PriorityEnum
from core.models.enums.choice_enums import ChoiceType
from core.services.choices_service import ChoicesService
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.type_converters import get_enum_attr_str
from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.choices.layout import create_choices_page
from ui.choices.views import ChoicesViewComponents
from ui.feedback import Badge, BadgeT
from ui.forms import Input, Label, Select, Textarea
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.modals import Modal, ModalBox
from ui.page_contexts import ChoicesPageContext
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.relationships import EntityRelationshipsSection
from ui.tokens import Container, Spacing

logger = get_logger("skuel.routes.choice.ui")

# Static option lists — must match Domain/ChoiceType enum values in core/models/enums/
CHOICE_TYPES = ["binary", "multiple", "ranking", "strategic", "operational"]
DOMAINS = ["personal", "business", "health", "finance", "social"]

# RouteDecorator and Request imported from adapters.inbound.fasthtml_types


def parse_filters(request) -> ActivityFilters:
    """Extract filter parameters from request query params."""
    return parse_activity_filters(request, default_status="pending", default_sort_by="deadline")


# ============================================================================
# UI ROUTES
# ============================================================================


# ============================================================================
# Form Parsing Helpers (pure — no service calls, no request access)
# ============================================================================


def parse_options_from_form(form: Any) -> list[dict[str, str]]:
    """Parse options[0].title, options[0].description, etc. from form data."""
    options = []
    index = 0
    while True:
        title_key = f"options[{index}].title"
        desc_key = f"options[{index}].description"
        if title_key not in form:
            break
        title = safe_form_string(form.get(title_key))
        desc = safe_form_string(form.get(desc_key))
        if title and desc:
            options.append({"title": title, "description": desc})
        index += 1
    return options


def parse_choice_create_request(
    form_data: dict[str, Any],
) -> ChoiceCreateRequest:
    """Parse form data into a ChoiceCreateRequest. Pure function, no side effects."""
    title = safe_form_string(form_data.get("title"))
    description = safe_form_string(form_data.get("description")) or None
    choice_type = safe_form_string(form_data.get("choice_type")) or "binary"
    domain = safe_form_string(form_data.get("domain")) or "personal"
    priority = safe_form_string(form_data.get("priority")) or "medium"
    deadline_str = form_data.get("decision_deadline", "")

    options = parse_options_from_form(form_data)

    # Parse deadline
    decision_deadline = parse_datetime_safe(deadline_str)

    # Map string values to enums (guard against invalid form input)
    choice_type_enum = parse_enum_safe(ChoiceType, choice_type, ChoiceType.MULTIPLE)
    domain_enum = parse_enum_safe(DomainEnum, domain, DomainEnum.PERSONAL)
    priority_enum = parse_enum_safe(PriorityEnum, priority, PriorityEnum.MEDIUM)

    option_requests = [
        ChoiceOptionCreateRequest(title=opt["title"], description=opt["description"])
        for opt in options
    ]

    return ChoiceCreateRequest(
        title=title,
        description=description or title,
        choice_type=choice_type_enum,
        domain=domain_enum,
        priority=priority_enum,
        decision_deadline=decision_deadline,
        options=option_requests,
    )


def parse_choice_update_request(form: Any) -> EntityUpdateRequest:
    """Parse edit form into an EntityUpdateRequest. Pure function, no side effects."""
    title = safe_form_string(form.get("title"))
    description = safe_form_string(form.get("description")) or None
    priority_str = safe_form_string(form.get("priority")) or "medium"
    domain_str = safe_form_string(form.get("domain")) or "personal"

    priority_enum = parse_enum_safe(PriorityEnum, priority_str, PriorityEnum.MEDIUM)
    domain_enum = parse_enum_safe(DomainEnum, domain_str, DomainEnum.PERSONAL)

    return EntityUpdateRequest(
        title=title if title else None,
        description=description,
        priority=priority_enum,
        domain=domain_enum,
    )


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
    # DASHBOARD + VIEW FRAGMENTS (via DashboardUIFactory)
    # ========================================================================

    async def fetch_choices_context(user_uid: str, filters: ActivityFilters) -> Any:
        """Fetch filtered choices context from service."""
        return await choices_service.get_filtered_context(user_uid, filters.status, filters.sort_by)

    def build_choices_page_context(
        svc_ctx: dict[str, Any], filters: ActivityFilters
    ) -> Any:
        """Map service context to ChoicesPageContext."""
        return ChoicesPageContext(
            entities=svc_ctx["entities"],
            filters=filters.to_dict(),
            stats=svc_ctx["stats"],
        )

    async def render_choices_create(user_uid: str, svc_ctx: dict[str, Any]) -> Any:
        """Render choices create view."""
        return ChoicesViewComponents.render_create_view(
            choice_types=CHOICE_TYPES,
            domains=DOMAINS,
        )

    async def render_choices_analytics(user_uid: str, request: Any) -> Any:
        """Render choices analytics view."""
        analytics_result = await choices_service.get_analytics_context(user_uid)
        if analytics_result.is_error:
            return render_error_banner("Failed to load analytics")
        return ChoicesViewComponents.render_analytics_view(
            analytics_data=analytics_result.value,
        )

    def render_choices_list_fragment(entities: list[Any]) -> Any:
        """Render choice list fragment for HTMX updates."""
        items = [ChoicesViewComponents._render_choice_item(choice) for choice in entities]
        return Div(
            *items if items else [EmptyState(title="No decisions found")],
            id="choice-list",
            cls="space-y-3",
        )

    DashboardUIFactory.register_routes(
        rt,
        DashboardUIConfig(
            domain_name="choices",
            title="Choices",
            subtitle="Make and track important decisions",
            default_view="list",
            views=("list", "create", "analytics"),
            parse_filters=parse_filters,
            fetch_filtered_context=fetch_choices_context,
            render_view_tabs=ChoicesViewComponents.render_view_tabs,
            render_list_view=ChoicesViewComponents.render_list_view,
            render_create_view=render_choices_create,
            render_third_view=render_choices_analytics,
            build_page_context=build_choices_page_context,
            render_list_fragment=render_choices_list_fragment,
            create_page=create_choices_page,
        ),
    )

    # ========================================================================
    # QUICK ADD (via QuickAddRouteFactory)
    # ========================================================================

    def validate_choice_options(form_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate that at least 2 options are provided."""
        options = parse_options_from_form(form_data)
        if len(options) < 2:
            return (False, "At least 2 options are required")
        return (True, "")

    async def create_choice_from_form(form_data: dict[str, Any], user_uid: str) -> Result[Any]:
        """Domain-specific choice creation logic."""
        choice_request = parse_choice_create_request(form_data)
        return cast(
            "Result[Any]", await choices_service.core.create_choice(choice_request, user_uid)
        )

    async def render_choice_success_view(user_uid: str) -> Any:
        """Render list view after successful choice creation."""
        result = await choices_service.get_filtered_context(user_uid)
        if result.is_error:
            return render_error_banner("Failed to load choices")
        svc_ctx = result.value
        page_ctx = ChoicesPageContext(
            entities=svc_ctx["entities"],
            filters={"status": "pending", "sort_by": "deadline"},
            stats=svc_ctx["stats"],
        )
        return ChoicesViewComponents.render_list_view(ctx=page_ctx)

    async def render_choice_add_another_view(user_uid: str) -> Any:
        """Render create view for add-another flow."""
        return ChoicesViewComponents.render_create_view(
            choice_types=CHOICE_TYPES,
            domains=DOMAINS,
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
            return Modal(
                "decide-modal",
                ModalBox(
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
                        **{"onclick": "UIkit.modal('#decide-modal').hide()"},
                    ),
                ),
                open_on_load=True,
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
                        cls="uk-radio",
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

        return Modal(
            "decide-choice-modal",
            ModalBox(
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
                            **{"onclick": "UIkit.modal('#decide-choice-modal').hide()"},
                        ),
                    ),
                    **{
                        "hx-post": f"/choices/{uid}/decide",
                        "hx-target": "body",
                    },
                ),
            ),
            open_on_load=True,
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
        decision_rationale = safe_form_string(form.get("decision_rationale")) or None

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

        return Modal(
            "edit-choice-modal",
            ModalBox(
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
                            **{"onclick": "UIkit.modal('#edit-choice-modal').hide()"},
                        ),
                    ),
                    **{
                        "hx-post": f"/choices/{uid}/edit",
                        "hx-target": "body",
                    },
                ),
            ),
            open_on_load=True,
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

        try:
            update_request = parse_choice_update_request(form)
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

        except Exception as e:  # safety-net: HTTP error boundary
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

        return Modal(
            "add-option-modal",
            ModalBox(
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
                            **{"onclick": "UIkit.modal('#add-option-modal').hide()"},
                        ),
                    ),
                    **{
                        "hx-post": f"/choices/{uid}/add-option",
                        "hx-target": "body",
                    },
                ),
            ),
            open_on_load=True,
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
        title = safe_form_string(form.get("title"))
        description = safe_form_string(form.get("description"))

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
            return await render_entity_not_found_page("Choice", uid, "choices", request)

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
                P(
                    choice.description or "No description provided",
                    cls="text-muted-foreground mb-4",
                ),
                # Status and Urgency badges
                Div(
                    Badge(f"Status: {choice.status.value}", variant=BadgeT.info, cls="mr-2"),
                    Badge(f"Priority: {priority.title()}", variant=BadgeT.ghost, cls="mr-2"),
                    Badge(f"Domain: {domain.title()}", variant=BadgeT.outline, cls="mr-2"),
                    Badge(f"Type: {choice_type.title()}", variant=BadgeT.outline),
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
