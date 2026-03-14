"""
User Profile UI Routes - Profile Hub with Sidebar Navigation
=============================================================

Routes for the user profile pages with sidebar navigation.

Key Routes:
- GET /profile - Profile overview (Focus + Velocity + Activity domains at a glance)
- GET /profile/{domain} - Domain-specific view (knowledge, learning-steps, learning-paths, shared)
- GET /profile/settings - User settings/preferences

Architecture:
- /profile is THE main entry point with sidebar navigation
- Activities overview (formerly /activities) is embedded in /profile
- Uses UserContext (~250 fields) as the authoritative source for user state
- Uses BasePage with sidebar for consistent UX
"""

__version__ = "4.0"  # Merged dashboard sidebar into profile/hub

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, Request

if TYPE_CHECKING:
    from services_bootstrap import Services

from adapters.inbound.auth import require_authenticated_user
from core.models.enums import Priority
from core.ports import get_enum_value
from core.services.user.unified_user_context import UserContext
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT, get_submission_status_badge_class
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
from ui.profile.layout import (
    CURRICULUM_ORDER,
    DEFAULT_DOMAIN_ICONS,
    DEFAULT_DOMAIN_NAMES,
    DOMAIN_ORDER,
    ProfileDomainItem,
    create_profile_page,
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
# FORM PARSING HELPERS
# ============================================================================


def safe_int(value: Any, default: int) -> int:
    """
    Safely parse integer from form data.

    Args:
        value: Form field value (may be None, empty string, or invalid)
        default: Default value if parsing fails

    Returns:
        Parsed integer or default

    Examples:
        >>> safe_int("25", 10)
        25
        >>> safe_int("", 10)
        10
        >>> safe_int(None, 10)
        10
        >>> safe_int("invalid", 10)
        10
    """
    if not value:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    """
    Safely parse boolean from form data.

    HTML checkboxes send "on" when checked, nothing when unchecked.

    Args:
        value: Form field value
        default: Default value if parsing fails

    Returns:
        Parsed boolean or default

    Examples:
        >>> safe_bool("on", False)
        True
        >>> safe_bool(None, False)
        False
        >>> safe_bool("true", False)
        True
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    # HTML checkbox values
    if value in ("on", "true", "True", "1"):
        return True
    if value in ("off", "false", "False", "0"):
        return False
    return default


# ============================================================================
# ERROR HANDLING HELPERS
# ============================================================================


async def error_page(message: str, status_code: int, user_display_name: str = "User") -> Any:
    """
    Unified error page for profile routes.

    One path forward: Clear errors with no silent fallbacks.

    Args:
        message: Error message to display
        status_code: HTTP status code (404, 500, etc.)
        user_display_name: User's display name for page header

    Returns:
        Error page with consistent styling
    """
    from fasthtml.common import H1, P

    from ui.profile.layout import create_profile_page

    content = Div(
        H1(f"Error {status_code}", cls="text-3xl font-bold text-error mb-4"),
        P(message, cls="text-lg text-muted-foreground"),
        cls="flex flex-col items-center justify-center min-h-[400px] p-8",
    )

    return await create_profile_page(
        content=content,
        domains=[],
        active_domain="",
        user_display_name=user_display_name,
        title=f"Error {status_code}",
        is_admin=False,
        curriculum_domains=[],
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

        try:
            user, _context = await _get_user_and_context(user_uid)
        except ValueError as e:
            logger.error("Failed to load user for settings", extra={"error": str(e)})
            return await error_page("User not found", 404)

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
            "learning_level": form_data.get("learning_level", "intermediate"),
            "preferred_modalities": modalities,
            "preferred_time_of_day": form_data.get("preferred_time_of_day", "anytime"),
            "available_minutes_daily": safe_int(form_data.get("available_minutes_daily"), 60),
            "enable_reminders": safe_bool(form_data.get("enable_reminders"), False),
            "reminder_minutes_before": safe_int(form_data.get("reminder_minutes_before"), 15),
            "daily_summary_time": form_data.get("daily_summary_time", "09:00"),
            "theme": form_data.get("theme", "light"),
            "language": form_data.get("language", "en"),
            "timezone": form_data.get("timezone", "UTC"),
            "weekly_task_goal": safe_int(form_data.get("weekly_task_goal"), 10),
            "daily_habit_goal": safe_int(form_data.get("daily_habit_goal"), 3),
            "monthly_learning_hours": safe_int(form_data.get("monthly_learning_hours"), 20),
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

    async def _get_user_and_context(
        user_uid: str,
    ) -> tuple[Any, UserContext]:
        """
        Get user entity and UserContext.

        One path forward: Get user and context from service or raise error.

        Args:
            user_uid: Authenticated user's UID

        Returns:
            Tuple of (User, UserContext)

        Raises:
            ValueError: If user or context cannot be loaded
        """
        # Get user - ONE PATH (no fallback)
        user_result = await user_service.get_user(user_uid)
        if user_result.is_error:
            raise ValueError(f"User not found: {user_uid}")
        user = user_result.value

        # Get context - ONE PATH (no fallback)
        context_result = await user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            raise ValueError(f"Failed to load context for user: {user_uid}")
        context = context_result.value

        return user, context

    def _build_domain_items(
        context: UserContext, insight_counts: dict[str, int] | None = None
    ) -> list[ProfileDomainItem]:
        """
        Build ProfileDomainItem list from UserContext using configuration.

        Configuration-driven approach eliminates repetitive if-elif blocks.

        Args:
            context: UserContext with all domain data
            insight_counts: Optional dict mapping domain -> insight count (e.g., {"habits": 3})

        See: /ui/profile/domain_stats_config.py
        """
        items = []
        insight_counts = insight_counts or {}

        for slug in DOMAIN_ORDER:
            name = DEFAULT_DOMAIN_NAMES[slug]
            icon = DEFAULT_DOMAIN_ICONS[slug]
            href = f"/{slug}"  # Link directly to domain routes, not profile/hub summary

            # Get configuration or use defaults
            config = DOMAIN_STATS_CONFIG.get(slug)
            if config:
                count = config.count_fn(context)
                active = config.active_fn(context)
                status_args = config.status_args_fn(context)
                status = config.status_fn(*status_args)
            else:
                count = 0
                active = 0
                status = "healthy"

            # Add insight count badge if available
            insight_count = insight_counts.get(slug, 0)

            items.append(
                ProfileDomainItem(
                    name=name,
                    slug=slug,
                    icon=icon,
                    count=count,
                    active_count=active,
                    status=status,
                    href=href,
                    insight_count=insight_count,
                )
            )

        return items

    def _build_curriculum_items(context: UserContext) -> list[ProfileDomainItem]:
        """
        Build ProfileDomainItem list for curriculum domains using configuration.

        Configuration-driven approach for curriculum domain statistics.

        See: /ui/profile/domain_stats_config.py
        """
        # Map slug -> (count_fn, active_fn, status_fn)
        curriculum_stats = {
            "knowledge": (knowledge_count, knowledge_active, knowledge_status),
            "learning-steps": (learning_steps_count, learning_steps_active, learning_steps_status),
            "learning-paths": (learning_paths_count, learning_paths_active, learning_paths_status),
        }

        items = []

        for slug in CURRICULUM_ORDER:
            name = DEFAULT_DOMAIN_NAMES[slug]
            icon = DEFAULT_DOMAIN_ICONS[slug]
            href = f"/profile/{slug}"

            stats_fns = curriculum_stats.get(slug)
            if stats_fns:
                count_fn, active_fn, status_fn = stats_fns
                count = count_fn(context)
                active = active_fn(context)
                status = status_fn(context)
            else:
                count = 0
                active = 0
                status = "healthy"

            items.append(
                ProfileDomainItem(
                    name=name,
                    slug=slug,
                    icon=icon,
                    count=count,
                    active_count=active,
                    status=status,
                    href=href,
                )
            )

        return items

    async def _get_intelligence_data(
        context: UserContext,
    ) -> "Result[dict[str, Any] | None]":
        """
        Get intelligence data for OverviewView if available.

        Calls UserContextIntelligence methods to get:
        - Daily work plan (THE flagship)
        - Life path alignment (5 dimensions)
        - Cross-domain synergies
        - Optimal learning steps

        Error Handling Strategy:
        - Configuration errors (AttributeError, TypeError, KeyError) → basic mode
        - Runtime computation errors → Result.fail() (propagates to HTTP boundary)
        - Service not available → basic mode

        Returns:
            - Result.ok(dict) - Intelligence data when fully configured
            - Result.ok(None) - Intelligence not available (use basic mode UI)
            - Result.fail() - Actual error during intelligence computation

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

            # Methods return Result[T] - propagate errors via Result.fail()
            plan_result = await intelligence.get_ready_to_work_on_today()
            if plan_result.is_error:
                return Result.fail(plan_result.expect_error())

            alignment_result = await intelligence.calculate_life_path_alignment()
            if alignment_result.is_error:
                return Result.fail(alignment_result.expect_error())

            synergies_result = await intelligence.get_cross_domain_synergies()
            if synergies_result.is_error:
                return Result.fail(synergies_result.expect_error())

            steps_result = await intelligence.get_optimal_next_learning_steps()
            if steps_result.is_error:
                return Result.fail(steps_result.expect_error())

            return Result.ok(
                {
                    "daily_plan": plan_result.value,
                    "alignment": alignment_result.value,
                    "synergies": synergies_result.value,
                    "learning_steps": steps_result.value,
                }
            )

        except (AttributeError, TypeError, KeyError) as e:
            # Configuration errors - intelligence services not properly configured
            # These are setup issues, not runtime errors - degrade gracefully to basic mode
            logger.warning(
                "Intelligence services not properly configured - using basic mode",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.ok(None)
        except Exception as e:
            # Unexpected error during intelligence computation
            # This is a true runtime error - propagate as failure
            logger.error(
                "Unexpected error in intelligence computation",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            from core.utils.result_simplified import Errors

            return Result.fail(Errors.system(f"Intelligence computation failed: {e}"))

    @rt("/profile")
    async def profile_page(request: Request) -> Any:
        """Profile overview — Focus + Velocity + Activity domains at a glance."""
        user_uid = require_authenticated_user(request)

        try:
            user, context = await _get_user_and_context(user_uid)
        except ValueError as e:
            logger.error(
                "Failed to load user or context for profile page",
                extra={"user_uid": user_uid, "error": str(e)},
            )
            return await error_page(str(e), 500)

        from ui.profile.lean_profile import LeanProfileView

        content = LeanProfileView(context)

        # Build sidebar domain items
        insight_counts: dict[str, int] = {}
        total_unread_insights = 0
        if services.insight_store:
            counts_result = await services.insight_store.get_insight_counts_by_domain(user_uid)
            if not counts_result.is_error:
                insight_counts = counts_result.value
                total_unread_insights = sum(insight_counts.values())

        domain_items = _build_domain_items(context, insight_counts)
        curriculum_items = _build_curriculum_items(context)
        display_name = user.display_name if user.display_name else user.username

        return await create_profile_page(
            content=content,
            domains=domain_items,
            active_domain="",
            user_display_name=display_name,
            title="Profile",
            is_admin=user.can_manage_users(),
            curriculum_domains=curriculum_items,
            unread_insights=total_unread_insights,
            request=request,
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
            "learning-steps": "/pathways",
            "learning-paths": "/pathways",
        }
        if domain in curriculum_redirects:
            return RedirectResponse(curriculum_redirects[domain], status_code=302)

        return RedirectResponse("/profile", status_code=302)

    @rt("/profile/shared")
    async def profile_shared(request: Request) -> Any:
        """
        Shared With Me tab - shows assignments and events shared with current user.

        Assignments only
        Will include events

        Uses profile hub layout with custom content view.
        """
        user_uid = require_authenticated_user(request)

        # Get user and context
        try:
            user, context = await _get_user_and_context(user_uid)
        except ValueError as e:
            logger.error(
                "Failed to load user or context for shared content page",
                extra={"user_uid": user_uid, "error": str(e)},
            )
            return await error_page(str(e), 500)

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

        # Build domain items for sidebar
        insight_counts: dict[str, int] = {}
        total_unread_insights = 0
        if services.insight_store:
            counts_result = await services.insight_store.get_insight_counts_by_domain(user_uid)
            if not counts_result.is_error:
                insight_counts = counts_result.value
                total_unread_insights = sum(insight_counts.values())

        domain_items = _build_domain_items(context, insight_counts)
        curriculum_items = _build_curriculum_items(context)
        display_name = user.display_name if user.display_name else user.username
        is_admin = user.can_manage_users()

        return await create_profile_page(
            content=content,
            domains=domain_items,
            active_domain="shared",  # Custom domain for sidebar highlighting
            user_display_name=display_name,
            title="Shared With Me - Profile Hub",
            is_admin=is_admin,
            curriculum_domains=curriculum_items,
            unread_insights=total_unread_insights,
            request=request,
        )

    async def _build_knowledge_view(context: UserContext, user_uid: str) -> Any:
        """Build the Knowledge domain view with all KUs and user status.

        Queries Neo4j for all Entity nodes with per-user VIEWED/BOOKMARKED/MASTERED relationships.
        """
        from fasthtml.common import H2, H4, A, Div, P, Span

        # Query all KUs with user's relationship status via ArticleService
        all_kus: list[dict] = []
        if services.article:
            result = await services.article.get_all_user_knowledge_status(user_uid)
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
                href=f"/article/{ku['uid']}",
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
            _user, context = await _get_user_and_context(user_uid)
        except ValueError as e:
            from starlette.responses import JSONResponse

            return JSONResponse({"error": str(e)}, status_code=500)

        intel_result = await _get_intelligence_data(context)
        if intel_result.is_error or intel_result.value is None:
            # No intelligence data - return empty chart
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
                                "text": "Life Path Alignment (No Data)",
                            }
                        },
                    },
                }
            )

        intel_data = intel_result.value
        alignment = intel_data.get("alignment")

        if alignment is None:
            from starlette.responses import JSONResponse

            return JSONResponse(
                {"error": "Alignment data not available"},
                status_code=500,
            )

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
            _user, context = await _get_user_and_context(user_uid)
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
            _user, context = await _get_user_and_context(user_uid)
        except ValueError as e:
            from ui.patterns.empty_state import EmptyState

            return EmptyState(
                title="Error Loading Intelligence",
                message=str(e),
                icon="⚠️",
            )

        # Get intelligence data - may return None for basic mode
        intel_result = await _get_intelligence_data(context)
        if intel_result.is_error:
            from ui.patterns.empty_state import EmptyState

            return EmptyState(
                title="Intelligence Unavailable",
                message="Failed to load intelligence features.",
                icon="⚠️",
            )

        intel_data = intel_result.value

        if intel_data is None:
            # Basic mode - return unavailable card
            from ui.profile.overview import _intelligence_unavailable_card

            return _intelligence_unavailable_card()

        # Full mode - return intelligence section
        from ui.profile.overview import (
            _alignment_breakdown,
            _chart_visualizations_section,
            _daily_work_plan_card,
            _learning_steps_card,
            _synergies_card,
        )

        return Div(
            _chart_visualizations_section(),
            _alignment_breakdown(intel_data["alignment"]),
            _daily_work_plan_card(intel_data["daily_plan"]),
            _synergies_card(intel_data.get("synergies", [])),
            _learning_steps_card(intel_data.get("learning_steps", [])),
        )

    logger.info("✅ Profile routes registered (/profile, /profile/{domain}, /profile/settings)")
    logger.info("✅ Profile chart API routes registered (/api/profile/charts/*)")
    logger.info(
        "✅ Profile HTMX intelligence endpoint registered (/api/profile/intelligence-section)"
    )


__all__ = ["setup_user_profile_routes"]
