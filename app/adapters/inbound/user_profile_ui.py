"""
User Profile UI Routes - Profile Hub with Domain Sidebar
=========================================================

Routes for the user profile pages with Activity Domain navigation sidebar.

Key Routes:
- GET /profile - Profile with sidebar navigation (all 6 domains summary)
- GET /profile/{domain} - Domain-specific view (tasks, events, goals, habits, principles, choices)
- GET /profile/settings - User settings/preferences

Architecture:
- /profile is THE main entry point with domain sidebar navigation
- Uses UserContext (~240 fields) as the authoritative source for user state
- ProfileLayout provides sidebar navigation similar to /docs
"""

__version__ = "4.0"  # Merged dashboard sidebar into profile/hub

from typing import Any

from fasthtml.common import Request

from core.auth import require_authenticated_user
from core.ui.daisy_components import Div
from core.services.protocols import get_enum_value
from core.services.user.unified_user_context import UserContext
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.profile.badges import DomainStatus
from ui.profile.domain_views import (
    ChoicesDomainView,
    EventsDomainView,
    GoalsDomainView,
    HabitsDomainView,
    LearningDomainView,
    OverviewView,
    PrinciplesDomainView,
    TasksDomainView,
)
from ui.profile.layout import (
    CURRICULUM_ORDER,
    DEFAULT_DOMAIN_ICONS,
    DEFAULT_DOMAIN_NAMES,
    DOMAIN_ORDER,
    ProfileDomainItem,
    create_profile_page,
)

logger = get_logger("skuel.routes.user_profile")


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


def error_page(message: str, status_code: int, user_display_name: str = "User") -> Any:
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
        P(message, cls="text-lg text-base-content/70"),
        cls="flex flex-col items-center justify-center min-h-[400px] p-8"
    )

    return create_profile_page(
        content=content,
        domains=[],
        active_domain="",
        user_display_name=user_display_name,
        title=f"Error {status_code}",
        is_admin=False,
        curriculum_domains=[],
    )


# ============================================================================
# ROUTE SETUP
# ============================================================================


def setup_user_profile_routes(rt, services):
    """
    Setup user profile routes.

    Args:
        rt: FastHTML route decorator
        services: Services container with all backends
    """

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

        # Get user - ONE PATH (no fallback)
        user_result = await services.user_service.get_user(user_uid)
        if user_result.is_error:
            logger.error(
                "Failed to load user for settings",
                extra={"user_uid": user_uid, "error": str(user_result.error)},
            )
            return error_page("User not found", 404)

        user = user_result.value

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

        from components.user_preferences_components import UserPreferencesComponents

        return UserPreferencesComponents.render_preferences_editor(prefs_dict)

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
        update_result = await services.user_service.update_preferences(
            user_uid, preferences_update
        )

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
                    cls="text-sm text-base-content/50 mt-2",
                ),
                cls="p-4",
            )

        from components.user_preferences_components import UserPreferencesComponents

        return UserPreferencesComponents.render_preferences_saved_message()

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
        user_result = await services.user_service.get_user(user_uid)
        if user_result.is_error:
            raise ValueError(f"User not found: {user_uid}")
        user = user_result.value

        # Get context - ONE PATH (no fallback)
        context_result = await services.user_service.get_unified_context(user_uid)
        if context_result.is_error:
            raise ValueError(f"Failed to load context for user: {user_uid}")
        context = context_result.value

        return user, context

    def _build_domain_items(context: UserContext) -> list[ProfileDomainItem]:
        """
        Build ProfileDomainItem list from UserContext.

        Calculates counts and status for each domain.
        """
        items = []

        for slug in DOMAIN_ORDER:
            name = DEFAULT_DOMAIN_NAMES[slug]
            icon = DEFAULT_DOMAIN_ICONS[slug]
            href = f"/{slug}"  # Link directly to domain routes, not profile/hub summary

            # Calculate counts and status based on domain
            if slug == "tasks":
                count = len(context.active_task_uids) + len(context.completed_task_uids)
                active = len(context.active_task_uids)
                status = DomainStatus.calculate_tasks_status(
                    len(context.overdue_task_uids),
                    len(context.blocked_task_uids),
                )
            elif slug == "events":
                count = len(context.upcoming_event_uids) + len(context.today_event_uids)
                active = len(context.today_event_uids)
                status = DomainStatus.calculate_events_status(
                    0,
                    len(context.missed_event_uids),
                )
            elif slug == "goals":
                count = len(context.active_goal_uids) + len(context.completed_goal_uids)
                active = len(context.active_goal_uids)
                status = DomainStatus.calculate_goals_status(
                    len(context.at_risk_goals),
                    len(context.get_stalled_goals()),
                )
            elif slug == "habits":
                count = len(context.active_habit_uids)
                active = count
                status = DomainStatus.calculate_habits_status(len(context.at_risk_habits))
            elif slug == "principles":
                count = len(context.core_principle_uids)
                active = count
                status = DomainStatus.calculate_principles_status(
                    context.decisions_aligned_with_principles,
                    context.decisions_against_principles,
                )
            elif slug == "choices":
                count = len(context.pending_choice_uids) + len(context.resolved_choice_uids)
                active = len(context.pending_choice_uids)
                status = DomainStatus.calculate_choices_status(len(context.pending_choice_uids))
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

    def _build_curriculum_items(context: UserContext) -> list[ProfileDomainItem]:
        """
        Build ProfileDomainItem list for curriculum domains.

        Calculates counts and status for learning/curriculum domain.
        """
        items = []

        for slug in CURRICULUM_ORDER:
            name = DEFAULT_DOMAIN_NAMES[slug]
            icon = DEFAULT_DOMAIN_ICONS[slug]
            href = f"/profile/{slug}"

            if slug == "learning":
                # Count curriculum items
                mastered = len(context.mastered_knowledge_uids)
                in_progress = len(context.in_progress_knowledge_uids)
                ready = len(context.ready_to_learn_uids)
                enrolled_paths = len(context.enrolled_path_uids)
                blocked = len(context.prerequisites_needed)

                count = mastered + in_progress + ready
                active = in_progress + ready

                # Determine status
                if blocked > enrolled_paths * 0.5 and enrolled_paths > 0:
                    status = "critical"
                elif blocked > 0:
                    status = "warning"
                else:
                    status = "healthy"
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

    def _get_domain_view(domain: str, context: UserContext) -> Any:
        """
        Get the appropriate view component for a domain.

        Raises ValueError if domain is invalid (fail-fast).
        Note: Route validates domains, so this should never be reached.
        """
        views = {
            # Activity Domains
            "tasks": TasksDomainView,
            "events": EventsDomainView,
            "goals": GoalsDomainView,
            "habits": HabitsDomainView,
            "principles": PrinciplesDomainView,
            "choices": ChoicesDomainView,
            # Curriculum Domains
            "learning": LearningDomainView,
        }

        view_fn = views.get(domain)
        if view_fn:
            return view_fn(context)

        # Fail-fast: Route should validate domains, so this is a bug
        raise ValueError(f"Unknown domain: {domain}")

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
        """
        Profile overview page - shows all 6 Activity Domains + Curriculum with sidebar.

        Operates in two modes:
        - Basic mode: Core profile data (always works)
        - Full mode: Intelligence features when properly configured

        Intelligence features (when available):
        - Daily work plan (THE flagship recommendation)
        - Life path alignment (5 dimensions)
        - Cross-domain synergies (high-leverage actions)
        - Optimal learning steps

        Requires authentication.
        Fail-fast: Actual errors propagate to HTTP boundary.
        One path forward: Service succeeds or fails with clear error.
        """
        user_uid = require_authenticated_user(request)

        # Get user and context - ONE PATH (no fallback)
        try:
            user, context = await _get_user_and_context(user_uid)
        except ValueError as e:
            logger.error(
                "Failed to load user or context for profile page",
                extra={"user_uid": user_uid, "error": str(e)},
            )
            return error_page(str(e), 500)

        # Get intelligence data - may return None for basic mode
        intel_result = await _get_intelligence_data(context)
        if intel_result.is_error:
            # Actual error - propagate to HTTP boundary
            from starlette.responses import JSONResponse

            return JSONResponse(
                {"error": str(intel_result.error)},
                status_code=500,
            )

        intel_data = intel_result.value  # May be None (basic mode) or dict (full mode)
        domain_items = _build_domain_items(context)
        curriculum_items = _build_curriculum_items(context)
        display_name = user.display_name if user.display_name else user.username

        # Create OverviewView - passes None for intelligence data in basic mode
        if intel_data is not None:
            content = OverviewView(
                context,
                daily_plan=intel_data["daily_plan"],
                alignment=intel_data["alignment"],
                synergies=intel_data["synergies"],
                learning_steps=intel_data["learning_steps"],
            )
        else:
            # Basic mode - show profile without intelligence features
            content = OverviewView(context)

        # Check if user is admin (shows Admin Dashboard in navbar instead of Profile Hub)
        is_admin = user.can_manage_users() if hasattr(user, "can_manage_users") else False

        return create_profile_page(
            content=content,
            domains=domain_items,
            active_domain="",
            user_display_name=display_name,
            title="Profile Hub",
            is_admin=is_admin,
            curriculum_domains=curriculum_items,
        )

    @rt("/profile/{domain}")
    async def profile_domain(request: Request, domain: str) -> Any:
        """
        Domain-specific profile view with sidebar.

        Shows combined stats + item list for the selected domain.
        Valid domains: tasks, events, goals, habits, principles, choices, learning

        Requires authentication.
        One path forward: Service succeeds or fails with clear error.
        """
        # Activity Domains + Curriculum Domains
        valid_domains = {
            "tasks",
            "events",
            "goals",
            "habits",
            "principles",
            "choices",
            "learning",
        }
        if domain not in valid_domains:
            from starlette.responses import RedirectResponse

            return RedirectResponse("/profile", status_code=302)

        user_uid = require_authenticated_user(request)

        # Get user and context - ONE PATH (no fallback)
        try:
            user, context = await _get_user_and_context(user_uid)
        except ValueError as e:
            logger.error(
                "Failed to load user or context for domain view",
                extra={"user_uid": user_uid, "domain": domain, "error": str(e)},
            )
            return error_page(str(e), 500)

        domain_items = _build_domain_items(context)
        curriculum_items = _build_curriculum_items(context)
        display_name = user.display_name if user.display_name else user.username
        content = _get_domain_view(domain, context)
        domain_title = DEFAULT_DOMAIN_NAMES.get(domain, domain.title())

        # Check if user is admin (shows Admin Dashboard in navbar instead of Profile Hub)
        is_admin = user.can_manage_users() if hasattr(user, "can_manage_users") else False

        return create_profile_page(
            content=content,
            domains=domain_items,
            active_domain=domain,
            user_display_name=display_name,
            title=f"{domain_title} - Profile Hub",
            is_admin=is_admin,
            curriculum_domains=curriculum_items,
        )

    logger.info("✅ Profile routes registered (/profile, /profile/{domain}, /profile/settings)")


__all__ = ["setup_user_profile_routes"]
