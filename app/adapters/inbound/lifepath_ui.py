"""
LifePath UI Routes
==================

UI routes and presentation logic for LifePath domain.

Domain #14: The Destination - "Everything flows toward the life path"

UI Routes:
- GET /lifepath - Main dashboard
- GET /lifepath/vision - Vision capture page
- POST /lifepath/vision - Process vision capture
- POST /lifepath/designate - Designate an LP as life path
- GET /lifepath/alignment - Alignment dashboard

Philosophy:
    "The user's vision is understood via the words user uses to communicate,
    the UserContext is determined via user's actions."
"""

from typing import Any

from fasthtml.common import H1, H2, H3, A, Div, Form, P, Span
from starlette.requests import Request
from starlette.responses import RedirectResponse

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.buttons import Button
from ui.cards import Card
from ui.feedback import Badge, BadgeT, Progress
from ui.forms import Label, Textarea
from ui.layout import Size
from ui.patterns.drawer_layout import create_drawer_layout
from ui.tokens import Container

logger = get_logger("skuel.routes.lifepath.ui")

# Menu items for LifePath drawer navigation
LIFEPATH_MENU_ITEMS: list[tuple[str, str, str, str]] = [
    ("dashboard", "Dashboard", "/lifepath", "home"),
    ("vision", "Vision", "/lifepath/vision", "eye"),
    ("alignment", "Alignment", "/lifepath/alignment", "chart-bar"),
]


def _lifepath_drawer_layout(active_page: str, content: Any) -> Any:
    """
    Create drawer layout for LifePath pages.

    Args:
        active_page: Current active page identifier
        content: Main content to render

    Returns:
        Complete drawer layout with LifePath navigation
    """
    return create_drawer_layout(
        drawer_id="lifepath-drawer",
        title="Life Path",
        menu_items=LIFEPATH_MENU_ITEMS,
        active_page=active_page,
        content=content,
        subtitle="Your Journey",
    )


def create_lifepath_ui_routes(
    _app: Any,
    rt: Any,
    lifepath_service: Any,
    services: Any = None,
) -> list:
    """
    Create LifePath UI routes.

    Args:
        _app: FastHTML app instance (unused)
        rt: FastHTML route decorator
        lifepath_service: LifePath service facade
        services: Services container (optional, for future use)

    Returns:
        List of registered route functions
    """

    @rt("/lifepath")
    async def lifepath_dashboard(request: Request) -> Any:
        """Main life path dashboard."""
        user_uid = require_authenticated_user(request)

        if not lifepath_service:
            return _service_unavailable_page()

        status_result = await lifepath_service.get_full_status(user_uid)

        if status_result.is_error:
            return _error_page(str(status_result.expect_error()))

        status = status_result.value

        # Build dashboard content
        content = _build_dashboard_content(status, user_uid)

        return _lifepath_drawer_layout("dashboard", content)

    @rt("/lifepath/vision")
    async def vision_capture_page(request: Request) -> Any:
        """Vision capture page - where user expresses their vision."""
        user_uid = require_authenticated_user(request)

        if not lifepath_service:
            return _service_unavailable_page()

        # Check if user already has a vision
        designation_result = await lifepath_service.core.get_designation(user_uid)
        existing_vision = ""
        if designation_result.is_ok and designation_result.value:
            existing_vision = designation_result.value.vision_statement

        content = Div(
            H1("Express Your Vision", cls="text-3xl font-bold mb-6"),
            P(
                "What do you want to become? Express your life vision in your own words.",
                cls="text-lg text-muted-foreground mb-8",
            ),
            Card(
                Div(
                    Form(
                        Div(
                            Label("Your Vision", for_="vision"),
                            Textarea(
                                existing_vision or "",
                                id="vision",
                                name="vision_statement",
                                placeholder="I want to become a mindful technical leader who builds products that matter and makes a positive impact on the world...",
                                cls="w-full h-48 p-4 border rounded-lg",
                                required=True,
                            ),
                            P(
                                "Be specific about who you want to become, not just what you want to achieve.",
                                cls="text-sm text-muted-foreground mt-2",
                            ),
                            cls="mb-6",
                        ),
                        Button(
                            "Extract Themes & Get Recommendations",
                            type="submit",
                            cls="btn btn-primary w-full",
                        ),
                        method="post",
                        action="/lifepath/vision",
                        cls="space-y-4",
                    ),
                    cls="p-6",
                ),
                cls=Container.NARROW,
            ),
            cls="container mx-auto px-4 py-8",
        )

        return _lifepath_drawer_layout("vision", content)

    @rt("/lifepath/vision", methods=["POST"])
    async def process_vision_capture(request: Request) -> Any:
        """Process vision capture and show recommendations."""
        user_uid = require_authenticated_user(request)

        form = await request.form()
        vision_statement = str(form.get("vision_statement", "")).strip()

        if not vision_statement or len(vision_statement) < 10:
            return _error_page("Please provide a vision statement of at least 10 characters.")

        if not lifepath_service:
            return _service_unavailable_page()

        # Capture and recommend
        result = await lifepath_service.capture_and_recommend(user_uid, vision_statement)

        if result.is_error:
            return _error_page(str(result.expect_error()))

        data = result.value

        # Build recommendations page
        content = _build_recommendations_page(data, user_uid)

        return _lifepath_drawer_layout("vision", content)

    @rt("/lifepath/designate", methods=["POST"])
    async def designate_life_path(request: Request) -> Any:
        """Designate an LP as the user's life path."""
        user_uid = require_authenticated_user(request)

        form = await request.form()
        life_path_uid = str(form.get("life_path_uid", "")).strip()

        if not life_path_uid:
            return _error_page("Please select a Learning Path.")

        if not lifepath_service:
            return _service_unavailable_page()

        # Designate and calculate initial alignment
        result = await lifepath_service.designate_and_calculate(user_uid, life_path_uid)

        if result.is_error:
            return _error_page(str(result.expect_error()))

        # Redirect to alignment dashboard
        return RedirectResponse(url="/lifepath/alignment", status_code=303)

    @rt("/lifepath/alignment")
    async def alignment_dashboard(request: Request) -> Any:
        """Alignment dashboard showing word-action alignment."""
        user_uid = require_authenticated_user(request)

        if not lifepath_service:
            return _service_unavailable_page()

        status_result = await lifepath_service.get_full_status(user_uid)

        if status_result.is_error:
            return _error_page(str(status_result.expect_error()))

        status = status_result.value

        if not status.get("has_designation"):
            # Redirect to vision capture if no designation
            return RedirectResponse(url="/lifepath/vision", status_code=303)

        content = _build_alignment_dashboard(status, user_uid)

        return _lifepath_drawer_layout("alignment", content)

    logger.info("LifePath UI routes registered (5 routes)")

    return [
        lifepath_dashboard,
        vision_capture_page,
        process_vision_capture,
        designate_life_path,
        alignment_dashboard,
    ]


# ============================================================================
# UI HELPER FUNCTIONS
# ============================================================================


def _service_unavailable_page():
    """Return page when LifePath service is not available."""
    return Div(
        H1("Service Unavailable", cls="text-2xl font-bold text-red-600"),
        P("The LifePath service is not available. Please try again later."),
        cls="container mx-auto px-4 py-8",
    )


def _error_page(message: str):
    """Return error page."""
    return Div(
        H1("Error", cls="text-2xl font-bold text-red-600"),
        P(message, cls="text-muted-foreground mt-2"),
        A("Go back", href="/lifepath", cls="btn btn-primary mt-4"),
        cls="container mx-auto px-4 py-8",
    )


def _build_dashboard_content(status: dict, user_uid: str) -> Any:
    """Build the main dashboard content."""
    if not status.get("has_vision"):
        return Div(
            H1("Welcome to Your Life Path", cls="text-3xl font-bold mb-6"),
            P(
                "You haven't expressed your vision yet. Start by telling us what you want to become.",
                cls="text-lg text-muted-foreground mb-8",
            ),
            A(
                "Express Your Vision",
                href="/lifepath/vision",
                cls="btn btn-primary btn-lg",
            ),
            cls="container mx-auto px-4 py-8 text-center",
        )

    # Has vision - show summary
    alignment = status.get("alignment", {})
    alignment_score = alignment.get("alignment_score", 0)
    alignment_level = alignment.get("alignment_level", "unknown")

    return Div(
        H1("Your Life Path", cls="text-3xl font-bold mb-6"),
        # Vision summary
        Card(
            Div(
                H3("Your Vision", cls="font-semibold text-lg mb-2"),
                P(
                    status.get("vision", {}).get("statement", "No vision"),
                    cls="text-muted-foreground italic",
                ),
                Div(
                    *[
                        Badge(theme, variant=BadgeT.outline, cls="mr-2")
                        for theme in status.get("vision", {}).get("themes", [])[:5]
                    ],
                    cls="mt-4",
                ),
                cls="p-4",
            ),
            cls="mb-6",
        ),
        # Alignment score
        Card(
            Div(
                H3("Alignment Score", cls="font-semibold text-lg mb-2"),
                Div(
                    Span(f"{int(alignment_score * 100)}%", cls="text-4xl font-bold"),
                    Span(f" ({alignment_level})", cls="text-xl text-muted-foreground ml-2"),
                    cls="mb-4",
                ),
                Progress(
                    value=int(alignment_score * 100),
                    max=100,
                    cls="w-full h-4",
                ),
                P(
                    "Are you LIVING what you SAID?",
                    cls="text-sm text-muted-foreground mt-2",
                ),
                cls="p-4",
            ),
            cls="mb-6",
        ),
        # Quick actions
        Div(
            A("View Alignment Details", href="/lifepath/alignment", cls="btn btn-outline mr-4"),
            A("Update Vision", href="/lifepath/vision", cls="btn btn-outline"),
            cls="flex gap-4",
        ),
        # Daily focus
        _build_daily_focus(status.get("daily_focus")),
        cls="container mx-auto px-4 py-8",
    )


def _build_recommendations_page(data: dict, user_uid: str) -> Any:
    """Build recommendations page after vision capture."""
    vision = data.get("vision", {})
    recommendations = data.get("recommendations", [])

    rec_cards = [
        Card(
            Form(
                Div(
                    H3(rec.get("lp_name", "Unknown"), cls="font-semibold text-lg"),
                    P(
                        f"Match: {int(rec.get('match_score', 0) * 100)}%",
                        cls="text-sm text-muted-foreground",
                    ),
                    Div(
                        *[
                            Badge(t, variant=BadgeT.primary, size=Size.sm, cls="mr-1")
                            for t in rec.get("matching_themes", [])[:3]
                        ],
                        cls="mt-2",
                    ),
                    cls="p-4",
                ),
                Div(
                    Button(
                        "Choose This Path",
                        type="submit",
                        cls="btn btn-primary btn-sm",
                    ),
                    cls="p-4 pt-0",
                ),
                method="post",
                action="/lifepath/designate",
                **{
                    "hx-post": "/lifepath/designate",
                    "hx-vals": f'{{"life_path_uid": "{rec.get("lp_uid", "")}"}}',
                },
            ),
            cls="mb-4",
        )
        for rec in recommendations
    ]

    return Div(
        H1("Choose Your Life Path", cls="text-3xl font-bold mb-4"),
        P(f'Your vision: "{vision.get("statement", "")}"', cls="text-muted-foreground italic mb-2"),
        P(
            f"Themes extracted: {', '.join(vision.get('themes', []))}",
            cls="text-sm text-muted-foreground mb-8",
        ),
        H2("Recommended Learning Paths", cls="text-xl font-semibold mb-4"),
        *rec_cards if rec_cards else [P("No matching Learning Paths found. Create one!")],
        cls=f"container mx-auto px-4 py-8 {Container.NARROW}",
    )


def _build_alignment_dashboard(status: dict, user_uid: str) -> Any:
    """Build alignment dashboard with 5-dimension breakdown."""
    alignment = status.get("alignment", {})
    dimensions = alignment.get("dimensions", {})
    recommendations = status.get("recommendations", [])

    dimension_cards = []
    for dim_name, score in dimensions.items():
        color = (
            "text-green-600"
            if score >= 0.7
            else "text-yellow-600"
            if score >= 0.4
            else "text-red-600"
        )
        dimension_cards.append(
            Div(
                Div(
                    Span(dim_name.title(), cls="text-sm font-medium"),
                    Span(f"{int(score * 100)}%", cls=f"text-lg font-bold {color}"),
                    cls="flex justify-between items-center mb-1",
                ),
                Progress(value=int(score * 100), max=100, cls="w-full h-2"),
                cls="mb-4",
            )
        )

    rec_items = [
        Div(
            Span(rec.get("title", ""), cls="font-medium"),
            P(rec.get("description", ""), cls="text-sm text-muted-foreground"),
            cls="p-3 bg-muted rounded mb-2",
        )
        for rec in recommendations[:5]
    ]

    return Div(
        H1("Life Path Alignment", cls="text-3xl font-bold mb-6"),
        # Overall score
        Card(
            Div(
                Div(
                    Span(
                        f"{int(alignment.get('alignment_score', 0) * 100)}%",
                        cls="text-5xl font-bold",
                    ),
                    Span(
                        alignment.get("alignment_level", "").title(),
                        cls="text-2xl text-muted-foreground ml-4",
                    ),
                    cls="flex items-baseline mb-4",
                ),
                P(
                    "Are you LIVING what you SAID?",
                    cls="text-muted-foreground",
                ),
                cls="p-6 text-center",
            ),
            cls="mb-8",
        ),
        # Dimension breakdown
        Card(
            Div(
                H3("5-Dimension Breakdown", cls="font-semibold text-lg mb-4"),
                *dimension_cards,
                cls="p-6",
            ),
            cls="mb-8",
        ),
        # Recommendations
        Card(
            Div(
                H3("Recommendations", cls="font-semibold text-lg mb-4"),
                *rec_items if rec_items else [P("Great work! Keep it up.")],
                cls="p-6",
            ),
            cls="mb-8",
        ),
        A("Back to Dashboard", href="/lifepath", cls="btn btn-outline"),
        cls=f"container mx-auto px-4 py-8 {Container.NARROW}",
    )


def _build_daily_focus(daily_focus: dict | None) -> Any:
    """Build daily focus card."""
    if not daily_focus:
        return Div()

    return Card(
        Div(
            H3("Today's Focus", cls="font-semibold text-lg mb-2"),
            P(daily_focus.get("focus", ""), cls="text-xl font-medium mb-2"),
            P(daily_focus.get("reason", ""), cls="text-sm text-muted-foreground"),
            P(
                f"Action: {daily_focus.get('action', '')}",
                cls="text-sm text-muted-foreground mt-2 italic",
            ),
            cls="p-4",
        ),
        cls="mt-6",
    )
