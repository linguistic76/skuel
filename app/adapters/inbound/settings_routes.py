"""Settings Route Configuration — user preferences page.

Routes:
- GET /settings — user settings/preferences page
- POST /settings/save — save user preferences
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import safe_form_bool, safe_form_int, safe_form_string
from core.ports import get_enum_value
from core.utils.logging import get_logger
from ui.patterns.error_banner import render_error_banner
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services

logger = get_logger("skuel.routes.settings")


def create_settings_routes(
    app: "FastHTMLApp",
    rt: "RouteDecorator",
    services: "Services",
) -> None:
    """Register Settings routes."""

    user_service = services.user
    if user_service is None:
        raise RuntimeError("UserService is required for settings routes")

    @rt("/settings")
    def settings_page(request: Request) -> Any:
        """User settings page — shell renders immediately, content loads via HTMX."""
        require_authenticated_user(request)
        from fasthtml.common import A

        from ui.layouts.base_page import BasePage

        content = Div(
            PageHeader("Settings", subtitle="Manage your preferences"),
            Div(
                A(
                    "Devices — vault-agent enrollment →",
                    href="/settings/devices",
                    cls="link text-sm",
                ),
                cls="mb-4",
            ),
            content_loading_placeholder("/settings/content", "settings-content"),
        )
        return BasePage(
            content=content,
            title="Settings",
            request=request,
            active_page="settings",
        )

    @rt("/settings/content")
    async def settings_content_fragment(request: Request) -> Any:
        """HTMX fragment: user preferences editor."""
        user_uid = require_authenticated_user(request)

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error:
            logger.error("Failed to load user for settings", extra={"user_uid": user_uid})
            return Div(render_error_banner("Failed to load user settings"), id="settings-content")
        user = user_result.value
        if user is None:
            return Div(render_error_banner("User not found"), id="settings-content")

        prefs_dict: dict[str, Any] = {}
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

        return Div(
            UserPreferencesComponents.render_preferences_editor(prefs_dict),
            id="settings-content",
        )

    @rt("/settings/save")
    @csrf_protected
    async def save_settings(request: Request) -> Any:
        """Save user preferences from form submission."""
        user_uid = require_authenticated_user(request)

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

        update_result = await user_service.update_preferences(user_uid, preferences_update)

        if update_result.is_error:
            logger.error(
                "Failed to save user preferences",
                extra={"user_uid": user_uid, "error": str(update_result.error)},
            )
            from fasthtml.common import P

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

    logger.info("Settings routes registered")


__all__ = ["create_settings_routes"]
