"""
Askesis UI Routes
=================

UI routes for Askesis AI assistant — three-column chat surface.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import P
from starlette.responses import RedirectResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import safe_form_string
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import GuidanceMode
from core.services.intelligence_tier_service import get_user_intelligence_tier
from core.utils.logging import get_logger
from ui.askesis import render_askesis_page, render_assistant_message, render_user_message

if TYPE_CHECKING:
    from core.services.user_service import UserService

logger = get_logger("skuel.ui.askesis")


def create_askesis_ui_routes(
    _app: Any,
    rt: Any,
    _askesis_service: Any,
    intelligence_tier: IntelligenceTier | None = None,
    user_service: "UserService | None" = None,
) -> list[Any]:
    """Create UI routes for Askesis AI assistant."""

    routes = []

    @rt("/askesis")
    async def askesis_home(request: Request) -> Any:
        """Full Askesis chat surface."""
        return await render_askesis_page(request)

    routes.append(askesis_home)

    @rt("/askesis/new-chat")
    async def askesis_new_chat(request: Request) -> Any:
        return RedirectResponse("/askesis", status_code=302)

    routes.append(askesis_new_chat)

    @rt("/askesis/history")
    async def askesis_history(request: Request) -> Any:
        return RedirectResponse("/askesis", status_code=302)

    routes.append(askesis_history)

    @rt("/askesis/analytics")
    async def askesis_analytics(request: Request) -> Any:
        return RedirectResponse("/askesis", status_code=302)

    routes.append(askesis_analytics)

    @rt("/askesis/settings")
    async def askesis_settings(request: Request) -> Any:
        return RedirectResponse("/askesis", status_code=302)

    routes.append(askesis_settings)

    @rt("/askesis/api/submit")
    @csrf_protected
    async def submit_message(request: Request) -> Any:
        """Handle message submission (HTMX endpoint) — returns styled user + AI bubbles."""
        user_uid = require_authenticated_user(request)

        # Per-user tier gate (ADR-043): fail-secure — missing dependencies
        # mean the gate cannot be evaluated, so deny rather than allow.
        if intelligence_tier is None:
            return P(
                "AI features require a paid subscription. Upgrade to MEMBER to unlock Askesis.",
                cls="text-error text-sm px-7 py-2",
            )
        if user_service is None:
            return P(
                "Could not verify your access level. Please try again.",
                cls="text-error text-sm px-7 py-2",
            )
        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return P(
                "Could not verify your access level. Please try again.",
                cls="text-error text-sm px-7 py-2",
            )
        effective_tier = get_user_intelligence_tier(intelligence_tier, user_result.value.role)
        if not effective_tier.ai_enabled:
            return P(
                "AI features require a paid subscription. Upgrade to MEMBER to unlock Askesis.",
                cls="text-error text-sm px-7 py-2",
            )

        form_data = await request.form()
        message = safe_form_string(form_data.get("message"))

        if not message:
            return P("Please enter a message.", cls="text-error text-sm px-7 py-2")

        mode_str = safe_form_string(form_data.get("mode", ""))
        preferred_mode: GuidanceMode | None = (
            GuidanceMode(mode_str) if mode_str in GuidanceMode._value2member_map_ else None
        )

        ai_response: str
        try:
            result = await _askesis_service.answer_user_question(
                user_uid, message, preferred_mode=preferred_mode
            )
            if result.is_error:
                logger.error(f"Askesis service error: {result.error}")
                ai_response = (
                    result.error.message
                    if result.error.message
                    else "I'm having trouble right now. Please try again."
                )
            else:
                ai_response = result.value.get("answer", "No response generated.")
        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Unexpected AI service error: {e}", exc_info=True)
            ai_response = "I'm having trouble right now. Please try again."

        return render_user_message(message), render_assistant_message(ai_response)

    routes.append(submit_message)

    logger.info(f"Askesis UI routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_askesis_ui_routes"]
