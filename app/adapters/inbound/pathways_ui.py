"""
Pathways UI Routes
==================

Route handlers for structured learning pathway browsing and progress.
All pages use BasePage for consistent layout.
Wired to real LpService and UserProgressService.
"""

from typing import Any

from fasthtml.common import (
    H1,
    H3,
    A,
    Div,
    Header,
    Li,
    Ol,
    P,
    Span,
    Ul,
)

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from core.models.type_hints import EntityUID
from core.utils.logging import get_logger
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.feedback import Badge, BadgeT
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.pathways.components import (
    PathwaysUIComponents,
    difficulty_label,
    path_to_display_dict,
    render_step_browser_card,
)
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_inline_error
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import ButtonLink
from ui.ui_types import (
    ActivePathData,
    LearningStatsData,
)

logger = get_logger("skuel.ui.pathways")


def create_pathways_ui_routes(
    _app: Any, rt: Any, _primary_service: Any, orchestrator: Any = None
) -> list[Any]:
    """Create UI routes for pathway browsing and progress tracking."""

    routes: list[Any] = []

    @rt("/pathways")
    def pathways_dashboard(request) -> Any:
        """Main pathways dashboard — shell only, content loads via HTMX."""
        require_authenticated_user(request)
        content = Div(
            PageHeader(
                "Pathways Dashboard",
                subtitle="Track your learning journey and discover new knowledge",
            ),
            content_loading_placeholder("/pathways/content", "pathways-dashboard-content"),
            cls="container mx-auto px-4 py-6",
        )
        return BasePage(
            content=content,
            title="Pathways Dashboard",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(pathways_dashboard)

    @rt("/pathways/content")
    async def pathways_dashboard_content(request) -> Any:
        """HTMX fragment: pathways dashboard body."""
        user_uid = require_authenticated_user(request)
        summary_result = await orchestrator.get_dashboard_summary(user_uid)
        active_paths: list[ActivePathData] = []
        stats = LearningStatsData(
            total_hours=0.0,
            concepts_mastered=0,
            active_streak=0,
            completion_rate=0.0,
        )
        summary_error: str | None = None
        if summary_result.is_error:
            # G7: an all-zeros dashboard on a query failure reads as "you have
            # no paths" — render the error instead of a fabricated empty state.
            summary_error = summary_result.expect_error().message
        elif summary_result.value:
            active_paths = summary_result.value["active_paths"]
            stats = summary_result.value["stats"]
        if summary_error is not None:
            return Div(
                render_inline_error(f"Could not load your learning overview: {summary_error}"),
                cls="max-w-xl mx-auto py-8",
            )

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
                        cls=ButtonT.primary,
                    ),
                    ButtonLink(
                        "Browse Learning Steps",
                        href="/pathways/steps",
                        cls=ButtonT.secondary,
                    ),
                    cls="flex flex-wrap gap-3 justify-center",
                ),
                cls="text-center",
            )

        return Div(
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
                                label="Active Paths",
                                value=str(len(active_paths)),
                                color="primary",
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
            Card(
                CardHeader(
                    Div(
                        CardTitle("Active Learning Paths"),
                        Div(
                            ButtonLink(
                                "Browse Learning Paths",
                                href="/pathways/browse",
                                cls=ButtonT.primary,
                                size="sm",
                            ),
                            ButtonLink(
                                "Browse Learning Steps",
                                href="/pathways/steps",
                                cls=ButtonT.secondary,
                                size="sm",
                            ),
                            cls="flex flex-wrap gap-2",
                        ),
                        cls="flex justify-between items-center",
                    ),
                ),
                CardBody(paths_section),
                cls="mb-8",
            ),
            Card(
                CardHeader(CardTitle("Quick Actions")),
                CardBody(
                    Div(
                        ButtonLink(
                            "View Analytics",
                            href="/pathways/analytics",
                            cls=ButtonT.secondary,
                        ),
                        ButtonLink(
                            "Browse Paths",
                            href="/pathways/browse",
                            cls=ButtonT.secondary,
                        ),
                        ButtonLink(
                            "Browse Steps",
                            href="/pathways/steps",
                            cls=ButtonT.secondary,
                        ),
                        cls="flex flex-wrap gap-3",
                    ),
                ),
                cls="mb-8",
            ),
            id="pathways-dashboard-content",
        )

    routes.append(pathways_dashboard_content)

    @rt("/pathways/browse")
    def browse_learning_paths(request) -> Any:
        """Browse learning paths — shell only, content loads via HTMX."""
        content = Div(
            PageHeader(
                "Browse Learning Paths",
                subtitle="Discover structured learning paths to achieve your goals",
            ),
            content_loading_placeholder("/pathways/browse/content", "pathways-browse-content"),
            cls="container mx-auto px-4 py-6",
        )
        return BasePage(
            content=content,
            title="Browse Learning Paths",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(browse_learning_paths)

    @rt("/pathways/browse/content")
    async def browse_learning_paths_content(request) -> Any:
        """HTMX fragment: browse learning paths body."""
        available_paths: list[dict[str, Any]] = []
        paths_result = await orchestrator.list_all_paths(limit=50)
        if not paths_result.is_error and paths_result.value:
            available_paths.extend(path_to_display_dict(path) for path in paths_result.value)

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

        return Div(
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
            Div(grid_content, id="learning-paths-grid", cls="mb-8"),
            id="pathways-browse-content",
        )

    routes.append(browse_learning_paths_content)

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
                *[render_step_browser_card(s) for s in steps],
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

        return BasePage(
            content=content,
            title="Browse Learning Steps",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(browse_path_steps)

    @rt("/api/pathways/filter-paths", methods=["POST"])
    @csrf_protected
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
    def learning_path_detail(request, path_uid: str) -> Any:
        """Learning path detail — shell only, content loads via HTMX."""
        require_authenticated_user(request)
        content = Div(
            content_loading_placeholder(
                f"/pathways/path/{path_uid}/content", "pathways-path-content"
            ),
            cls="container mx-auto px-4 py-6",
        )
        return BasePage(
            content=content,
            title="Learning Path",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(learning_path_detail)

    @rt("/pathways/path/{path_uid}/content")
    async def learning_path_detail_content(request, path_uid: str) -> Any:
        """HTMX fragment: learning path detail body."""
        user_uid = require_authenticated_user(request)
        detail_result = await orchestrator.get_path_detail_progress(path_uid, user_uid)
        if detail_result.is_error:
            return Div(
                Card(
                    H1("Learning Path Not Found", cls="text-2xl font-bold mb-4"),
                    P(
                        f"Could not find learning path: {path_uid}",
                        cls="text-muted-foreground mb-4",
                    ),
                    Button(
                        "Back to Pathways",
                        hx_get="/pathways",
                        hx_target="body",
                        cls=ButtonT.ghost,
                    ),
                    cls="p-6",
                ),
                id="pathways-path-content",
            )

        detail = detail_result.value
        path = detail["path"]
        steps = detail["steps"]
        total_steps = len(steps)
        mastered_uids = detail["mastered_uids"]
        is_enrolled = detail["is_enrolled"]
        progress = detail["progress"]

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

        outcomes = path.outcomes or ()
        difficulty = difficulty_label(path.difficulty_rating)

        return Div(
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
                        cls=ButtonT.primary,
                        size="lg",
                        hx_post=f"/api/pathways/enroll/{path_uid}",
                        hx_target="#main-content",
                    ),
                    cls="flex-shrink-0",
                ),
                cls="flex items-start justify-between mb-8",
            ),
            Card(
                CardHeader(CardTitle("Curriculum")),
                CardBody(steps_section),
                cls="mb-8",
            ),
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
            id="pathways-path-content",
        )

    routes.append(learning_path_detail_content)

    @rt("/pathways/analytics")
    def learning_analytics(request) -> Any:
        """Learning analytics dashboard — shell only, content loads via HTMX."""
        require_authenticated_user(request)
        content = Div(
            PageHeader("Learning Analytics", subtitle="Insights into your learning journey"),
            content_loading_placeholder(
                "/pathways/analytics/content", "pathways-analytics-content"
            ),
            cls="container mx-auto px-4 py-6",
        )
        return BasePage(
            content=content,
            title="Learning Analytics",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(learning_analytics)

    @rt("/pathways/analytics/content")
    async def learning_analytics_content(request) -> Any:
        """HTMX fragment: learning analytics body."""
        user_uid = require_authenticated_user(request)
        analytics_result = await orchestrator.get_learning_analytics(user_uid)
        analytics = analytics_result.value if not analytics_result.is_error else {}
        concepts_mastered = analytics.get("concepts_mastered", 0)
        in_progress = analytics.get("in_progress", 0)
        needs_review = analytics.get("needs_review", 0)
        struggling = analytics.get("struggling", 0)
        active_paths_count = analytics.get("active_paths_count", 0)
        avg_retention = analytics.get("avg_retention", 0.0)

        return Div(
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
            id="pathways-analytics-content",
        )

    routes.append(learning_analytics_content)

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
            difficulty = difficulty_label(path.difficulty_rating)
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
                    H3("Steps", cls="font-semibold mb-2"),
                    # metadata["steps"] arrives sorted by the HAS_STEP sequence
                    # property, so this list renders in authored path order.
                    Ol(
                        *[
                            Li(
                                A(
                                    step.title or step.uid,
                                    href=f"/explore/ps/{step.uid}",
                                    cls="text-primary hover:underline",
                                )
                            )
                            for step in steps
                        ],
                        cls="list-decimal ml-4 space-y-1",
                    ),
                    cls="mb-4",
                )
                if steps
                else None,
                Div(
                    H3("Outcomes", cls="font-semibold mb-2"),
                    Ul(*[Li(o) for o in outcomes], cls="list-disc ml-4"),
                    cls="mb-4",
                )
                if outcomes
                else None,
                ButtonLink("← Back to Pathways", href="/pathways", cls=ButtonT.ghost),
                cls="p-6 mb-4",
            )
        else:
            detail_content = Card(
                H1(f"Learning Path: {uid}", cls="text-2xl font-bold mb-4"),
                P("Learning path not found.", cls="text-muted-foreground mb-4"),
                ButtonLink("← Back to Pathways", href="/pathways", cls=ButtonT.ghost),
                cls="p-6 mb-4",
            )

        content = Div(
            detail_content,
            EntityRelationshipsSection(entity_uid=EntityUID(uid), entity_type="lp"),
            cls="container mx-auto p-6 max-w-4xl",
        )

        return BasePage(
            content=content,
            title=f"LP: {uid}",
            page_type=PageType.STANDARD,
            request=request,
            active_page="pathways",
        )

    routes.append(lp_detail_view)

    logger.info(f"Pathways UI routes registered: {len(routes)} endpoints")
    return routes
