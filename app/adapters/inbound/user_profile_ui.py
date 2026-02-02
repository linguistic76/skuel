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
- Uses BasePage with /nous-style sidebar for modern, consistent UX
"""

__version__ = "4.0"  # Merged dashboard sidebar into profile/hub

from dataclasses import dataclass
from typing import Any

from fasthtml.common import Request

from core.auth import require_authenticated_user
from core.services.protocols import get_enum_value
from core.services.user.unified_user_context import UserContext
from core.ui.daisy_components import Div
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
        P(message, cls="text-lg text-base-content/70"),
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
            return await error_page("User not found", 404)

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
        update_result = await services.user_service.update_preferences(user_uid, preferences_update)

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
                    cls="text-sm text-base-content/60 mt-2",
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
        context_result = await services.user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            raise ValueError(f"Failed to load context for user: {user_uid}")
        context = context_result.value

        return user, context

    def _build_domain_items(
        context: UserContext, insight_counts: dict[str, int] | None = None
    ) -> list[ProfileDomainItem]:
        """
        Build ProfileDomainItem list from UserContext.

        Calculates counts and status for each domain.

        Args:
            context: UserContext with all domain data
            insight_counts: Optional dict mapping domain -> insight count (e.g., {"habits": 3})
        """
        items = []
        insight_counts = insight_counts or {}

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
                    insight_count=insight_count,  # Pass insight count to domain item
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

    def _get_domain_view(domain: str, context: UserContext, focus_uid: str | None = None) -> Any:
        """
        Get the appropriate view component for a domain.

        Phase 3, Task 11: Supports focus_uid for deep linking to specific entities.

        Args:
            domain: Domain name (tasks, events, goals, etc.)
            context: UserContext with all user data
            focus_uid: Optional entity UID to highlight/scroll to

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
            return view_fn(context, focus_uid)

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
            return await error_page(str(e), 500)

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

        # Get insight counts by domain for Profile Hub integration (Phase 1)
        insight_counts: dict[str, int] = {}
        total_unread_insights = 0
        if services.insight_store:
            counts_result = await services.insight_store.get_insight_counts_by_domain(user_uid)
            if not counts_result.is_error:
                insight_counts = counts_result.value
                total_unread_insights = sum(insight_counts.values())
            else:
                logger.warning(f"Failed to fetch insight counts: {counts_result.error}")

        domain_items = _build_domain_items(context, insight_counts)
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

        return await create_profile_page(
            content=content,
            domains=domain_items,
            active_domain="",
            user_display_name=display_name,
            title="Profile Hub",
            is_admin=is_admin,
            curriculum_domains=curriculum_items,
            unread_insights=total_unread_insights,
            request=request,
        )

    @rt("/profile/{domain}")
    async def profile_domain(request: Request, domain: str) -> Any:
        """
        Domain-specific profile view with sidebar.

        Shows combined stats + item list for the selected domain.
        Valid domains: tasks, events, goals, habits, principles, choices, learning

        Phase 3, Task 11: Supports ?focus={entity_uid} query param for deep linking from insights.

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

        # Parse typed parameters for deep linking (Phase 3, Task 11)
        params = parse_profile_params(request)
        focus_uid = params.focus

        # Get user and context - ONE PATH (no fallback)
        try:
            user, context = await _get_user_and_context(user_uid)
        except ValueError as e:
            logger.error(
                "Failed to load user or context for domain view",
                extra={"user_uid": user_uid, "domain": domain, "error": str(e)},
            )
            return await error_page(str(e), 500)

        # Get insight counts by domain for Profile Hub integration (Phase 1)
        insight_counts: dict[str, int] = {}
        total_unread_insights = 0
        if services.insight_store:
            counts_result = await services.insight_store.get_insight_counts_by_domain(user_uid)
            if not counts_result.is_error:
                insight_counts = counts_result.value
                total_unread_insights = sum(insight_counts.values())
            else:
                logger.warning(f"Failed to fetch insight counts: {counts_result.error}")

        domain_items = _build_domain_items(context, insight_counts)
        curriculum_items = _build_curriculum_items(context)
        display_name = user.display_name if user.display_name else user.username
        content = _get_domain_view(domain, context, focus_uid)
        domain_title = DEFAULT_DOMAIN_NAMES.get(domain, domain.title())

        # Check if user is admin (shows Admin Dashboard in navbar instead of Profile Hub)
        is_admin = user.can_manage_users() if hasattr(user, "can_manage_users") else False

        return await create_profile_page(
            content=content,
            domains=domain_items,
            active_domain=domain,
            user_display_name=display_name,
            title=f"{domain_title} - Profile Hub",
            is_admin=is_admin,
            curriculum_domains=curriculum_items,
            unread_insights=total_unread_insights,
            request=request,
        )

    @rt("/profile/shared")
    async def profile_shared(request: Request) -> Any:
        """
        Shared With Me tab - shows assignments and events shared with current user.

        Phase 1: Assignments only
        Phase 2: Will include events

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

        # Fetch shared assignments
        from fasthtml.common import H2, H4, A, Button, Div, P, Span

        shared_assignments = []
        if services.assignments_sharing:
            assignments_result = await services.assignments_sharing.get_assignments_shared_with_me(
                user_uid=user_uid,
                limit=50,
            )
            if not assignments_result.is_error:
                shared_assignments = assignments_result.value

        # Build shared content view
        def shared_content_card(assignment: Any) -> Any:
            """Render a shared assignment card."""
            return Div(
                Div(
                    # Header with filename and status
                    Div(
                        H4(assignment.original_filename, cls="card-title text-sm"),
                        Span(
                            assignment.status,
                            cls=f"badge badge-sm {_get_status_badge_class(assignment.status)}",
                        ),
                        cls="flex items-center justify-between",
                    ),
                    # Metadata
                    Div(
                        P(
                            f"Shared by: {assignment.user_uid}",
                            cls="text-xs text-base-content/60 mb-1",
                        ),
                        P(
                            f"Type: {assignment.assignment_type}",
                            cls="text-xs text-base-content/60 mb-0",
                        ),
                        cls="mt-2",
                    ),
                    # Actions
                    Div(
                        A(
                            "View",
                            href=f"/assignments/{assignment.uid}",
                            cls="btn btn-xs btn-primary",
                        ),
                        cls="mt-3",
                    ),
                    cls="card-body p-4",
                ),
                cls="card bg-base-200 shadow-sm hover:shadow-md transition-shadow",
            )

        def _get_status_badge_class(status: str) -> str:
            """Get DaisyUI badge class for assignment status."""
            classes = {
                "submitted": "badge-warning",
                "queued": "badge-warning",
                "processing": "badge-info",
                "completed": "badge-success",
                "failed": "badge-error",
                "manual_review": "badge-ghost",
            }
            return classes.get(status, "badge-ghost")

        # Content view
        content = Div(
            H2("📥 Shared With Me", cls="text-2xl font-bold mb-4"),
            P(
                "Assignments and events shared with you by teachers, peers, and mentors.",
                cls="text-base-content/70 mb-6",
            ),
            # Filter tabs (Phase 1: only Assignments active)
            Div(
                Button("All", cls="btn btn-sm btn-ghost", disabled=True),
                Button("Assignments", cls="btn btn-sm btn-primary"),
                Button("Events", cls="btn btn-sm btn-ghost", disabled=True),
                cls="flex gap-2 mb-6",
            ),
            # Shared content grid
            (
                Div(
                    *[shared_content_card(a) for a in shared_assignments],
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                )
                if shared_assignments
                else Div(
                    P(
                        "No content shared with you yet.",
                        cls="text-center text-base-content/60 py-12",
                    ),
                    cls="card bg-base-200 p-8",
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
        is_admin = user.can_manage_users() if hasattr(user, "can_manage_users") else False

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

    # ========================================================================
    # CHART API ROUTES - Phase 1, Task 2: Intelligence Data Visualization
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
            user, context = await _get_user_and_context(user_uid)
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
            user, context = await _get_user_and_context(user_uid)
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

        Phase 1, Task 3: Prevents blank screen during 2-3s intelligence load.
        """
        user_uid = require_authenticated_user(request)

        # Get user and context
        try:
            user, context = await _get_user_and_context(user_uid)
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
            from ui.profile.domain_views import _intelligence_unavailable_card

            return _intelligence_unavailable_card()

        # Full mode - return intelligence section
        from ui.profile.domain_views import (
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
