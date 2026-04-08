"""
Pathways UI Components
======================

Component-based UI routes for structured learning pathway browsing and progress.
All pages use BasePage for consistent layout.
Wired to real LpService and UserProgressService.
"""

from typing import Any

from fasthtml.common import (
    H1,
    H3,
    H4,
    Div,
    Header,
    Li,
    Option,
    P,
    Span,
    Ul,
)

from adapters.inbound.auth import require_authenticated_user
from core.models.pathways.pathways_request import LearningPathFilterRequest
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody, CardHeader, CardTitle
from ui.feedback import Badge, BadgeT
from ui.forms import LabelSelect
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.form_generator import FormGenerator
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.ui_types import (
    ActivePathData,
    LearningStatsData,
)

logger = get_logger("skuel.ui.pathways")


def _path_to_display_dict(path: Any) -> dict[str, Any]:
    """Convert a LearningPath domain model to a display dict for browser cards."""
    return {
        "uid": path.uid,
        "title": path.title or "Untitled Path",
        "description": path.description or "",
        "difficulty": _difficulty_label(path.difficulty_rating),
        "estimated_hours": int(path.estimated_hours or 0),
        "tags": list(path.tags) if path.tags else [],
    }


def _difficulty_label(rating: float) -> str:
    """Convert 0.0-1.0 difficulty rating to human-readable label."""
    if rating <= 0.35:
        return "beginner"
    if rating <= 0.65:
        return "intermediate"
    return "advanced"


def _render_step_browser_card(step: Any) -> Any:
    """Render a path step as a browseable card using CardGenerator."""

    def render_difficulty(value: float) -> Any:
        if not value:
            return None
        return Badge(_difficulty_label(value).title(), variant=BadgeT.primary, size=Size.sm)

    def render_hours(value: float) -> Any:
        if not value:
            return None
        return Badge(f"{value:.1f}h", variant=BadgeT.secondary, size=Size.sm)

    def render_sequence(value: int) -> Any:
        if not value:
            return None
        return Badge(f"Step {value}", variant=BadgeT.info, size=Size.sm)

    def render_description(value: str) -> Any:
        # Combine description and intent fallback
        text = value or getattr(step, "intent", "") or ""
        if not text:
            return None
        return P(text[:200], cls="text-muted-foreground text-sm")

    return CardGenerator.from_dataclass(
        step,
        display_fields=["description", "difficulty_rating", "estimated_hours", "sequence"],
        show_labels=False,
        title_href=f"/explore/ps/{step.uid}",
        field_renderers={
            "description": render_description,
            "difficulty_rating": render_difficulty,
            "estimated_hours": render_hours,
            "sequence": render_sequence,
        },
    )


class PathwaysUIComponents:
    """Reusable component library for pathway browsing interface."""

    @staticmethod
    def render_filter_form() -> Any:
        """Learning path filter form using FormGenerator with custom select widgets."""
        return FormGenerator.from_model(
            LearningPathFilterRequest,
            action="/api/pathways/filter-paths",
            method="POST",
            include_fields=["difficulty", "domain", "duration"],
            custom_widgets={
                "difficulty": LabelSelect(
                    Option("All Levels", value="all", selected=True),
                    Option("Beginner", value="beginner"),
                    Option("Intermediate", value="intermediate"),
                    Option("Advanced", value="advanced"),
                    label="Difficulty Level",
                    name="difficulty",
                ),
                "domain": LabelSelect(
                    Option("All Domains", value="all", selected=True),
                    Option("Programming", value="programming"),
                    Option("Data Science", value="data_science"),
                    Option("Web Development", value="web_dev"),
                    Option("Cloud Computing", value="cloud"),
                    label="Domain",
                    name="domain",
                ),
                "duration": LabelSelect(
                    Option("Any Duration", value="all", selected=True),
                    Option("Under 20 hours", value="short"),
                    Option("20-50 hours", value="medium"),
                    Option("50+ hours", value="long"),
                    label="Time Commitment",
                    name="duration",
                ),
            },
            form_attrs={
                "cls": "space-y-4",
                "hx_post": "/api/pathways/filter-paths",
                "hx_target": "#learning-paths-grid",
            },
            submit_label="Apply Filters",
        )

    @staticmethod
    def render_learning_path_card(path: ActivePathData) -> Any:
        """Create a learning path card for the dashboard."""
        return Card(
            Div(
                # Path Header
                Div(
                    H3(path.title, cls="text-lg font-semibold"),
                    Badge(path.difficulty.title(), variant=BadgeT.primary),
                    cls="flex justify-between items-start mb-2",
                ),
                # Progress Bar
                Div(
                    Div(f"{path.progress:.1f}% Complete", cls="text-sm text-muted-foreground mb-1"),
                    Div(
                        Div(
                            cls="h-2 bg-primary rounded-full transition-all",
                            style=f"width: {path.progress}%",
                        ),
                        cls="w-full bg-secondary rounded-full h-2",
                    ),
                    cls="mb-3",
                ),
                # Current Step & Time
                Div(
                    P(f"Current: {path.current_step}", cls="text-sm text-foreground/80"),
                    P(f"{path.time_invested} invested", cls="text-xs text-muted-foreground"),
                    P(
                        f"{path.estimated_completion} to complete",
                        cls="text-xs text-muted-foreground",
                    ),
                    cls="space-y-1 mb-4",
                ),
                # Action Button
                ButtonLink(
                    "Continue Learning",
                    href=f"/pathways/path/{path.uid}",
                    variant=ButtonT.primary,
                    size=Size.sm,
                    cls="w-full",
                ),
                cls="p-4",
            ),
            cls="hover:shadow-lg transition-shadow",
        )

    @staticmethod
    def render_learning_path_browser_card(path: dict[str, Any]) -> Any:
        """Create a learning path card for the browse page using CardGenerator."""

        def render_difficulty(value: str) -> Any:
            return Badge(value.title(), variant=BadgeT.primary)

        def render_hours(value: int) -> Any:
            return Span(f"{value}h", cls="text-sm text-muted-foreground")

        def render_tags(value: list) -> Any:
            if not value:
                return None
            return Div(
                *[Badge(tag, variant=BadgeT.outline, size=Size.sm) for tag in value[:3]],
                cls="flex flex-wrap gap-1",
            )

        action_buttons = Div(
            ButtonLink(
                "View Details",
                href=f"/pathways/path/{path['uid']}",
                variant=ButtonT.outline,
                size=Size.sm,
                cls="flex-1",
            ),
            Button(
                "Enroll",
                variant=ButtonT.primary,
                size=Size.sm,
                cls="flex-1",
                **{
                    "hx-post": f"/api/pathways/enroll/{path['uid']}",
                    "hx-target": "#main-content",
                },
            ),
            cls="flex gap-2",
        )

        return CardGenerator.from_dataclass(
            path,
            display_fields=["description", "estimated_hours", "difficulty", "tags"],
            show_labels=False,
            field_renderers={
                "difficulty": render_difficulty,
                "estimated_hours": render_hours,
                "tags": render_tags,
            },
            actions=action_buttons,
            card_attrs={"cls": "hover:shadow-lg transition-shadow h-full p-4"},
        )

    @staticmethod
    def render_step_item(step: Any, index: int, is_mastered: bool) -> Any:
        """Render a single path step in a path's curriculum list."""
        mastery_badge = (
            Badge("Mastered", variant=BadgeT.success, size=Size.sm)
            if is_mastered
            else Badge("Not started", variant=BadgeT.outline, size=Size.sm)
        )
        difficulty = _difficulty_label(step.difficulty_rating) if step.difficulty_rating else ""
        difficulty_badge = (
            Badge(difficulty.title(), variant=BadgeT.primary, size=Size.sm) if difficulty else None
        )
        hours_text = f"{step.estimated_hours:.0f}h" if step.estimated_hours else ""

        return Div(
            Div(
                # Sequence number
                Badge(f"Step {index}", variant=BadgeT.primary, cls="mr-2"),
                # Title
                H4(step.title or f"Step {index}", cls="text-lg font-semibold flex-1"),
                # Mastery status
                mastery_badge,
                cls="flex items-center justify-between mb-2",
            ),
            Div(
                P(
                    step.description or step.intent or "",
                    cls="text-muted-foreground mb-2",
                ),
                Div(
                    Span(hours_text, cls="text-sm text-muted-foreground mr-3")
                    if hours_text
                    else None,
                    difficulty_badge,
                    cls="flex items-center gap-2",
                ),
                cls="ml-8",
            ),
            cls="border border-border rounded-lg p-4 hover:bg-background transition-colors",
        )


def create_pathways_ui_routes(
    _app: Any, rt: Any, _primary_service: Any, orchestrator: Any = None
) -> list[Any]:
    """Create UI routes for pathway browsing and progress tracking."""

    routes: list[Any] = []

    @rt("/pathways")
    async def pathways_dashboard(request) -> Any:
        """Main pathways dashboard with progress overview and active paths."""
        user_uid = require_authenticated_user(request)

        # Fetch dashboard summary from service
        summary_result = await orchestrator.get_dashboard_summary(user_uid)
        active_paths: list[ActivePathData] = []
        stats = LearningStatsData(
            total_hours=0.0,
            concepts_mastered=0,
            active_streak=0,
            completion_rate=0.0,
        )
        if not summary_result.is_error and summary_result.value:
            active_paths = summary_result.value["active_paths"]
            stats = summary_result.value["stats"]

        # Build active paths section
        if active_paths:
            paths_section = Div(
                *[PathwaysUIComponents.render_learning_path_card(p) for p in active_paths],
                cls="space-y-4",
            )
        else:
            paths_section = Div(
                P(
                    "No active learning paths yet. Start exploring!",
                    cls="text-muted-foreground text-center py-8",
                ),
                Div(
                    ButtonLink(
                        "Browse Learning Paths",
                        href="/pathways/browse",
                        variant=ButtonT.primary,
                    ),
                    ButtonLink(
                        "Browse Learning Steps",
                        href="/pathways/steps",
                        variant=ButtonT.secondary,
                    ),
                    cls="flex flex-wrap gap-3 justify-center",
                ),
                cls="text-center",
            )

        content = Div(
            PageHeader(
                "Pathways Dashboard",
                subtitle="Track your learning journey and discover new knowledge",
            ),
            # Learning Stats Overview
            Card(
                CardHeader(CardTitle("Learning Overview")),
                CardBody(
                    StatsGrid(
                        [
                            StatItem(
                                label="Learning Hours",
                                value=f"{stats.total_hours:.0f}",
                                color="primary",
                            ),
                            StatItem(
                                label="Concepts Mastered",
                                value=str(stats.concepts_mastered),
                                color="success",
                            ),
                            StatItem(
                                label="Active Paths", value=str(len(active_paths)), color="primary"
                            ),
                            StatItem(
                                label="Completion Rate",
                                value=f"{stats.completion_rate * 100:.0f}%",
                                color="warning",
                            ),
                        ],
                    ),
                ),
                cls="mb-8",
            ),
            # Active Learning Paths
            Card(
                CardHeader(
                    Div(
                        CardTitle("Active Learning Paths"),
                        Div(
                            ButtonLink(
                                "Browse Learning Paths",
                                href="/pathways/browse",
                                variant=ButtonT.primary,
                                size=Size.sm,
                            ),
                            ButtonLink(
                                "Browse Learning Steps",
                                href="/pathways/steps",
                                variant=ButtonT.secondary,
                                size=Size.sm,
                            ),
                            cls="flex flex-wrap gap-2",
                        ),
                        cls="flex justify-between items-center",
                    ),
                ),
                CardBody(paths_section),
                cls="mb-8",
            ),
            # Quick Actions
            Card(
                CardHeader(CardTitle("Quick Actions")),
                CardBody(
                    Div(
                        ButtonLink(
                            "View Analytics",
                            href="/pathways/analytics",
                            variant=ButtonT.secondary,
                        ),
                        ButtonLink(
                            "Browse Paths",
                            href="/pathways/browse",
                            variant=ButtonT.outline,
                        ),
                        ButtonLink(
                            "Browse Steps",
                            href="/pathways/steps",
                            variant=ButtonT.outline,
                        ),
                        cls="flex flex-wrap gap-3",
                    ),
                ),
                cls="mb-8",
            ),
            cls="container mx-auto px-4 py-6",
        )

        return await BasePage(
            content=content,
            title="Pathways Dashboard",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(pathways_dashboard)

    @rt("/pathways/browse")
    async def browse_learning_paths(request) -> Any:
        """Browse available learning paths with filtering and recommendations."""
        available_paths: list[dict[str, Any]] = []
        paths_result = await orchestrator.list_all_paths(limit=50)
        if not paths_result.is_error and paths_result.value:
            available_paths.extend(_path_to_display_dict(path) for path in paths_result.value)

        if available_paths:
            grid_content = Div(
                *[
                    PathwaysUIComponents.render_learning_path_browser_card(p)
                    for p in available_paths
                ],
                cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6",
            )
        else:
            grid_content = Div(
                P(
                    "No learning paths available yet.",
                    cls="text-muted-foreground text-center py-8",
                ),
            )

        content = Div(
            PageHeader(
                "Browse Learning Paths",
                subtitle="Discover structured learning paths to achieve your goals",
            ),
            # Filters Section
            Card(
                CardHeader(CardTitle("Filter Learning Paths")),
                CardBody(
                    Div(
                        PathwaysUIComponents.render_filter_form(),
                        cls="grid grid-cols-1 md:grid-cols-3 gap-4",
                    ),
                ),
                cls="mb-8",
            ),
            # Learning Paths Grid
            Div(
                grid_content,
                id="learning-paths-grid",
                cls="mb-8",
            ),
            cls="container mx-auto px-4 py-6",
        )

        return await BasePage(
            content=content,
            title="Browse Learning Paths",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(browse_learning_paths)

    @rt("/pathways/steps")
    async def browse_path_steps(request) -> Any:
        """Browse available path steps."""
        require_authenticated_user(request)

        steps: list[Any] = []
        steps_result = await orchestrator.list_steps(limit=50)
        if not steps_result.is_error and steps_result.value:
            steps = steps_result.value

        if steps:
            grid_content = Div(
                *[_render_step_browser_card(s) for s in steps],
                cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6",
            )
        else:
            grid_content = Div(
                P(
                    "No path steps available yet.",
                    cls="text-muted-foreground text-center py-8",
                ),
            )

        content = Div(
            PageHeader(
                "Browse Learning Steps", subtitle="Explore individual path steps across all paths"
            ),
            Div(
                grid_content,
                id="path-steps-grid",
                cls="mb-8",
            ),
            cls="container mx-auto px-4 py-6",
        )

        return await BasePage(
            content=content,
            title="Browse Learning Steps",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(browse_path_steps)

    @rt("/api/pathways/filter-paths", methods=["POST"])
    async def filter_learning_paths(request) -> Any:
        """Filter learning paths by difficulty, domain, and duration."""
        form_data = await request.form()
        difficulty = form_data.get("difficulty", "all")
        domain = form_data.get("domain", "all")
        duration = form_data.get("duration", "all")

        filter_result = await orchestrator.filter_paths(
            difficulty=difficulty,
            domain=domain,
            duration=duration,
            limit=50,
        )
        paths = filter_result.value if not filter_result.is_error else []

        if paths:
            return Div(
                *[PathwaysUIComponents.render_learning_path_browser_card(p) for p in paths],
                cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6",
            )
        return Div(
            P(
                "No learning paths match your filters.",
                cls="text-muted-foreground text-center py-8",
            ),
        )

    routes.append(filter_learning_paths)

    @rt("/pathways/path/{path_uid}")
    async def learning_path_detail(request, path_uid: str) -> Any:
        """Detailed view of a specific learning path with curriculum and progress."""
        user_uid = require_authenticated_user(request)
        detail_result = await orchestrator.get_path_detail_progress(path_uid, user_uid)
        if detail_result.is_error:
            content = Div(
                Card(
                    H1("Learning Path Not Found", cls="text-2xl font-bold mb-4"),
                    P(
                        f"Could not find learning path: {path_uid}",
                        cls="text-muted-foreground mb-4",
                    ),
                    Button(
                        "Back to Pathways",
                        **{"hx-get": "/pathways", "hx-target": "body"},
                        variant=ButtonT.ghost,
                    ),
                    cls="p-6",
                ),
                cls="container mx-auto px-4 py-6",
            )
            return await BasePage(
                content=content,
                title="Path Not Found",
                page_type=PageType.STANDARD,
                request=request,
                active_page="pathways",
            )

        detail = detail_result.value
        path = detail["path"]
        steps = detail["steps"]
        total_steps = len(steps)
        mastered_uids = detail["mastered_uids"]
        is_enrolled = detail["is_enrolled"]
        progress = detail["progress"]

        # Build steps list
        if steps:
            steps_section = Div(
                *[
                    PathwaysUIComponents.render_step_item(
                        s, i + 1, s.uid in mastered_uids or s.is_mastered()
                    )
                    for i, s in enumerate(steps)
                ],
                cls="space-y-4",
            )
        else:
            steps_section = EmptyState(title="No steps defined for this path yet")

        # Learning outcomes
        outcomes = path.outcomes or ()
        difficulty = _difficulty_label(path.difficulty_rating)

        content = Div(
            # Header with Path Info
            Header(
                Div(
                    H1(path.title or "Untitled Path", cls="text-3xl font-bold text-primary"),
                    P(path.description or "", cls="text-lg text-muted-foreground mt-2"),
                    Div(
                        Badge(
                            f"{int(path.estimated_hours or 0)} hours",
                            variant=BadgeT.secondary,
                            cls="mr-2",
                        ),
                        Badge(f"{difficulty.title()}", variant=BadgeT.primary, cls="mr-2"),
                        Badge(f"{total_steps} steps", variant=BadgeT.info),
                        cls="flex flex-wrap gap-2 mt-4",
                    ),
                    cls="flex-1",
                ),
                Div(
                    Div(
                        Span(f"{progress:.0f}%", cls="text-2xl font-bold"),
                        cls="radial-progress text-primary",
                        style=f"--value:{progress}",
                    )
                    if is_enrolled
                    else Button(
                        "Enroll Now",
                        variant=ButtonT.primary,
                        size=Size.lg,
                        **{
                            "hx-post": f"/api/pathways/enroll/{path_uid}",
                            "hx-target": "#main-content",
                        },
                    ),
                    cls="flex-shrink-0",
                ),
                cls="flex items-start justify-between mb-8",
            ),
            # Curriculum — flat step list
            Card(
                CardHeader(CardTitle("Curriculum")),
                CardBody(steps_section),
                cls="mb-8",
            ),
            # Learning Outcomes
            Card(
                CardHeader(CardTitle("Learning Outcomes")),
                CardBody(
                    Ul(
                        *[
                            Li(Span("->", cls="mr-2"), outcome, cls="flex items-start")
                            for outcome in outcomes
                        ],
                        cls="space-y-2",
                    )
                    if outcomes
                    else EmptyState(title="No learning outcomes specified"),
                ),
                cls="mb-8",
            ),
            cls="container mx-auto px-4 py-6",
        )

        return await BasePage(
            content=content,
            title=f"Learning Path: {path.title or path_uid}",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(learning_path_detail)

    @rt("/pathways/analytics")
    async def learning_analytics(request) -> Any:
        """Learning analytics dashboard with real data from user progress profile."""
        user_uid = require_authenticated_user(request)

        analytics_result = await orchestrator.get_learning_analytics(user_uid)
        analytics = analytics_result.value if not analytics_result.is_error else {}
        concepts_mastered = analytics.get("concepts_mastered", 0)
        in_progress = analytics.get("in_progress", 0)
        needs_review = analytics.get("needs_review", 0)
        struggling = analytics.get("struggling", 0)
        active_paths_count = analytics.get("active_paths_count", 0)
        avg_retention = analytics.get("avg_retention", 0.0)

        content = Div(
            PageHeader("Learning Analytics", subtitle="Insights into your learning journey"),
            # Analytics Overview
            Card(
                CardHeader(CardTitle("Knowledge Profile")),
                CardBody(
                    StatsGrid(
                        [
                            StatItem(
                                label="Concepts Mastered",
                                value=str(concepts_mastered),
                                color="success",
                            ),
                            StatItem(label="In Progress", value=str(in_progress), color="primary"),
                            StatItem(
                                label="Avg Retention",
                                value=f"{avg_retention * 100:.0f}%",
                                color="warning",
                            ),
                        ],
                        cols=3,
                    ),
                ),
                cls="mb-8",
            ),
            # Detail Cards
            Card(
                CardHeader(CardTitle("Learning Health")),
                CardBody(
                    StatsGrid(
                        [
                            StatItem(label="Active Paths", value=str(active_paths_count)),
                            StatItem(label="Needs Review", value=str(needs_review)),
                            StatItem(label="Struggling", value=str(struggling)),
                        ],
                        cols=3,
                    ),
                ),
                cls="mb-8",
            ),
            cls="container mx-auto px-4 py-6",
        )

        return await BasePage(
            content=content,
            title="Learning Analytics",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(learning_analytics)

    # ========================================================================
    # LEARNING PATH DETAIL PAGE
    # ========================================================================

    @rt("/lp/{uid}")
    async def lp_detail_view(request, uid: str) -> Any:
        """Learning Path detail view with full context and relationships."""
        path_result = await orchestrator.get_learning_path(uid)

        if not path_result.is_error and path_result.value:
            path = path_result.value
            steps = path.metadata.get("steps", []) if path.metadata else []
            difficulty = _difficulty_label(path.difficulty_rating)
            outcomes = path.outcomes or ()

            detail_content = Card(
                H1(path.title or f"Learning Path: {uid}", cls="text-2xl font-bold mb-4"),
                P(path.description or "", cls="text-muted-foreground mb-4"),
                Div(
                    Badge(difficulty.title(), variant=BadgeT.primary, cls="mr-2"),
                    Badge(
                        f"{int(path.estimated_hours or 0)}h", variant=BadgeT.secondary, cls="mr-2"
                    ),
                    Badge(f"{len(steps)} steps", variant=BadgeT.info, cls="mr-2"),
                    Badge(
                        str(path.path_type.value if path.path_type else "standard"),
                        variant=BadgeT.outline,
                    ),
                    cls="flex flex-wrap gap-2 mb-4",
                ),
                Div(
                    H3("Outcomes", cls="font-semibold mb-2"),
                    Ul(*[Li(o) for o in outcomes], cls="list-disc ml-4"),
                    cls="mb-4",
                )
                if outcomes
                else None,
                ButtonLink("← Back to Pathways", href="/pathways", variant=ButtonT.ghost),
                cls="p-6 mb-4",
            )
        else:
            detail_content = Card(
                H1(f"Learning Path: {uid}", cls="text-2xl font-bold mb-4"),
                P("Learning path not found.", cls="text-muted-foreground mb-4"),
                ButtonLink("← Back to Pathways", href="/pathways", variant=ButtonT.ghost),
                cls="p-6 mb-4",
            )

        content = Div(
            detail_content,
            EntityRelationshipsSection(entity_uid=uid, entity_type="lp"),
            cls="container mx-auto p-6 max-w-4xl",
        )

        return await BasePage(
            content=content,
            title=f"LP: {uid}",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(lp_detail_view)

    logger.info(f"Pathways UI routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_pathways_ui_routes"]
