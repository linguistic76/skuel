"""Settings Route Configuration — user preferences page.

Routes:
- GET /settings — user settings/preferences page
- GET /settings/content — the preferences editor fragment
- POST /settings/save — save user preferences (the editor's one form)
- POST /api/user/display-name — change the signed-in user's display name (the
  Account card's save; answers HTMX with the card re-rendered)
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import FT, Div, FtResponse
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_body, parse_form_body
from adapters.inbound.route_factories.route_helpers import refuse_unavailable
from core.models.user.user_request import DisplayNameUpdateRequest, UserPreferencesFormRequest
from core.ports.query_types import DisplayNameSaved
from core.utils.auth_context import current_auth_state
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.type_converters import get_enum_value
from core.utils.zone_context import default_zone
from ui.layouts.base_page import HtmlDocument
from ui.patterns.error_banner import render_error_banner
from ui.settings import render_settings_page
from ui.settings.account import DISPLAY_NAME_REFUSAL, render_account_card

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import RouteDecorator
    from services_bootstrap._container import Services

logger = get_logger("skuel.routes.settings")


def create_settings_routes(
    rt: RouteDecorator,
    services: Services,
) -> None:
    """Register Settings routes."""

    user_service = services.user
    if user_service is None:
        raise RuntimeError("UserService is required for settings routes")

    @rt("/settings")
    def settings_page(request: Request) -> HtmlDocument:
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
    async def save_settings(request: Request) -> FT | Response:
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

    @rt("/api/user/display-name", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def save_display_name(
        request: Request,
    ) -> FtResponse | Result[DisplayNameSaved]:
        """Change the name the signed-in user is shown by (``DisplayNameUpdateRequest``).

        The name is trimmed; a blank one, one over the length limit, or one holding
        a control character or a line break is 400 and nothing is written. HTMX gets
        the Account card re-rendered: with the stored name and "Saved", or, refused,
        with the name the account still has and the reason, at the refusal's status.
        JSON gets ``{display_name}``.
        """
        user_uid = require_authenticated_user(request)
        htmx = bool(request.headers.get("HX-Request"))
        parsed = await parse_body(request, DisplayNameUpdateRequest)
        if parsed.is_error:
            if htmx:
                return refuse_unavailable(
                    render_account_card(
                        current_auth_state().display_name, note=DISPLAY_NAME_REFUSAL
                    ),
                    parsed.expect_error(),
                )
            return Result.fail(parsed)
        saved = await user_service.update_display_name(user_uid, parsed.value.display_name)
        if saved.is_error:
            if htmx:
                return refuse_unavailable(
                    render_account_card(
                        current_auth_state().display_name,
                        note="Your name could not be saved. Please try again.",
                    ),
                    saved.expect_error(),
                )
            return Result.fail(saved)
        name = saved.value.display_name
        if htmx:
            return FtResponse(render_account_card(name, saved=True))
        return Result.ok(DisplayNameSaved(display_name=name))

    logger.info("Settings routes registered")


__all__ = ["create_settings_routes"]
