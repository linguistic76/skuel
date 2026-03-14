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
    H2,
    H3,
    H4,
    A,
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
from ui.cards import Card
from ui.feedback import Badge, BadgeT
from ui.forms import LabelSelect
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.form_generator import FormGenerator
from ui.patterns.relationships import EntityRelationshipsSection
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
    """Render a learning step as a browseable card."""
    difficulty = _difficulty_label(step.difficulty_rating) if step.difficulty_rating else ""
    hours_text = f"{step.estimated_hours:.1f}h" if step.estimated_hours else ""

    badges = []
    if difficulty:
        badges.append(Badge(difficulty.title(), variant=BadgeT.primary, size=Size.sm))
    if hours_text:
        badges.append(Badge(hours_text, variant=BadgeT.secondary, size=Size.sm))
    if step.sequence:
        badges.append(Badge(f"Step {step.sequence}", variant=BadgeT.info, size=Size.sm))

    return Card(
        H4(
            A(
                step.title or f"Step: {step.uid}",
                href=f"/ls/{step.uid}",
                cls="text-primary hover:underline",
            ),
            cls="text-lg font-semibold mb-2",
        ),
        P(
            (step.description or step.intent or "")[:150],
            cls="text-muted-foreground text-sm mb-3",
        ),
        Div(*badges, cls="flex flex-wrap gap-2") if badges else None,
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
        """Create a learning path card for the browse page."""
        return Card(
            Div(
                # Path Header
                Div(
                    H3(path["title"], cls="text-lg font-semibold mb-2"),
                    P(path["description"], cls="text-sm text-muted-foreground mb-3"),
                    cls="mb-4",
                ),
                # Path Info
                Div(
                    Div(
                        Span(f"{path['estimated_hours']}h", cls="text-sm"),
                        cls="text-muted-foreground mb-2",
                    ),
                    Badge(path["difficulty"].title(), variant=BadgeT.primary, cls="mb-3"),
                    cls="mb-4",
                ),
                # Tags
                Div(
                    *[
                        Badge(tag, variant=BadgeT.outline, size=Size.sm, cls="mr-1 mb-1")
                        for tag in path.get("tags", [])[:3]
                    ],
                    cls="mb-4",
                ),
                # Action Buttons
                Div(
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
                ),
                cls="p-4",
            ),
            cls="hover:shadow-lg transition-shadow h-full",
        )

    @staticmethod
    def render_step_item(step: Any, index: int, is_mastered: bool) -> Any:
        """Render a single learning step in a path's curriculum list."""
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


def create_pathways_ui_routes(_app, rt, lp_service, user_progress=None, ls_service=None):
    """Create UI routes for pathway browsing and progress tracking."""

    routes: list[Any] = []

    @rt("/pathways")
    async def pathways_dashboard(request) -> Any:
        """Main pathways dashboard with progress overview and active paths."""
        user_uid = require_authenticated_user(request)

        # Fetch user's learning paths
        active_paths: list[ActivePathData] = []
        total_hours = 0.0
        paths_result = await lp_service.list_user_paths(user_uid)
        if not paths_result.is_error and paths_result.value:
            for path in paths_result.value:
                steps = path.metadata.get("steps", []) if path.metadata else []
                total_steps = len(steps)
                mastered_count = sum(1 for s in steps if s.is_mastered())
                progress = (mastered_count / total_steps * 100.0) if total_steps > 0 else 0.0
                # Find first non-mastered step as current
                current_step = "Complete"
                for s in steps:
                    if not s.is_mastered():
                        current_step = s.title or "Next step"
                        break
                total_hours += path.estimated_hours or 0
                active_paths.append(
                    ActivePathData(
                        uid=path.uid,
                        title=path.title or "Untitled Path",
                        progress=progress,
                        current_step=current_step,
                        estimated_completion=f"{int(path.estimated_hours or 0)}h total",
                        difficulty=_difficulty_label(path.difficulty_rating),
                        time_invested=f"{int(path.estimated_hours or 0)}h est.",
                    )
                )

        # Fetch knowledge profile for stats
        concepts_mastered = 0
        completion_rate = 0.0
        if user_progress:
            profile_result = await user_progress.build_user_knowledge_profile(user_uid)
            if not profile_result.is_error and profile_result.value:
                profile = profile_result.value
                concepts_mastered = len(profile.mastered_knowledge)

        if active_paths:
            completed = sum(1 for p in active_paths if p.progress >= 100.0)
            completion_rate = completed / len(active_paths)

        stats = LearningStatsData(
            total_hours=total_hours,
            concepts_mastered=concepts_mastered,
            active_streak=0,
            completion_rate=completion_rate,
        )

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
            Header(
                H1("Pathways Dashboard", cls="text-3xl font-bold text-primary"),
                P(
                    "Track your learning journey and discover new knowledge",
                    cls="text-lg text-muted-foreground mt-2",
                ),
                cls="mb-8",
            ),
            # Learning Stats Overview
            Card(
                H2("Learning Overview", cls="text-xl font-semibold mb-4"),
                Div(
                    Div(
                        Div(
                            Span("Learning Hours", cls="text-sm text-muted-foreground"),
                            Span(f"{stats.total_hours:.0f}", cls="text-2xl font-bold text-primary"),
                            P("Total estimated hours", cls="text-xs text-muted-foreground"),
                            cls="p-4 text-center",
                        ),
                        Div(
                            Span("Concepts Mastered", cls="text-sm text-muted-foreground"),
                            Span(
                                str(stats.concepts_mastered),
                                cls="text-2xl font-bold text-success",
                            ),
                            P("Across all learning paths", cls="text-xs text-muted-foreground"),
                            cls="p-4 text-center",
                        ),
                        Div(
                            Span("Active Paths", cls="text-sm text-muted-foreground"),
                            Span(
                                str(len(active_paths)),
                                cls="text-2xl font-bold text-primary",
                            ),
                            P("In progress", cls="text-xs text-muted-foreground"),
                            cls="p-4 text-center",
                        ),
                        Div(
                            Span("Completion Rate", cls="text-sm text-muted-foreground"),
                            Span(
                                f"{stats.completion_rate * 100:.0f}%",
                                cls="text-2xl font-bold text-warning",
                            ),
                            P("Started paths finished", cls="text-xs text-muted-foreground"),
                            cls="p-4 text-center",
                        ),
                        cls="grid grid-cols-2 lg:grid-cols-4 gap-4 shadow rounded-lg w-full",
                    ),
                    cls="mb-6",
                ),
                cls="mb-8",
            ),
            # Active Learning Paths
            Card(
                Div(
                    H2("Active Learning Paths", cls="text-xl font-semibold mb-4"),
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
                    cls="flex justify-between items-center mb-4",
                ),
                paths_section,
                cls="mb-8",
            ),
            # Quick Actions
            Card(
                H2("Quick Actions", cls="text-xl font-semibold mb-4"),
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
        paths_result = await lp_service.list_all_paths(limit=50)
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
            Header(
                H1("Browse Learning Paths", cls="text-3xl font-bold text-primary"),
                P(
                    "Discover structured learning paths to achieve your goals",
                    cls="text-lg text-muted-foreground mt-2",
                ),
                cls="mb-8",
            ),
            # Filters Section
            Card(
                H3("Filter Learning Paths", cls="text-lg font-semibold mb-4"),
                Div(
                    PathwaysUIComponents.render_filter_form(),
                    cls="grid grid-cols-1 md:grid-cols-3 gap-4",
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
    async def browse_learning_steps(request) -> Any:
        """Browse available learning steps."""
        require_authenticated_user(request)

        steps: list[Any] = []
        if ls_service:
            steps_result = await ls_service.list_steps(limit=50)
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
                    "No learning steps available yet.",
                    cls="text-muted-foreground text-center py-8",
                ),
            )

        content = Div(
            Header(
                H1("Browse Learning Steps", cls="text-3xl font-bold text-primary"),
                P(
                    "Explore individual learning steps across all paths",
                    cls="text-lg text-muted-foreground mt-2",
                ),
                cls="mb-8",
            ),
            Div(
                grid_content,
                id="learning-steps-grid",
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

    routes.append(browse_learning_steps)

    @rt("/api/pathways/filter-paths", methods=["POST"])
    async def filter_learning_paths(request) -> Any:
        """Filter learning paths by difficulty, domain, and duration."""
        form_data = await request.form()
        difficulty = form_data.get("difficulty", "all")
        domain = form_data.get("domain", "all")
        duration = form_data.get("duration", "all")

        paths: list[dict[str, Any]] = []
        paths_result = await lp_service.list_all_paths(limit=50)
        if not paths_result.is_error and paths_result.value:
            paths = [_path_to_display_dict(p) for p in paths_result.value]

        # Apply filters
        if difficulty and difficulty != "all":
            paths = [p for p in paths if p["difficulty"] == difficulty]
        if domain and domain != "all":
            paths = [p for p in paths if domain in p["tags"]]
        if duration and duration != "all":
            if duration == "short":
                paths = [p for p in paths if p["estimated_hours"] < 20]
            elif duration == "medium":
                paths = [p for p in paths if 20 <= p["estimated_hours"] <= 50]
            elif duration == "long":
                paths = [p for p in paths if p["estimated_hours"] > 50]

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
        path_result = await lp_service.get_learning_path(path_uid)
        if path_result.is_error or not path_result.value:
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

        path = path_result.value
        steps = path.metadata.get("steps", []) if path.metadata else []
        total_steps = len(steps)

        # Check enrollment and mastery
        mastered_uids: set[str] = set()
        is_enrolled = False
        user_uid = require_authenticated_user(request)
        if user_progress:
            profile_result = await user_progress.build_user_knowledge_profile(user_uid)
            if not profile_result.is_error and profile_result.value:
                profile = profile_result.value
                mastered_uids = profile.mastered_uids
                is_enrolled = path_uid in profile.active_learning_paths

        mastered_steps = sum(1 for s in steps if s.uid in mastered_uids or s.is_mastered())
        progress = (mastered_steps / total_steps * 100.0) if total_steps > 0 else 0.0

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
            steps_section = P("No steps defined for this path yet.", cls="text-muted-foreground")

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
                H2("Curriculum", cls="text-xl font-semibold mb-4"),
                steps_section,
                cls="mb-8",
            ),
            # Learning Outcomes
            Card(
                H3("Learning Outcomes", cls="text-lg font-semibold mb-3"),
                Ul(
                    *[
                        Li(Span("->", cls="mr-2"), outcome, cls="flex items-start")
                        for outcome in outcomes
                    ],
                    cls="space-y-2",
                )
                if outcomes
                else P("No learning outcomes specified.", cls="text-muted-foreground"),
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

        concepts_mastered = 0
        in_progress = 0
        needs_review = 0
        struggling = 0
        active_paths_count = 0
        avg_retention = 0.0

        if user_progress:
            profile_result = await user_progress.build_user_knowledge_profile(user_uid)
            if not profile_result.is_error and profile_result.value:
                profile = profile_result.value
                concepts_mastered = len(profile.mastered_knowledge)
                in_progress = len(profile.in_progress_knowledge)
                needs_review = len(profile.needs_review_uids)
                struggling = len(profile.struggling_uids)
                active_paths_count = len(profile.active_learning_paths)
                if profile.mastered_knowledge:
                    avg_retention = sum(
                        m.retention_score for m in profile.mastered_knowledge
                    ) / len(profile.mastered_knowledge)

        content = Div(
            Header(
                H1("Learning Analytics", cls="text-3xl font-bold text-primary"),
                P(
                    "Insights into your learning journey",
                    cls="text-lg text-muted-foreground mt-2",
                ),
                cls="mb-8",
            ),
            # Analytics Overview
            Card(
                H2("Knowledge Profile", cls="text-xl font-semibold mb-4"),
                Div(
                    Div(
                        Div(
                            Span("Concepts Mastered", cls="text-sm text-muted-foreground"),
                            Span(str(concepts_mastered), cls="text-2xl font-bold text-success"),
                            P("Knowledge units mastered", cls="text-xs text-muted-foreground"),
                            cls="p-4 text-center",
                        ),
                        Div(
                            Span("In Progress", cls="text-sm text-muted-foreground"),
                            Span(str(in_progress), cls="text-2xl font-bold text-primary"),
                            P("Currently learning", cls="text-xs text-muted-foreground"),
                            cls="p-4 text-center",
                        ),
                        Div(
                            Span("Avg Retention", cls="text-sm text-muted-foreground"),
                            Span(
                                f"{avg_retention * 100:.0f}%",
                                cls="text-2xl font-bold text-warning",
                            ),
                            P("Across mastered concepts", cls="text-xs text-muted-foreground"),
                            cls="p-4 text-center",
                        ),
                        cls="grid grid-cols-2 lg:grid-cols-4 gap-4 shadow rounded-lg w-full",
                    ),
                    cls="mb-6",
                ),
                cls="mb-8",
            ),
            # Detail Cards
            Card(
                H2("Learning Health", cls="text-xl font-semibold mb-4"),
                Div(
                    Div(
                        _render_stat_card(
                            "Active Paths", str(active_paths_count), "Learning paths in progress"
                        ),
                        _render_stat_card("Needs Review", str(needs_review), "Concepts to revisit"),
                        _render_stat_card(
                            "Struggling", str(struggling), "Concepts needing extra work"
                        ),
                        cls="grid grid-cols-1 md:grid-cols-3 gap-4",
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
    # LEARNING STEP DETAIL PAGE
    # ========================================================================

    @rt("/ls/{uid}")
    async def ls_detail_view(request, uid: str) -> Any:
        """Learning Step detail view with full context and relationships."""
        step_result = await lp_service.get_step(uid)

        if not step_result.is_error and step_result.value:
            step = step_result.value
            difficulty = _difficulty_label(step.difficulty_rating) if step.difficulty_rating else ""
            hours_text = f"{step.estimated_hours:.1f} hours" if step.estimated_hours else ""

            detail_content = Card(
                H1(step.title or f"Learning Step: {uid}", cls="text-2xl font-bold mb-4"),
                P(step.description or step.intent or "", cls="text-muted-foreground mb-4"),
                Div(
                    Badge(f"Sequence: {step.sequence}", variant=BadgeT.info, cls="mr-2")
                    if step.sequence
                    else None,
                    Badge(difficulty.title(), variant=BadgeT.primary, cls="mr-2")
                    if difficulty
                    else None,
                    Badge(hours_text, variant=BadgeT.secondary, cls="mr-2") if hours_text else None,
                    Badge(
                        f"Mastery: {step.current_mastery * 100:.0f}%",
                        variant=BadgeT.success if step.is_mastered() else BadgeT.outline,
                    ),
                    cls="flex flex-wrap gap-2 mb-4",
                ),
                ButtonLink("← Back to Pathways", href="/pathways", variant=ButtonT.ghost),
                cls="p-6 mb-4",
            )
        else:
            detail_content = Card(
                H1(f"Learning Step: {uid}", cls="text-2xl font-bold mb-4"),
                P("Learning step not found.", cls="text-muted-foreground mb-4"),
                ButtonLink("← Back to Pathways", href="/pathways", variant=ButtonT.ghost),
                cls="p-6 mb-4",
            )

        content = Div(
            detail_content,
            EntityRelationshipsSection(entity_uid=uid, entity_type="ls"),
            cls="container mx-auto p-6 max-w-4xl",
        )

        return await BasePage(
            content=content,
            title=f"LS: {uid}",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(ls_detail_view)

    # ========================================================================
    # LEARNING PATH DETAIL PAGE
    # ========================================================================

    @rt("/lp/{uid}")
    async def lp_detail_view(request, uid: str) -> Any:
        """Learning Path detail view with full context and relationships."""
        path_result = await lp_service.get_learning_path(uid)

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


def _render_stat_card(title: str, value: str, description: str) -> Any:
    """Render a simple stat card for analytics."""
    return Card(
        Div(
            P(title, cls="text-sm text-muted-foreground"),
            P(value, cls="text-2xl font-bold"),
            P(description, cls="text-xs text-muted-foreground"),
            cls="text-center p-4",
        ),
    )


__all__ = ["create_pathways_ui_routes"]
