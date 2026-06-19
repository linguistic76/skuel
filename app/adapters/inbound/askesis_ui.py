"""
Askesis UI Routes
=================

UI routes for Askesis AI assistant. All HTML construction delegated to ui/askesis/.

Design Philosophy: "Users can handle complexity, but they need visual calm to process it."
"""

from typing import Any

from fasthtml.common import H2, Div, P

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import safe_form_string
from core.utils.logging import get_logger
from ui.askesis import (
    render_askesis_page,
    render_centered_welcome,
    render_message_bubble,
    render_settings_form,
)
from ui.cards import Card
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.ui.askesis")


def create_askesis_ui_routes(_app, rt, _askesis_service):
    """Create UI routes for Askesis AI assistant."""

    routes = []

    @rt("/askesis")
    async def askesis_home(request: Request) -> Any:
        """Main Askesis page with progressive disclosure."""
        return await render_askesis_page(
            request,
            content=render_centered_welcome(),
            active="dashboard",
            page_title="Askesis - SKUEL",
        )

    routes.append(askesis_home)

    @rt("/askesis/new-chat")
    async def askesis_new_chat(request: Request) -> Any:
        """Start a new chat conversation."""
        return await render_askesis_page(
            request,
            content=render_centered_welcome(),
            active="new-chat",
            page_title="New Chat - Askesis - SKUEL",
        )

    routes.append(askesis_new_chat)

    @rt("/askesis/history")
    async def askesis_history(request: Request) -> Any:
        """View conversation history."""
        content = Div(
            PageHeader("Chat History", subtitle="Your past conversations will appear here."),
            Div(
                Card(
                    EmptyState(title="No conversations yet"),
                    cls="bg-muted",
                ),
                cls="max-w-4xl mx-auto",
            ),
        )
        return await render_askesis_page(
            request,
            content=content,
            active="history",
            page_title="Chat History - Askesis - SKUEL",
        )

    routes.append(askesis_history)

    @rt("/askesis/analytics")
    async def askesis_analytics(request: Request) -> Any:
        """View AI insights and analytics."""
        content = Div(
            PageHeader("Analytics", subtitle="Intelligence insights and performance metrics."),
            Div(
                Card(
                    Div(
                        H2("Coming Soon", cls="text-xl font-semibold mb-2"),
                        P(
                            "AI analytics and insights will be available here.",
                            cls="text-muted-foreground",
                        ),
                        cls="text-center py-12",
                    ),
                    cls="bg-muted",
                ),
                cls="max-w-4xl mx-auto",
            ),
        )
        return await render_askesis_page(
            request,
            content=content,
            active="analytics",
            page_title="Analytics - Askesis - SKUEL",
        )

    routes.append(askesis_analytics)

    @rt("/askesis/settings")
    async def askesis_settings(request: Request) -> Any:
        """Configure Askesis assistant."""
        return await render_askesis_page(
            request,
            content=render_settings_form(),
            active="settings",
            page_title="Settings - Askesis - SKUEL",
        )

    routes.append(askesis_settings)

    @rt("/askesis/api/submit")
    @csrf_protected
    async def submit_message(request: Request):
        """Handle message submission (HTMX endpoint)."""
        user_uid = require_authenticated_user(request)

        form_data = await request.form()
        message = safe_form_string(form_data.get("message"))

        user_name = user_uid.replace("user_", "").title()

        if not message:
            return P("Please enter a message", cls="text-error text-sm")

        # _askesis_service is always non-None here: register_domain_routes skips
        # route registration entirely when services.askesis is None (CORE tier).
        ai_response: str
        try:
            result = await _askesis_service.answer_user_question(user_uid, message)
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

        user_bubble = render_message_bubble(user_name, message, is_ai=False)
        ai_bubble = render_message_bubble("AI", ai_response, is_ai=True)

        return user_bubble, ai_bubble

    routes.append(submit_message)

    logger.info(f"Askesis UI routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_askesis_ui_routes"]
