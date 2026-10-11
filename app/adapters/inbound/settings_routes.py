"""Settings Route Configuration — user preferences page.

Routes:
- GET /settings — user settings/preferences page
- GET /settings/content — the preferences editor fragment
- POST /settings/save — save user preferences (the editor's one form)
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import FT, Div
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_form_body
from core.models.user.user_request import UserPreferencesFormRequest
from core.utils.logging import get_logger
from core.utils.type_converters import get_enum_value
from core.utils.zone_context import default_zone
from ui.patterns.error_banner import render_error_banner
from ui.settings import render_settings_page

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services

logger = get_logger("skuel.routes.settings")


def create_settings_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
) -> None:
    """Register Settings routes."""

    user_service = services.user
    if user_service is None:
        raise RuntimeError("UserService is required for settings routes")

    @rt("/settings")
    def settings_page(request: Request) -> FT:
        """User settings page — shell renders immediately, content loads via HTMX."""
        require_authenticated_user(request)
        return render_settings_page(request)

    @rt("/settings/content")
    async def settings_content_fragment(request: Request) -> FT:
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

        from ui.settings.preferences import UserPreferencesComponents

        return Div(
            UserPreferencesComponents.render_preferences_editor(
                prefs_dict, default_timezone=default_zone().key
            ),
            id="settings-content",
        )

    @rt("/settings/save", methods=["POST"])
    @csrf_protected
    async def save_settings(request: Request) -> Any:
        """Save user preferences from form submission.

        Every field is validated before anything is written: a value the editor
        could not have sent — a number that does not read or is out of range, a
        learning level, time of day, theme or language outside its vocabulary, a
        malformed summary time, a time zone zoneinfo does not list, or a missing
        field — is refused (400, nothing saved), never replaced by a default. An
        empty time zone is the SKUEL default, stored as no choice.
        """
        user_uid = require_authenticated_user(request)

        parsed = await parse_form_body(request, UserPreferencesFormRequest)
        if parsed.is_error:
            return Response(parsed.expect_error().message, status_code=400)
        preferences_update = parsed.value.to_preferences_update()

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

        from ui.settings.preferences import UserPreferencesComponents

        saved_theme = parsed.value.theme
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
