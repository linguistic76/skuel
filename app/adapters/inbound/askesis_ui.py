"""
Askesis UI Components
=====================

Calm design UI for Askesis AI assistant following 5 design principles:

1. **Calm Design** - More breathing room, reduced visual stimuli
2. **Progressive Disclosure** - Start minimal, reveal contextually
3. **Visual Refinement** - Subtle shadows, consistent borders, refined typography
4. **Minimal Icons** - Focus on clean icons over emojis
5. **Centered Experience** - Chat interface as hero element

Philosophy: "Users can handle complexity, but they need visual calm to process it."
"""

__version__ = "5.0"

from typing import Any

from fasthtml.common import H1, H2, Div, Form, Label, Option, P, Span
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.forms import Select, Textarea
from ui.patterns.sidebar import SidebarItem, SidebarPage

logger = get_logger("skuel.ui.askesis")

ASKESIS_TITLE = "Askesis"
ASKESIS_STORAGE_KEY = "askesis-sidebar"
ASKESIS_ACTIVE_PAGE = "askesis"


# Sidebar items for Askesis pages
ASKESIS_SIDEBAR_ITEMS = [
    SidebarItem(
        "New Chat", "/askesis/new-chat", "new-chat", description="Start a fresh conversation"
    ),
    SidebarItem(
        "Chat History", "/askesis/history", "history", description="View past conversations"
    ),
    SidebarItem("Dashboard", "/askesis", "dashboard", description="AI assistant overview"),
    SidebarItem(
        "Analytics", "/askesis/analytics", "analytics", description="Intelligence insights"
    ),
    SidebarItem("Settings", "/askesis/settings", "settings", description="Configure assistant"),
]


class AskesisUI:
    """
    UI components for Askesis AI assistant.

    Design Principles:
    - Generous whitespace
    - Single focus (chat interface hero)
    - Minimal colors (2-3 max)
    - Subtle depth (shadows, borders)
    - Progressive disclosure (reveal when needed)
    - Clean typography hierarchy
    """

    @staticmethod
    def render_centered_welcome() -> Any:
        """
        Clean, centered welcome screen - login page inspired.

        Key differences from old design:
        - BEFORE: Sidebar + top nav + greeting + 5 emoji buttons + chat
        - AFTER: Just centered greeting + minimal input + hidden shortcuts

        Whitespace: 2-3x more than old design
        """
        return Div(
            # Centered container (like login page)
            Div(
                # Main greeting (generous top margin like login)
                Div(
                    H1(
                        "How can I help you today?",
                        cls="text-3xl font-bold text-center mb-3",
                    ),
                    P(
                        "Ask me anything about your learning, tasks, or knowledge.",
                        cls="text-base text-center text-base-content/60 mb-12",
                    ),
                    cls="mt-32",  # Generous top margin (login page style)
                ),
                # Chat input form (centered, clean like login form)
                Card(
                    Form(
                        Div(
                            Textarea(
                                name="message",
                                placeholder="Type your message here...",
                                cls="textarea textarea-bordered w-full min-h-[100px] resize-none focus:outline-none focus:ring-2 focus:ring-primary",
                                required=True,
                                rows=4,
                                id="chat-input",
                            ),
                            cls="mb-4",
                        ),
                        Div(
                            # Left: Model selector (subtle, like login's "Remember me")
                            Select(
                                Option("Sonnet 4.5", value="sonnet-4.5"),
                                Option("Opus 3", value="opus-3"),
                                Option("Haiku 3", value="haiku-3"),
                                name="model",
                                cls="select select-bordered select-sm text-sm",
                            ),
                            # Right: Primary action (blue button like login)
                            Button(
                                "Send Message",
                                type="submit",
                                variant=ButtonT.primary,
                                cls="px-8",
                                id="send-btn",
                            ),
                            cls="flex items-center justify-between",
                        ),
                        # Loading indicator (hidden by default, shown during request)
                        Div(
                            Div(
                                # Spinner icon
                                Div(
                                    cls="inline-block h-5 w-5 animate-spin rounded-full border-4 border-solid border-primary border-r-transparent",
                                ),
                                # Loading text
                                Span(
                                    "Processing your message with AI...",
                                    cls="ml-3 font-medium text-base text-primary",
                                ),
                                cls="flex items-center justify-center gap-2",
                            ),
                            id="loading-indicator",
                            cls="hidden mt-4 p-4 bg-primary/10 border border-primary/20 rounded-lg",
                        ),
                        **{
                            "hx-post": "/askesis/api/submit",
                            "hx-target": "#chat-messages",
                            "hx-swap": "beforeend",
                            "hx-indicator": "#loading-indicator",
                            "hx-disabled-elt": "#send-btn",
                            "hx-on::after-request": "this.reset(); document.getElementById('chat-messages').classList.remove('hidden');",
                        },
                        cls="space-y-4",
                    ),
                    cls="shadow-md",  # Subtle shadow (login page style)
                ),
                # Hidden shortcuts button (progressive disclosure)
                Div(
                    Button(
                        "Show quick shortcuts",
                        variant=ButtonT.ghost,
                        cls="btn-sm",
                        **{
                            "onclick": "document.getElementById('shortcuts').classList.toggle('hidden')",
                        },
                    ),
                    cls="text-center mt-6",
                ),
                # Shortcuts menu (hidden by default - progressive disclosure)
                Div(
                    Div(
                        Button("Write", variant=ButtonT.outline, cls="btn-sm"),
                        Button("Learn", variant=ButtonT.outline, cls="btn-sm"),
                        Button("Code", variant=ButtonT.outline, cls="btn-sm"),
                        Button("Plan", variant=ButtonT.outline, cls="btn-sm"),
                        cls="flex gap-2 justify-center flex-wrap",
                    ),
                    id="shortcuts",
                    cls="mt-4 hidden",
                ),
                # Chat messages container (hidden until first message)
                Div(
                    id="chat-messages",
                    cls="mt-8 space-y-3 hidden",
                ),
                cls="max-w-2xl mx-auto",  # Centered like login (max-w-md equivalent)
            ),
            cls="min-h-screen bg-base-100 px-4 py-8",
        )

    @staticmethod
    def render_message_bubble(sender: str, message: str, is_ai: bool = False) -> Any:
        """
        Clean message bubble with subtle styling.

        Inspired by login page's form input styling:
        - Subtle borders
        - Clean rounded corners
        - Minimal color (just border differences)
        - No heavy backgrounds
        """
        if is_ai:
            # AI message - subtle left border (like login's blue input focus)
            return Div(
                Div(
                    Span(
                        sender[0].upper(),
                        cls="inline-flex items-center justify-center w-8 h-8 rounded-full bg-primary text-primary-content text-sm font-semibold",
                    ),
                    cls="mr-3",
                ),
                Div(
                    P(sender, cls="text-xs text-base-content/60 mb-1"),
                    P(message, cls="text-base text-base-content"),
                    cls="flex-1",
                ),
                cls="flex items-start p-4 bg-base-100 border-l-2 border-primary rounded-lg",
            )
        else:
            # User message - subtle styling
            return Div(
                Div(
                    Span(
                        sender[0].upper(),
                        cls="inline-flex items-center justify-center w-8 h-8 rounded-full bg-base-300 text-base-content text-sm font-semibold",
                    ),
                    cls="mr-3",
                ),
                Div(
                    P(sender, cls="text-xs text-base-content/60 mb-1"),
                    P(message, cls="text-base text-base-content"),
                    cls="flex-1",
                ),
                cls="flex items-start p-4 bg-base-50 border border-base-300 rounded-lg",
            )


async def _render_askesis_page(
    request: Request, *, content: Any, active: str, page_title: str
) -> Any:
    """Render Askesis sidebar pages with consistent defaults."""
    return await SidebarPage(
        content=content,
        items=ASKESIS_SIDEBAR_ITEMS,
        active=active,
        title=ASKESIS_TITLE,
        storage_key=ASKESIS_STORAGE_KEY,
        page_title=page_title,
        request=request,
        active_page=ASKESIS_ACTIVE_PAGE,
    )


def create_askesis_ui_routes(_app, rt, _askesis_service):
    """Create UI routes for Askesis AI assistant."""

    routes = []

    @rt("/askesis")
    async def askesis_home(request: Request) -> Any:
        """Main Askesis page with progressive disclosure."""
        return await _render_askesis_page(
            request,
            content=AskesisUI.render_centered_welcome(),
            active="dashboard",
            page_title="Askesis - SKUEL",
        )

    routes.append(askesis_home)

    @rt("/askesis/new-chat")
    async def askesis_new_chat(request: Request) -> Any:
        """Start a new chat conversation."""
        return await _render_askesis_page(
            request,
            content=AskesisUI.render_centered_welcome(),
            active="new-chat",
            page_title="New Chat - Askesis - SKUEL",
        )

    routes.append(askesis_new_chat)

    @rt("/askesis/history")
    async def askesis_history(request: Request) -> Any:
        """View conversation history."""
        content = Div(
            H1("Chat History", cls="text-3xl font-bold mb-6"),
            P("Your past conversations will appear here.", cls="text-base-content/60 mb-4"),
            Div(
                Card(
                    P("No conversations yet", cls="text-center py-8 text-base-content/60"),
                    cls="bg-base-200",
                ),
                cls="max-w-4xl mx-auto",
            ),
        )
        return await _render_askesis_page(
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
            H1("Analytics", cls="text-3xl font-bold mb-6"),
            P("Intelligence insights and performance metrics.", cls="text-base-content/60 mb-4"),
            Div(
                Card(
                    Div(
                        H2("Coming Soon", cls="text-xl font-semibold mb-2"),
                        P(
                            "AI analytics and insights will be available here.",
                            cls="text-base-content/60",
                        ),
                        cls="text-center py-12",
                    ),
                    cls="bg-base-200",
                ),
                cls="max-w-4xl mx-auto",
            ),
        )
        return await _render_askesis_page(
            request,
            content=content,
            active="analytics",
            page_title="Analytics - Askesis - SKUEL",
        )

    routes.append(askesis_analytics)

    @rt("/askesis/settings")
    async def askesis_settings(request: Request) -> Any:
        """Configure Askesis assistant."""
        content = Div(
            H1("Settings", cls="text-3xl font-bold mb-6"),
            P("Configure your AI assistant preferences.", cls="text-base-content/60 mb-6"),
            Div(
                Card(
                    Form(
                        Div(
                            Label("Default Model", cls="label"),
                            Select(
                                Option("Sonnet 4.5", value="sonnet-4.5", selected=True),
                                Option("Opus 3", value="opus-3"),
                                Option("Haiku 3", value="haiku-3"),
                                name="default_model",
                                cls="select select-bordered w-full",
                            ),
                            cls="form-control mb-4",
                        ),
                        Div(
                            Label("Response Length", cls="label"),
                            Select(
                                Option("Concise", value="concise"),
                                Option("Balanced", value="balanced", selected=True),
                                Option("Detailed", value="detailed"),
                                name="response_length",
                                cls="select select-bordered w-full",
                            ),
                            cls="form-control mb-4",
                        ),
                        Button("Save Settings", variant=ButtonT.primary, type="submit"),
                        cls="space-y-4",
                    ),
                    cls="bg-base-200 p-6",
                ),
                cls="max-w-2xl mx-auto",
            ),
        )
        return await _render_askesis_page(
            request,
            content=content,
            active="settings",
            page_title="Settings - Askesis - SKUEL",
        )

    routes.append(askesis_settings)

    @rt("/askesis/api/submit")
    async def submit_message(request: Request):
        """Handle message submission (HTMX endpoint)."""
        user_uid = require_authenticated_user(request)

        form_data = await request.form()
        message = str(form_data.get("message", "")).strip()

        user_name = user_uid.replace("user_", "").title()

        if not message:
            return P("Please enter a message", cls="text-error text-sm")

        # Call AI service (mock for now)
        ai_response = "I'm processing your request..."

        if _askesis_service:
            try:
                result = await _askesis_service.answer_user_question(user_uid, message)

                # Check for errors FIRST, use error message if available
                if result.is_error:
                    logger.error(f"Askesis service error: {result.error}")
                    # Use error message if available, otherwise fallback
                    ai_response = (
                        result.error.message
                        if result.error.message
                        else "I'm having trouble right now. Please try again."
                    )
                else:
                    ai_response = result.value.get("answer", "No response generated.")

            except Exception as e:
                logger.error(f"Unexpected AI service error: {e}", exc_info=True)
                ai_response = "I'm having trouble right now. Please try again."

        # Return message bubbles
        user_bubble = AskesisUI.render_message_bubble(user_name, message, is_ai=False)
        ai_bubble = AskesisUI.render_message_bubble("AI", ai_response, is_ai=True)

        return user_bubble, ai_bubble

    routes.append(submit_message)

    logger.info(f"Askesis UI routes registered: {len(routes)} endpoints")
    return routes


# Export
__all__ = ["AskesisUI", "create_askesis_ui_routes"]
