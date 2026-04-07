"""
User Profile UI Routes - Profile Hub Page (MOC Pattern)
=======================================================

Routes for the user profile hub page and related endpoints.

Key Routes:
- GET /profile - Profile hub (grouped card grid with links)
- GET /profile/settings - 301 redirect to /settings
- GET /profile/shared - Shared content view

Architecture:
- /profile is a hub page with grouped cards (no sidebar)
- Uses BasePage(STANDARD) — the MOC pattern
- Uses UserContext (~250 fields) as the authoritative source for user state

See: /docs/design-principles/HUB_PAGES.md
"""

__version__ = "5.0"  # Hub page (MOC pattern) — no sidebar

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, Request

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from services_bootstrap import Services

from adapters.inbound.auth import require_authenticated_user
from core.services.user.unified_user_context import UserContext
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.cards import Card, CardBody
from ui.enum_helpers import get_submission_status_badge_class
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.patterns.page_header import PageHeader
from ui.profile.domain_stats_config import (
    DOMAIN_STATS_CONFIG,
    knowledge_active,
    knowledge_count,
    knowledge_status,
    learning_paths_active,
    learning_paths_count,
    learning_paths_status,
    path_steps_active,
    path_steps_count,
    path_steps_status,
)
from ui.profile.overview import render_domain_card_preview

logger = get_logger("skuel.routes.user_profile")


# ============================================================================
# ERROR HANDLING HELPERS
# ============================================================================


async def error_page(
    message: str,
    status_code: int,
    user_display_name: str = "User",
    request: Any = None,
) -> Any:
    """
    Unified error page for profile routes.

    One path forward: Clear errors with no silent fallbacks.

    Args:
        message: Error message to display
        status_code: HTTP status code (404, 500, etc.)
        user_display_name: User's display name for page header
        request: Optional request for navbar auth detection

    Returns:
        Error page with consistent styling
    """
    from ui.patterns.error_banner import render_error_banner

    content = Div(
        render_error_banner(f"Error {status_code}", technical_details=message),
        cls="flex flex-col items-center justify-center min-h-[400px] p-8",
    )

    return await BasePage(
        content=content,
        title=f"Error {status_code}",
        request=request,
        active_page="profile",
    )


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


@dataclass
class ProfileParams:
    """Typed parameters for profile page deep linking."""

    focus: str | None


def parse_profile_params(request: Request) -> ProfileParams:
    """
    Extract profile parameters from request query params.

    Args:
        request: Starlette request object

    Returns:
        Typed ProfileParams with defaults applied
    """
    return ProfileParams(
        focus=request.query_params.get("focus"),
    )


# ============================================================================
# ROUTE SETUP
# ============================================================================


def setup_user_profile_routes(rt: Any, services: "Services") -> None:
    """
    Setup user profile routes.

    Args:
        rt: FastHTML route decorator
        services: Services container with all backends
    """

    if services.user_service is None:
        raise RuntimeError("UserService is required for profile routes")
    user_service = services.user_service

    if profile_orchestrator is None:
        raise RuntimeError("ProfileOrchestrator is required for profile routes")
    profile_orchestrator = profile_orchestrator

    # ========================================================================
    # SETTINGS REDIRECT — moved to /settings (2026-04-06)
    # ========================================================================

    @rt("/profile/settings")
    async def profile_settings_redirect(request: Request) -> Any:
        """301 redirect: settings moved to /settings."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/settings", status_code=301)

    # ========================================================================
    # PROFILE HUB ROUTES - Sidebar Navigation with Domain Views
    # ========================================================================

    async def _get_context(
        user_uid: UserUID,
    ) -> UserContext:
        """
        Get rich UserContext — single call, includes user identity + role.

        Args:
            user_uid: Authenticated user's UID

        Returns:
            UserContext with ~250 fields including user_role, display_name, username

        Raises:
            ValueError: If context cannot be loaded
        """
        context_result = await user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            raise ValueError(f"Failed to load context for user: {user_uid}")
        return context_result.value

    @rt("/profile")
    async def profile_redirect(request: Request) -> Any:
        """301 redirect: profile moved to /tasks."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/tasks", status_code=301)

    @rt("/api/profile/{slug}/preview")
    async def domain_card_preview(request: Request, slug: str) -> Any:
        """
        HTMX fragment: top 3 active items for a domain block, sorted by priority.

        Called by the Activity Domain blocks on the /profile page via
        hx-trigger="load". Returns a row of 3 cards (priority dot + title)
        or an empty-state message.

        Requires authentication.
        """
        user_uid = require_authenticated_user(request)

        result = await profile_orchestrator.get_domain_preview_items(user_uid, slug)

        if result.is_error:
            from fasthtml.common import P as Para

            logger.warning(
                "Failed to load domain card preview",
                extra={"slug": slug, "user_uid": user_uid, "error": str(result.error)},
            )
            return Para("Unable to load items", cls="text-sm text-muted-foreground py-2")

        return render_domain_card_preview(result.value, slug)

    # ------------------------------------------------------------------
    # HTMX report summary fragments for profile hub
    # ------------------------------------------------------------------

    @rt("/api/profile/reports/exercise-summary")
    async def exercise_reports_summary(request: Request) -> Any:
        """HTMX fragment: 5 most recent exercise reports for the profile hub."""
        from fasthtml.common import A, P, Span

        user_uid = require_authenticated_user(request)

        result = await profile_orchestrator.get_recent_exercise_reports(user_uid, limit=5)
        if result.is_error:
            return P("Unable to load reports", cls="text-sm text-muted-foreground py-2")

        reports = result.value or []
        if not reports:
            return P(
                "No exercise reports yet.",
                cls="text-sm text-muted-foreground py-3 px-3",
            )

        rows: list[Any] = []
        for report in reports:
            title = getattr(report, "title", None) or "Untitled Report"
            uid = getattr(report, "uid", "")
            created = getattr(report, "created_at", None)
            date_str = created.strftime("%b %d") if created else ""

            rows.append(
                Div(
                    A(
                        title,
                        href=f"/exercise-reports?uid={uid}",
                        cls="text-sm font-medium text-foreground hover:text-primary truncate",
                    ),
                    Span(
                        date_str,
                        cls="text-[10px] text-muted-foreground whitespace-nowrap ml-auto",
                    ),
                    cls="flex items-center gap-2 py-2 px-3 rounded-lg hover:bg-muted/50",
                )
            )
        return Div(*rows)

    @rt("/api/profile/reports/activity-summary")
    async def activity_reports_summary(request: Request) -> Any:
        """HTMX fragment: 5 most recent activity reports for the profile hub."""
        from fasthtml.common import A, P, Span

        user_uid = require_authenticated_user(request)

        result = await profile_orchestrator.get_recent_activity_reports(user_uid, limit=5)
        if result.is_error:
            return P("Unable to load reports", cls="text-sm text-muted-foreground py-2")

        reports = result.value or []
        if not reports:
            return P(
                "No activity reports yet.",
                cls="text-sm text-muted-foreground py-3 px-3",
            )

        rows: list[Any] = []
        for report in reports:
            title = getattr(report, "title", None) or "Activity Report"
            uid = getattr(report, "uid", "")
            created = getattr(report, "created_at", None)
            date_str = created.strftime("%b %d") if created else ""
            time_period = getattr(report, "time_period", None)

            badges: list[Any] = []
            if time_period:
                badges.append(
                    Span(
                        time_period,
                        cls="text-[10px] font-medium bg-muted text-muted-foreground px-1.5 py-0.5 rounded",
                    )
                )
            badges.append(
                Span(
                    date_str,
                    cls="text-[10px] text-muted-foreground whitespace-nowrap",
                ),
            )

            rows.append(
                Div(
                    A(
                        title,
                        href=f"/activity-reports/detail?uid={uid}",
                        cls="text-sm font-medium text-foreground hover:text-primary truncate",
                    ),
                    *badges,
                    cls="flex items-center gap-2 py-2 px-3 rounded-lg hover:bg-muted/50 ml-auto",
                )
            )
        return Div(*rows)

    # ------------------------------------------------------------------
    # HTMX submission tab fragments for profile hub
    # ------------------------------------------------------------------

    @rt("/api/profile/submissions/submit-form")
    async def profile_submit_form(request: Request) -> Any:
        """HTMX fragment: upload form for the Submit tab on the profile hub."""
        from fasthtml.common import Div

        try:
            user_uid = require_authenticated_user(request)

            assigned_exercises: list[Any] = []
            exercises_result = await profile_orchestrator.get_assigned_exercises(user_uid)
            if not exercises_result.is_error and exercises_result.value:
                assigned_exercises = exercises_result.value

            from ui.submissions.forms import render_upload_form, upload_form_script

            return Div(
                render_upload_form(assigned_exercises),
                upload_form_script(),
            )
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading submit form: {e}", exc_info=True)
            from ui.patterns.error_banner import render_error_banner

            return Div(render_error_banner("Failed to load submit form", str(e)))

    @rt("/api/profile/submissions/report-form")
    async def profile_report_form(request: Request) -> Any:
        """HTMX fragment: activity report request form for the Request Report tab."""
        from fasthtml.common import Div

        try:
            require_authenticated_user(request)
            from ui.patterns.generate_report import (
                render_activity_report_request_card,
                render_recent_reports_section,
            )

            return Div(render_activity_report_request_card(), render_recent_reports_section())
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading report form: {e}", exc_info=True)
            from ui.patterns.error_banner import render_error_banner

            return Div(render_error_banner("Failed to load report form", str(e)))

    @rt("/api/sidebar/badges")
    async def sidebar_badges(request: Request) -> Any:
        """HTMX OOB-swap endpoint: async-loaded count + status badges for sidebar items.

        Returns Span elements with hx-swap-oob="true" that replace the
        `sidebar-badge-{slug}` placeholders rendered by `_default_item_renderer`.
        """
        from fasthtml.common import Span

        from ui.profile.badges import CountBadge, HealthIndicator

        user_uid = require_authenticated_user(request)

        try:
            context = await _get_context(user_uid)
        except ValueError:
            # Degrade silently — badges are enhancement, not critical
            return Div()

        fragments: list[Any] = []

        # Activity domain badges
        for slug, config in DOMAIN_STATS_CONFIG.items():
            count = config.count_fn(context)
            active = config.active_fn(context)
            status_args = config.status_args_fn(context)
            status = config.status_fn(*status_args)

            fragments.append(
                Span(
                    CountBadge(count, active),
                    HealthIndicator(status),
                    id=f"sidebar-badge-{slug}",
                    hx_swap_oob="true",
                    cls="flex items-center gap-1",
                )
            )

        # Curriculum badges
        curriculum_configs: list[tuple[str, int, int, str]] = [
            (
                "knowledge",
                knowledge_count(context),
                knowledge_active(context),
                knowledge_status(context),
            ),
            (
                "path-steps",
                path_steps_count(context),
                path_steps_active(context),
                path_steps_status(context),
            ),
            (
                "learning-paths",
                learning_paths_count(context),
                learning_paths_active(context),
                learning_paths_status(context),
            ),
        ]
        for slug, count, active, status in curriculum_configs:
            fragments.append(
                Span(
                    CountBadge(count, active),
                    HealthIndicator(status),
                    id=f"sidebar-badge-{slug}",
                    hx_swap_oob="true",
                    cls="flex items-center gap-1",
                )
            )

        return Div(*fragments)

    @rt("/profile/shared")
    async def profile_shared(request: Request) -> Any:
        """
        Shared With Me tab - shows assignments and events shared with current user.

        Assignments only. Will include events.
        """
        user_uid = require_authenticated_user(request)

        # Fetch shared reports
        from fasthtml.common import H4, Div, P

        from ui.buttons import Button, ButtonLink, ButtonT
        from ui.layout import Size

        shared_reports = []
        reports_result = await profile_orchestrator.get_shared_with_me_items(
            user_uid=user_uid,
            limit=50,
        )
        if not reports_result.is_error:
            shared_reports = reports_result.value

        # Build shared content view
        def shared_content_card(report: Any) -> Any:
            """Render a shared report card."""
            return Card(
                CardBody(
                    # Header with filename and status
                    Div(
                        H4(report.original_filename, cls="text-sm"),
                        Badge(
                            report.status,
                            variant=None,
                            size=Size.sm,
                            cls=get_submission_status_badge_class(report.status),
                        ),
                        cls="flex items-center justify-between",
                    ),
                    # Metadata
                    Div(
                        P(
                            f"Shared by: {report.user_uid}",
                            cls="text-xs text-muted-foreground mb-1",
                        ),
                        P(
                            f"Type: {report.report_type}",
                            cls="text-xs text-muted-foreground mb-0",
                        ),
                        cls="mt-2",
                    ),
                    # Actions
                    Div(
                        ButtonLink(
                            "View",
                            href=f"/gradebook/{report.uid}",
                            variant=ButtonT.primary,
                            size=Size.xs,
                        ),
                        cls="mt-3",
                    ),
                    cls="p-4",
                ),
                cls="bg-muted shadow-sm hover:shadow-md transition-shadow",
            )

        # Content view
        content = Div(
            PageHeader(
                "📥 Shared With Me",
                subtitle="Reports and events shared with you by teachers, peers, and mentors.",
            ),
            # Filter tabs
            Div(
                Button("All", variant=ButtonT.ghost, size=Size.sm, disabled=True),
                Button("Reports", variant=ButtonT.primary, size=Size.sm),
                Button("Events", variant=ButtonT.ghost, size=Size.sm, disabled=True),
                cls="flex gap-2 mb-6",
            ),
            # Shared content grid
            (
                Div(
                    *[shared_content_card(a) for a in shared_reports],
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                )
                if shared_reports
                else Card(
                    P(
                        "No content shared with you yet.",
                        cls="text-center text-muted-foreground py-12",
                    ),
                    cls="bg-muted p-8",
                )
            ),
        )

        return await BasePage(
            content=content,
            title="Shared With Me",
            request=request,
            active_page="profile",
        )

    async def _build_knowledge_view(context: UserContext, user_uid: UserUID) -> Any:
        """Build the Knowledge domain view with all KUs and user status.

        Queries Neo4j for all Entity nodes with per-user VIEWED/BOOKMARKED/MASTERED relationships.
        """
        from fasthtml.common import H4, A, Div, P, Span

        # Query all KUs with user's relationship status via orchestrator
        all_kus: list[dict] = []
        result = await profile_orchestrator.get_knowledge_status(user_uid)
        if result.is_error:
            logger.warning(f"Failed to fetch KUs: {result.expect_error()}")
        else:
            all_kus = result.value or []

        # Build KU cards
        def entity_card(ku: dict) -> Any:
            """Render a knowledge entity card with status badges."""
            ku_title = ku.get("title") or ku.get("uid") or "Untitled"
            ku_domain = ku.get("domain", "")
            is_bookmarked = ku.get("bookmarked", False)
            is_mastered = ku.get("mastered", False)
            is_studying = ku.get("studying", False)

            badges = []
            if is_mastered:
                badges.append(Badge("Understood", variant=BadgeT.success, size=Size.xs))
            elif is_studying:
                badges.append(Badge("Studying", variant=BadgeT.warning, size=Size.xs))
            if is_bookmarked:
                badges.append(Badge("Bookmarked", variant=BadgeT.info, size=Size.xs))

            return A(
                Card(
                    CardBody(
                        H4(ku_title, cls="text-sm"),
                        (
                            P(ku_domain, cls="text-xs text-muted-foreground mt-1")
                            if ku_domain
                            else None
                        ),
                        Div(*badges, cls="flex gap-1 mt-2") if badges else None,
                        cls="p-4",
                    ),
                    cls="bg-muted shadow-sm hover:shadow-md transition-shadow",
                ),
                href=f"/explore/ku/{ku['uid']}",
            )

        ku_content = (
            Div(
                Badge(
                    f"{len(all_kus)} knowledge units",
                    variant=BadgeT.ghost,
                    cls="mb-4",
                ),
                Div(
                    *[entity_card(ku) for ku in all_kus],
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                ),
            )
            if all_kus
            else Card(
                P(
                    "No knowledge units available yet.",
                    cls="text-center text-muted-foreground py-12",
                ),
                cls="bg-muted p-8",
            )
        )

        return Div(
            PageHeader(
                "Knowledge Units",
                subtitle="All knowledge units in the curriculum. Track your learning progress.",
            ),
            # Quick stats row
            Div(
                Div(
                    Span(
                        str(len(context.mastered_knowledge_uids)),
                        cls="text-xl font-bold text-success",
                    ),
                    Span(" mastered", cls="text-sm text-muted-foreground"),
                    cls="flex items-baseline gap-1",
                ),
                Div(
                    Span(
                        str(len(context.in_progress_knowledge_uids)),
                        cls="text-xl font-bold text-warning",
                    ),
                    Span(" in progress", cls="text-sm text-muted-foreground"),
                    cls="flex items-baseline gap-1",
                ),
                Div(
                    Span(str(len(context.ready_to_learn_uids)), cls="text-xl font-bold text-info"),
                    Span(" ready", cls="text-sm text-muted-foreground"),
                    cls="flex items-baseline gap-1",
                ),
                cls="flex gap-6 mb-6",
            ),
            ku_content,
            A(
                "Browse All Knowledge →",
                href="/knowledge",
                cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
            ),
        )

    # ========================================================================
    # CHART API ROUTES - , Task 2: Intelligence Data Visualization
    # ========================================================================

    @rt("/api/profile/charts/alignment")
    async def alignment_radar_chart(request: Request):
        """
        Chart.js radar chart config for life path alignment.

        Returns JSON with 5 dimensions: knowledge, activity, goal, principle, momentum.
        Scores range from 0.0 to 1.0.
        """
        user_uid = require_authenticated_user(request)

        # Get intelligence data for alignment scores
        try:
            context = await _get_context(user_uid)
        except ValueError as e:
            from starlette.responses import JSONResponse

            return JSONResponse({"error": str(e)}, status_code=500)

        def _empty_alignment_chart(title_suffix: str) -> Any:
            """Return an empty radar chart with zeroed data."""
            from starlette.responses import JSONResponse

            return JSONResponse(
                {
                    "type": "radar",
                    "data": {
                        "labels": ["Knowledge", "Activity", "Goals", "Principles", "Momentum"],
                        "datasets": [
                            {
                                "label": "Life Path Alignment",
                                "data": [0, 0, 0, 0, 0],
                                "backgroundColor": "rgba(59, 130, 246, 0.2)",
                                "borderColor": "rgba(59, 130, 246, 1)",
                                "borderWidth": 2,
                            }
                        ],
                    },
                    "options": {
                        "scales": {
                            "r": {
                                "min": 0,
                                "max": 1,
                                "ticks": {"stepSize": 0.2},
                            }
                        },
                        "plugins": {
                            "title": {
                                "display": True,
                                "text": f"Life Path Alignment ({title_suffix})",
                            }
                        },
                    },
                }
            )

        intel_result = await profile_orchestrator.get_intelligence_data(context)
        if intel_result.is_error or intel_result.value is None:
            return _empty_alignment_chart("No Data")

        intel_data = intel_result.value
        alignment = intel_data.get("alignment")

        if alignment is None:
            return _empty_alignment_chart("Unavailable")

        # Extract alignment scores (0.0-1.0)
        knowledge_score = getattr(alignment, "knowledge_score", 0.0)
        activity_score = getattr(alignment, "activity_score", 0.0)
        goal_score = getattr(alignment, "goal_score", 0.0)
        principle_score = getattr(alignment, "principle_score", 0.0)
        momentum_score = getattr(alignment, "momentum_score", 0.0)

        # Build Chart.js config
        from starlette.responses import JSONResponse

        return JSONResponse(
            {
                "type": "radar",
                "data": {
                    "labels": ["Knowledge", "Activity", "Goals", "Principles", "Momentum"],
                    "datasets": [
                        {
                            "label": "Your Alignment",
                            "data": [
                                knowledge_score,
                                activity_score,
                                goal_score,
                                principle_score,
                                momentum_score,
                            ],
                            "backgroundColor": "rgba(59, 130, 246, 0.2)",  # blue
                            "borderColor": "rgba(59, 130, 246, 1)",
                            "borderWidth": 2,
                            "pointBackgroundColor": "rgba(59, 130, 246, 1)",
                            "pointBorderColor": "#fff",
                            "pointHoverBackgroundColor": "#fff",
                            "pointHoverBorderColor": "rgba(59, 130, 246, 1)",
                        }
                    ],
                },
                "options": {
                    "scales": {
                        "r": {
                            "min": 0,
                            "max": 1,
                            "ticks": {
                                "stepSize": 0.2,
                                "callback": "function(value) { return (value * 100) + '%'; }",
                            },
                        }
                    },
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Life Path Alignment - 5 Dimensions",
                            "font": {"size": 16},
                        },
                        "legend": {"display": False},
                    },
                },
            }
        )

    @rt("/api/profile/charts/domain-progress")
    async def domain_progress_timeline(request: Request):
        """
        Chart.js line chart showing activity across domains over 30 days.

        Returns completion counts for tasks, events, habits, goals.
        """
        user_uid = require_authenticated_user(request)

        try:
            context = await _get_context(user_uid)
        except ValueError as e:
            from starlette.responses import JSONResponse

            return JSONResponse({"error": str(e)}, status_code=500)

        # Generate 30-day timeline (mock data for now - would come from analytics)
        # In production, this would query completion events from Neo4j
        from datetime import date, timedelta

        today = date.today()
        dates = [(today - timedelta(days=i)).strftime("%m/%d") for i in range(29, -1, -1)]

        # Mock data - in production, query actual completion counts per day
        # For now, use current context to generate plausible trends
        tasks_completed_recent = len(list(context.completed_task_uids)[:30])
        habits_active = len(context.active_habit_uids)

        # Generate simple mock trends (would be real data in production)
        import random

        random.seed(hash(user_uid))  # Consistent per user
        tasks_data = [random.randint(0, min(5, tasks_completed_recent)) for _ in range(30)]
        habits_data = [random.randint(0, min(3, habits_active)) for _ in range(30)]
        goals_data = [1 if i % 7 == 0 else 0 for i in range(30)]  # Weekly goal updates

        from starlette.responses import JSONResponse

        return JSONResponse(
            {
                "type": "line",
                "data": {
                    "labels": dates,
                    "datasets": [
                        {
                            "label": "Tasks Completed",
                            "data": tasks_data,
                            "borderColor": "rgba(34, 197, 94, 1)",  # green
                            "backgroundColor": "rgba(34, 197, 94, 0.1)",
                            "tension": 0.4,
                            "fill": True,
                        },
                        {
                            "label": "Habits Checked",
                            "data": habits_data,
                            "borderColor": "rgba(59, 130, 246, 1)",  # blue
                            "backgroundColor": "rgba(59, 130, 246, 0.1)",
                            "tension": 0.4,
                            "fill": True,
                        },
                        {
                            "label": "Goal Updates",
                            "data": goals_data,
                            "borderColor": "rgba(168, 85, 247, 1)",  # purple
                            "backgroundColor": "rgba(168, 85, 247, 0.1)",
                            "tension": 0.4,
                            "fill": True,
                        },
                    ],
                },
                "options": {
                    "responsive": True,
                    "interaction": {"mode": "index", "intersect": False},
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "30-Day Activity Overview",
                            "font": {"size": 16},
                        },
                        "legend": {"position": "bottom"},
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True,
                            "ticks": {"stepSize": 1},
                            "title": {"display": True, "text": "Count"},
                        },
                        "x": {"title": {"display": True, "text": "Date"}},
                    },
                },
            }
        )

    @rt("/api/profile/intelligence-section")
    async def intelligence_section_htmx(request: Request):
        """
        HTMX endpoint for loading intelligence section with skeleton loading state.

        , Task 3: Prevents blank screen during 2-3s intelligence load.
        """
        user_uid = require_authenticated_user(request)

        # Get user and context
        try:
            context = await _get_context(user_uid)
        except ValueError as e:
            from ui.patterns.empty_state import EmptyState

            return EmptyState(
                title="Error Loading Intelligence",
                description=str(e),
                icon="⚠️",
            )

        # Get intelligence data - may return None for basic mode
        intel_result = await profile_orchestrator.get_intelligence_data(context)
        if intel_result.is_error:
            from ui.patterns.empty_state import EmptyState

            return EmptyState(
                title="Intelligence Unavailable",
                description="Failed to load intelligence features.",
                icon="⚠️",
            )

        intel_data = intel_result.value

        if intel_data is None:
            # Basic mode - return unavailable card
            from ui.profile.overview import _intelligence_unavailable_card

            return _intelligence_unavailable_card()

        # Full mode - return intelligence section with partial error support
        from ui.patterns.error_banner import render_error_banner
        from ui.profile.overview import (
            _alignment_breakdown,
            _chart_visualizations_section,
            _daily_work_plan_card,
            _path_steps_card,
            _synergies_card,
        )

        partial_errors = intel_data.get("partial_errors", [])
        sections: list[Any] = [_chart_visualizations_section()]

        if partial_errors:
            sections.append(
                render_error_banner(
                    "Some intelligence features are temporarily unavailable",
                    severity="warning",
                )
            )

        if intel_data.get("alignment") is not None:
            sections.append(_alignment_breakdown(intel_data["alignment"]))
        if intel_data.get("daily_plan") is not None:
            sections.append(_daily_work_plan_card(intel_data["daily_plan"]))
        if intel_data.get("synergies") is not None:
            sections.append(_synergies_card(intel_data["synergies"]))
        if intel_data.get("path_steps") is not None:
            sections.append(_path_steps_card(intel_data["path_steps"]))

        return Div(*sections)

    logger.info("✅ Profile routes registered (/profile, /profile/{domain})")
    logger.info("✅ Profile chart API routes registered (/api/profile/charts/*)")
    logger.info(
        "✅ Profile HTMX intelligence endpoint registered (/api/profile/intelligence-section)"
    )


__all__ = ["setup_user_profile_routes"]
