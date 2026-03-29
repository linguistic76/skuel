"""
User Profile UI Routes - Profile Hub Page (MOC Pattern)
=======================================================

Routes for the user profile hub page and related endpoints.

Key Routes:
- GET /profile - Profile hub (grouped card grid with links)
- GET /profile/{domain} - Legacy redirects to domain routes
- GET /profile/settings - User settings/preferences
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
from adapters.inbound.form_helpers import safe_form_bool, safe_form_int, safe_form_string
from core.models.enums import Priority
from core.ports import get_enum_value
from core.services.user.unified_user_context import UserContext
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.cards import Card, CardBody
from ui.enum_helpers import get_submission_status_badge_class
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.profile.domain_stats_config import (
    DOMAIN_STATS_CONFIG,
    knowledge_active,
    knowledge_count,
    knowledge_status,
    learning_paths_active,
    learning_paths_count,
    learning_paths_status,
    learning_steps_active,
    learning_steps_count,
    learning_steps_status,
)
from ui.profile.overview import render_domain_card_preview

logger = get_logger("skuel.routes.user_profile")

_PREVIEW_PRIORITY_ORDER = {
    Priority.CRITICAL: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}


def _preview_priority_sort_key(item: Any) -> int:
    """Sort key for domain card preview items by priority (CRITICAL first).

    Coerces string priority values to Priority enum before lookup so that
    service backends returning plain strings sort correctly.
    """
    raw = getattr(item, "priority", Priority.LOW)
    if not isinstance(raw, Priority):
        try:
            raw = Priority(str(raw).lower())
        except ValueError:
            raw = Priority.LOW
    return _PREVIEW_PRIORITY_ORDER.get(raw, 4)


# Valid Activity Domain slugs for the preview endpoint
_PREVIEW_VALID_SLUGS = frozenset({"tasks", "goals", "habits", "events", "choices", "principles"})


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

    # ========================================================================
    # SETTINGS ROUTES
    # ========================================================================

    @rt("/profile/settings")
    async def user_settings(request: Request) -> Any:
        """
        User settings and preferences page.
        Requires authentication.

        One path forward: Get user from service or fail with clear error.
        """
        user_uid = require_authenticated_user(request)

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error:
            logger.error("Failed to load user for settings", extra={"user_uid": user_uid})
            return await error_page("User not found", 404, request=request)
        user = user_result.value
        if user is None:
            return await error_page("User not found", 404, request=request)

        # Extract preferences as dict
        prefs_dict = {}
        if user.preferences is not None:
            prefs = user.preferences
            prefs_dict = {
                "learning_level": get_enum_value(prefs.learning_level),
                "preferred_modalities": prefs.preferred_modalities,
                "preferred_subjects": prefs.preferred_subjects,
                "preferred_time_of_day": get_enum_value(prefs.preferred_time_of_day),
                "available_minutes_daily": prefs.available_minutes_daily,
                "enable_reminders": prefs.enable_reminders,
                "reminder_minutes_before": prefs.reminder_minutes_before,
                "daily_summary_time": prefs.daily_summary_time,
                "theme": prefs.theme,
                "language": prefs.language,
                "timezone": prefs.timezone,
                "weekly_task_goal": prefs.weekly_task_goal,
                "daily_habit_goal": prefs.daily_habit_goal,
                "monthly_learning_hours": prefs.monthly_learning_hours,
            }

        from ui.profile.preferences import UserPreferencesComponents

        content = UserPreferencesComponents.render_preferences_editor(prefs_dict)

        return await BasePage(
            content,
            title="Settings",
            request=request,
            active_page="profile/hub",
        )

    @rt("/profile/settings/save")
    async def save_user_settings(request: Request) -> Any:
        """
        Save user preferences from form submission.
        Requires authentication.
        """
        user_uid = require_authenticated_user(request)

        # Parse form data
        form_data = await request.form()

        # Build modalities list from checkboxes
        modalities = []
        if form_data.get("modality_video"):
            modalities.append("video")
        if form_data.get("modality_reading"):
            modalities.append("reading")
        if form_data.get("modality_interactive"):
            modalities.append("interactive")
        if form_data.get("modality_audio"):
            modalities.append("audio")

        # Create preferences update (use safe parsing to prevent crashes)
        preferences_update = {
            "learning_level": safe_form_string(form_data.get("learning_level"), "intermediate"),
            "preferred_modalities": modalities,
            "preferred_time_of_day": safe_form_string(
                form_data.get("preferred_time_of_day"), "anytime"
            ),
            "available_minutes_daily": safe_form_int(form_data.get("available_minutes_daily"), 60),
            "enable_reminders": safe_form_bool(form_data.get("enable_reminders"), False),
            "reminder_minutes_before": safe_form_int(form_data.get("reminder_minutes_before"), 15),
            "daily_summary_time": safe_form_string(form_data.get("daily_summary_time"), "09:00"),
            "theme": safe_form_string(form_data.get("theme"), "light"),
            "language": safe_form_string(form_data.get("language"), "en"),
            "timezone": safe_form_string(form_data.get("timezone"), "UTC"),
            "weekly_task_goal": safe_form_int(form_data.get("weekly_task_goal"), 10),
            "daily_habit_goal": safe_form_int(form_data.get("daily_habit_goal"), 3),
            "monthly_learning_hours": safe_form_int(form_data.get("monthly_learning_hours"), 20),
        }

        # Update user preferences - ONE PATH (no fallback)
        update_result = await user_service.update_preferences(user_uid, preferences_update)

        if update_result.is_error:
            # Log detailed error for debugging (don't leak to user)
            logger.error(
                "Failed to save user preferences",
                extra={
                    "user_uid": user_uid,
                    "error": str(update_result.error),
                },
            )
            from fasthtml.common import P

            # Return user-safe error message
            return Div(
                P("Failed to save preferences. Please try again.", cls="text-error"),
                P(
                    "If this problem persists, contact support.",
                    cls="text-sm text-muted-foreground mt-2",
                ),
                cls="p-4",
            )

        from fasthtml.common import Script

        from ui.profile.preferences import UserPreferencesComponents

        # Persist theme to localStorage so it applies on all pages
        saved_theme = preferences_update.get("theme", "light")
        dark_toggle = (
            "document.documentElement.classList.add('dark')"
            if saved_theme == "dark"
            else "document.documentElement.classList.remove('dark')"
        )
        theme_script = Script(
            f"localStorage.setItem('skuel-theme', '{saved_theme}');{dark_toggle};"
        )

        return Div(
            UserPreferencesComponents.render_preferences_saved_message(),
            theme_script,
        )

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

    async def _get_intelligence_data(
        context: UserContext,
    ) -> "Result[dict[str, Any] | None]":
        """
        Get intelligence data for OverviewView if available.

        Calls UserContextIntelligence methods independently to get:
        - Daily work plan (THE flagship)
        - Life path alignment (5 dimensions)
        - Cross-domain synergies
        - Optimal learning steps

        Each call is independent — a failure in one does not block the others.
        Partial failures are tracked in ``partial_errors`` so the UI can show
        a warning banner while still rendering the sections that succeeded.

        Returns:
            - Result.ok(dict) - Intelligence data (some values may be None on partial failure)
            - Result.ok(None) - Intelligence not available (use basic mode UI)
            - Result.fail() - All intelligence calls failed

        Profile Hub operates in two modes:
        - Basic mode: Core profile data always works
        - Full mode: Intelligence features when properly configured
        """
        # Check if factory is available
        if not services.context_intelligence:
            logger.info("Intelligence factory not configured - using basic mode")
            return Result.ok(None)

        try:
            intelligence = services.context_intelligence.create(context)
        except (AttributeError, TypeError, KeyError) as e:
            logger.warning(
                "Intelligence services not properly configured - using basic mode",
                extra={"error_type": type(e).__name__, "error_message": str(e)},
            )
            return Result.ok(None)

        # Independent calls — partial failures are tracked, not propagated
        daily_plan = alignment = synergies = learning_steps = None
        partial_errors: list[str] = []

        try:
            plan_result = await intelligence.get_ready_to_work_on_today()
            if plan_result.is_error:
                partial_errors.append("Daily plan unavailable")
            else:
                daily_plan = plan_result.value
        except Exception as e:  # safety-net: individual intelligence call
            logger.warning(f"Daily plan call failed: {e}")
            partial_errors.append("Daily plan unavailable")

        try:
            alignment_result = await intelligence.calculate_life_path_alignment()
            if alignment_result.is_error:
                partial_errors.append("Life path alignment unavailable")
            else:
                alignment = alignment_result.value
        except Exception as e:  # safety-net: individual intelligence call
            logger.warning(f"Alignment call failed: {e}")
            partial_errors.append("Life path alignment unavailable")

        try:
            synergies_result = await intelligence.get_cross_domain_synergies()
            if synergies_result.is_error:
                partial_errors.append("Cross-domain synergies unavailable")
            else:
                synergies = synergies_result.value
        except Exception as e:  # safety-net: individual intelligence call
            logger.warning(f"Synergies call failed: {e}")
            partial_errors.append("Cross-domain synergies unavailable")

        try:
            steps_result = await intelligence.get_optimal_next_learning_steps()
            if steps_result.is_error:
                partial_errors.append("Learning step recommendations unavailable")
            else:
                learning_steps = steps_result.value
        except Exception as e:  # safety-net: individual intelligence call
            logger.warning(f"Learning steps call failed: {e}")
            partial_errors.append("Learning step recommendations unavailable")

        if all(v is None for v in [daily_plan, alignment, synergies, learning_steps]):
            return Result.fail(Errors.system("All intelligence calls failed"))

        return Result.ok(
            {
                "daily_plan": daily_plan,
                "alignment": alignment,
                "synergies": synergies,
                "learning_steps": learning_steps,
                "partial_errors": partial_errors,
            }
        )

    @rt("/profile")
    async def profile_page(request: Request) -> Any:
        """Profile overview — Focus + Velocity + Activity domains at a glance."""
        user_uid = require_authenticated_user(request)

        try:
            context = await _get_context(user_uid)
        except ValueError as e:
            logger.error(
                "Failed to load context for profile page",
                extra={"user_uid": user_uid, "error": str(e)},
            )
            return await error_page(str(e), 500, request=request)

        from ui.profile.hub import ProfileHubView

        content = ProfileHubView(context)

        return await BasePage(
            content=content,
            title="Profile",
            request=request,
            active_page="profile",
        )

    @rt("/api/profile/{slug}/preview")
    async def domain_card_preview(request: Request, slug: str) -> Any:
        """
        HTMX fragment: top 5 active items for a domain card, sorted by priority.

        Called by the domain cards on the /profile overview page via
        hx-trigger="load". Returns a compact item list (priority dot + title)
        or an empty-state message.

        Requires authentication.
        """
        if slug not in _PREVIEW_VALID_SLUGS:
            from fasthtml.common import P as Para

            return Para("Unknown domain", cls="text-error text-sm")

        user_uid = require_authenticated_user(request)

        async def _fetch_items() -> Result[list[Any]]:
            """Dispatch to the correct service based on slug."""
            if slug == "tasks":
                if services.tasks is None:
                    return Result.fail(Errors.system("Tasks service not initialized"))
                return await services.tasks.get_user_tasks(user_uid)
            elif slug == "goals":
                if services.goals is None:
                    return Result.fail(Errors.system("Goals service not initialized"))
                return await services.goals.get_user_goals(user_uid)
            elif slug == "habits":
                if services.habits is None:
                    return Result.fail(Errors.system("Habits service not initialized"))
                return await services.habits.get_user_habits(user_uid)
            elif slug == "events":
                if services.events is None:
                    return Result.fail(Errors.system("Events service not initialized"))
                return await services.events.get_user_events(user_uid)
            elif slug == "choices":
                if services.choices is None:
                    return Result.fail(Errors.system("Choices service not initialized"))
                return await services.choices.get_user_choices(user_uid)
            else:  # principles
                if services.principles is None:
                    return Result.fail(Errors.system("Principles service not initialized"))
                return await services.principles.get_user_principles(user_uid)

        result = await _fetch_items()

        if result.is_error:
            from fasthtml.common import P as Para

            logger.warning(
                "Failed to load domain card preview",
                extra={"slug": slug, "user_uid": user_uid, "error": str(result.error)},
            )
            return Para("Unable to load items", cls="text-sm text-muted-foreground py-2")

        # Filter terminal statuses (completed, failed, cancelled, archived).
        # Guard against string status values returned by some service backends.
        _terminal_strings = frozenset(["completed", "failed", "cancelled", "archived"])
        active_items = [
            item
            for item in result.value
            if str(getattr(item, "status", "active")).lower() not in _terminal_strings
        ]

        # Sort by priority (most important first), take top 5
        sorted_items = sorted(active_items, key=_preview_priority_sort_key)
        preview_items = sorted_items[:5]

        return render_domain_card_preview(preview_items, slug)

    @rt("/api/sidebar/badges")
    async def sidebar_badges(request: Request) -> Any:
        """HTMX OOB-swap endpoint: async-loaded count + status badges for sidebar items.

        Returns Span elements with hx-swap-oob="true" that replace the
        `sidebar-badge-{slug}` placeholders rendered by `_default_item_renderer`.
        """
        from fasthtml.common import Span

        from ui.profile.badges import CountBadge, StatusBadge

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
                    StatusBadge(status),
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
                "learning-steps",
                learning_steps_count(context),
                learning_steps_active(context),
                learning_steps_status(context),
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
                    StatusBadge(status),
                    id=f"sidebar-badge-{slug}",
                    hx_swap_oob="true",
                    cls="flex items-center gap-1",
                )
            )

        return Div(*fragments)

    @rt("/profile/{domain}")
    async def profile_domain(request: Request, domain: str) -> Any:
        """Redirect legacy profile domain URLs.

        Activity domains redirect to /activities/{domain}.
        Curriculum domains redirect to standalone entity routes.
        """
        from starlette.responses import RedirectResponse

        activity_domains = {"tasks", "events", "goals", "habits", "principles", "choices"}
        if domain in activity_domains:
            focus = request.query_params.get("focus", "")
            suffix = f"?focus={focus}" if focus else ""
            return RedirectResponse(f"/{domain}{suffix}", status_code=302)

        curriculum_redirects = {
            "knowledge": "/ku",
            "learning-steps": "/learning-steps",
            "learning-paths": "/learning-paths",
        }
        if domain in curriculum_redirects:
            return RedirectResponse(curriculum_redirects[domain], status_code=302)

        return RedirectResponse("/profile", status_code=302)

    @rt("/profile/shared")
    async def profile_shared(request: Request) -> Any:
        """
        Shared With Me tab - shows assignments and events shared with current user.

        Assignments only. Will include events.
        """
        user_uid = require_authenticated_user(request)

        # Fetch shared reports
        from fasthtml.common import H2, H4, Div, P

        from ui.buttons import Button, ButtonLink, ButtonT
        from ui.layout import Size

        shared_reports = []
        if services.sharing:
            reports_result = await services.sharing.get_shared_with_me(
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
                            href=f"/submissions/{report.uid}",
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
            H2("📥 Shared With Me", cls="text-2xl font-bold mb-4"),
            P(
                "Reports and events shared with you by teachers, peers, and mentors.",
                cls="text-muted-foreground mb-6",
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
        from fasthtml.common import H2, H4, A, Div, P, Span

        # Query all KUs with user's relationship status via LessonService
        all_kus: list[dict] = []
        if services.lesson:
            result = await services.lesson.get_all_user_knowledge_status(user_uid)
            if result.is_error:
                logger.warning(f"Failed to fetch KUs: {result.expect_error()}")
            else:
                all_kus = result.value or []

        # Build KU cards
        def entity_card(ku: dict) -> Any:
            """Render a knowledge entity card with status badges."""
            ku_title = ku.get("title") or ku.get("uid") or "Untitled"
            ku_domain = ku.get("domain", "")
            is_viewed = ku.get("viewed", False)
            is_bookmarked = ku.get("bookmarked", False)
            is_mastered = ku.get("mastered", False)

            badges = []
            if is_mastered:
                badges.append(Badge("Mastered", variant=BadgeT.success, size=Size.xs))
            if is_bookmarked:
                badges.append(Badge("Bookmarked", variant=BadgeT.info, size=Size.xs))
            if is_viewed and not is_mastered:
                badges.append(Badge("Viewed", variant=BadgeT.ghost, size=Size.xs))

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
                href=f"/lesson/{ku['uid']}",
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
            H2("Knowledge Units", cls="text-2xl font-bold mb-2"),
            P(
                "All knowledge units in the curriculum. Track your learning progress.",
                cls="text-muted-foreground mb-6",
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

        intel_result = await _get_intelligence_data(context)
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
        intel_result = await _get_intelligence_data(context)
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
            _learning_steps_card,
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
        if intel_data.get("learning_steps") is not None:
            sections.append(_learning_steps_card(intel_data["learning_steps"]))

        return Div(*sections)

    logger.info("✅ Profile routes registered (/profile, /profile/{domain}, /profile/settings)")
    logger.info("✅ Profile chart API routes registered (/api/profile/charts/*)")
    logger.info(
        "✅ Profile HTMX intelligence endpoint registered (/api/profile/intelligence-section)"
    )


__all__ = ["setup_user_profile_routes"]
