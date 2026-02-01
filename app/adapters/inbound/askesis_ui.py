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

__version__ = "4.0"

from typing import Any

from fasthtml.common import (
    H1,
    H2,
    Body,
    Form,
    Head,
    Html,
    Label,
    Link,
    Meta,
    NotStr,
    P,
    Script,
    Title,
)
from starlette.requests import Request

from core.auth import get_current_user
from core.ui.daisy_components import Button, ButtonT, Card, Div, Option, Select, Span, Textarea
from core.utils.logging import get_logger
from ui.layouts.navbar import create_navbar_for_request

logger = get_logger("skuel.ui.askesis")


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

    @staticmethod
    def render_sidebar_layout(active_page: str, content: Any) -> NotStr:
        """
        SEL-inspired collapsible sidebar layout.

        Follows the EXACT pattern from /sel routes with:
        - Fixed sidebar with toggle
        - Rich menu items (title + description)
        - Active state styling
        - Smooth transitions
        - localStorage state persistence
        - Mobile responsiveness
        """
        # Menu items (calm design - ChatGPT-inspired)
        menu_items = [
            ("New Chat", "new-chat", "Start a fresh conversation"),
            ("Chat History", "history", "View past conversations"),
            ("Dashboard", "dashboard", "AI assistant overview"),
            ("Analytics", "analytics", "Intelligence insights"),
            ("Settings", "settings", "Configure assistant"),
        ]

        # Build sidebar links HTML (SEL pattern with onclick handling)
        sidebar_links = []
        for title, slug, description in menu_items:
            is_active = slug == active_page
            active_class = "active-menu-item" if is_active else ""
            href = "/askesis" if slug == "dashboard" else f"/askesis/{slug}"

            sidebar_links.append(f"""
                <a href="{href}" class="menu-item {active_class}" onclick="window.location.href='{href}'; return false;">
                    <div class="menu-item-title">{title}</div>
                    <div class="menu-item-desc">{description}</div>
                </a>
            """)

        # Complete layout HTML (EXACT SEL pattern)
        layout_html = f"""
        <style>
            /* Navbar positioning */
            nav.navbar {{
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                z-index: 1000;
                height: 64px;
            }}

            .askesis-container {{
                display: flex;
                min-height: calc(100vh - 64px);
                position: relative;
                margin-top: 64px;
            }}

            .askesis-sidebar {{
                width: 256px;
                background-color: oklch(var(--color-base-200));
                border-right: 1px solid oklch(var(--color-base-300));
                transition: transform 0.3s ease;
                position: fixed;
                top: 64px;
                left: 0;
                bottom: 0;
                z-index: 40;
                transform: translateX(0);
            }}

            .askesis-sidebar.collapsed {{
                transform: translateX(-208px);
            }}

            .sidebar-inner {{
                height: 100%;
                overflow-y: auto;
                position: relative;
            }}

            .askesis-content {{
                flex: 1;
                margin-left: 256px;
                padding: 2rem;
                transition: margin-left 0.3s ease;
                background: oklch(var(--color-base-100));
                min-height: calc(100vh - 64px);
            }}

            .askesis-content.expanded {{
                margin-left: 48px;
            }}

            .sidebar-toggle {{
                position: absolute;
                right: 10px;
                top: 20px;
                background: oklch(var(--color-base-100));
                border: 1px solid oklch(var(--color-base-300));
                cursor: pointer;
                padding: 8px;
                border-radius: 4px;
                transition: background 0.2s;
                z-index: 5;
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .sidebar-toggle:hover {{
                background: oklch(var(--color-base-300));
            }}

            .sidebar-header {{
                padding: 1.5rem;
                padding-right: 60px;
                font-size: 1.125rem;
                font-weight: 700;
                color: oklch(var(--bc));
                border-bottom: 1px solid oklch(var(--color-base-300));
            }}

            .askesis-sidebar.collapsed .sidebar-nav {{
                opacity: 0;
                visibility: hidden;
            }}

            .askesis-sidebar.collapsed .sidebar-header span {{
                opacity: 0;
            }}

            .sidebar-nav {{
                padding: 1rem;
                position: relative;
                z-index: 10;
            }}

            .menu-item {{
                display: block;
                padding: 0.75rem 1rem;
                margin-bottom: 0.5rem;
                border-radius: 8px;
                text-decoration: none;
                color: oklch(var(--bc) / 0.7);
                transition: all 0.2s;
                border-left: 3px solid transparent;
                cursor: pointer;
                position: relative;
                z-index: 11;
            }}

            .menu-item:hover {{
                background-color: oklch(var(--color-base-100));
                border-left-color: oklch(var(--bc) / 0.4);
            }}

            .menu-item.active-menu-item {{
                background-color: oklch(var(--p) / 0.1);
                border-left-color: oklch(var(--p));
                color: oklch(var(--p));
            }}

            .menu-item-title {{
                font-weight: 600;
                margin-bottom: 0.25rem;
            }}

            .menu-item-desc {{
                font-size: 0.75rem;
                color: oklch(var(--bc) / 0.5);
                line-height: 1.4;
            }}

            .active-menu-item .menu-item-desc {{
                color: oklch(var(--p) / 0.7);
            }}

            .overlay {{
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                z-index: 30;
                display: none;
            }}

            .overlay.active {{
                display: block;
            }}

            /* Mobile responsiveness */
            @media (max-width: 768px) {{
                .askesis-sidebar {{
                    width: 85%;
                    max-width: 320px;
                }}

                .askesis-content {{
                    margin-left: 0;
                }}

                .sidebar-toggle.shifted {{
                    left: 16px;
                }}
            }}
        </style>

        <div class="askesis-container">
            <!-- Overlay for mobile -->
            <div class="overlay" onclick="toggleSidebar()"></div>

            <!-- Sidebar -->
            <aside class="askesis-sidebar" id="askesis-sidebar">
                <div class="sidebar-inner">
                    <!-- Toggle Button positioned absolutely -->
                    <button class="sidebar-toggle" onclick="toggleSidebar()" title="Toggle Sidebar">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M9 18l6-6-6-6"></path>
                        </svg>
                    </button>

                    <div class="sidebar-header">
                        <span>Askesis</span>
                    </div>
                    <nav class="sidebar-nav">
                        {"".join(sidebar_links)}
                    </nav>
                </div>
            </aside>

            <!-- Main Content -->
            <main class="askesis-content" id="askesis-content">
                {content}
            </main>
        </div>

        <script>
            let sidebarCollapsed = false;

            function toggleSidebar() {{
                const sidebar = document.getElementById('askesis-sidebar');
                const content = document.getElementById('askesis-content');
                const overlay = document.querySelector('.overlay');

                sidebarCollapsed = !sidebarCollapsed;

                if (sidebarCollapsed) {{
                    sidebar.classList.add('collapsed');
                    content.classList.add('expanded');
                    overlay.classList.remove('active');
                }} else {{
                    sidebar.classList.remove('collapsed');
                    content.classList.remove('expanded');

                    // Show overlay on mobile
                    if (window.innerWidth <= 768) {{
                        overlay.classList.add('active');
                    }}
                }}

                // Save state
                localStorage.setItem('askesis-sidebar-collapsed', sidebarCollapsed);
            }}

            // Restore saved state on load
            document.addEventListener('DOMContentLoaded', function() {{
                const savedState = localStorage.getItem('askesis-sidebar-collapsed');
                console.log('Askesis Sidebar: Initializing, saved state:', savedState, 'window width:', window.innerWidth);

                // Only apply saved state on desktop
                if (window.innerWidth > 768 && savedState === 'true') {{
                    console.log('Askesis Sidebar: Applying saved collapsed state on desktop');
                    toggleSidebar();
                }}

                // Always start collapsed on mobile
                if (window.innerWidth <= 768) {{
                    console.log('Askesis Sidebar: Collapsing on mobile');
                    sidebarCollapsed = false; // Reset state
                    toggleSidebar(); // Collapse it
                }}

                console.log('Askesis Sidebar: Final collapsed state:', sidebarCollapsed);
            }});

            // Handle window resize
            window.addEventListener('resize', function() {{
                const overlay = document.querySelector('.overlay');
                if (window.innerWidth > 768) {{
                    overlay.classList.remove('active');
                }}
            }});
        </script>
        """

        return NotStr(layout_html)


def create_askesis_ui_routes(_app, rt, _askesis_service):
    """
    Create UI routes for Askesis AI assistant.

    Minimal route structure - just one main route with progressive disclosure.
    """

    routes = []

    @rt("/askesis")
    async def askesis_home(request: Request) -> Any:
        """
        Main Askesis page.

        Uses sidebar layout with progressive disclosure.
        """
        # Centered welcome screen (main content)
        content = AskesisUI.render_centered_welcome()

        # Wrap in sidebar layout (SEL pattern)
        page_layout = AskesisUI.render_sidebar_layout("dashboard", content)

        # Add navbar at top (session-aware for admin detection)
        navbar = _render_minimal_nav(request)

        # Return proper HTML document with data-theme for DaisyUI styling
        return Html(
            Head(
                Meta(charset="UTF-8"),
                Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
                Title("Askesis - SKUEL"),
                Link(rel="stylesheet", href="/static/css/output.css"),
                Script(src="/static/vendor/htmx/htmx.1.9.10.min.js"),
                Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True),
            ),
            Body(
                navbar,
                page_layout,
                cls="bg-base-100 text-base-content",
            ),
            **{"data-theme": "light"},
        )

    routes.append(askesis_home)

    @rt("/askesis/new-chat")
    async def askesis_new_chat(request: Request) -> Any:
        """Start a new chat conversation."""
        content = AskesisUI.render_centered_welcome()
        page_layout = AskesisUI.render_sidebar_layout("new-chat", content)
        navbar = _render_minimal_nav(request)

        return Html(
            Head(
                Meta(charset="UTF-8"),
                Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
                Title("New Chat - Askesis - SKUEL"),
                Link(rel="stylesheet", href="/static/css/output.css"),
                Script(src="/static/vendor/htmx/htmx.1.9.10.min.js"),
                Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True),
            ),
            Body(
                navbar,
                page_layout,
                cls="bg-base-100 text-base-content",
            ),
            **{"data-theme": "light"},
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
        page_layout = AskesisUI.render_sidebar_layout("history", content)
        navbar = _render_minimal_nav(request)

        return Html(
            Head(
                Meta(charset="UTF-8"),
                Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
                Title("Chat History - Askesis - SKUEL"),
                Link(rel="stylesheet", href="/static/css/output.css"),
                Script(src="/static/vendor/htmx/htmx.1.9.10.min.js"),
                Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True),
            ),
            Body(
                navbar,
                page_layout,
                cls="bg-base-100 text-base-content",
            ),
            **{"data-theme": "light"},
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
        page_layout = AskesisUI.render_sidebar_layout("analytics", content)
        navbar = _render_minimal_nav(request)

        return Html(
            Head(
                Meta(charset="UTF-8"),
                Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
                Title("Analytics - Askesis - SKUEL"),
                Link(rel="stylesheet", href="/static/css/output.css"),
                Script(src="/static/vendor/htmx/htmx.1.9.10.min.js"),
                Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True),
            ),
            Body(
                navbar,
                page_layout,
                cls="bg-base-100 text-base-content",
            ),
            **{"data-theme": "light"},
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
        page_layout = AskesisUI.render_sidebar_layout("settings", content)
        navbar = _render_minimal_nav(request)

        return Html(
            Head(
                Meta(charset="UTF-8"),
                Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
                Title("Settings - Askesis - SKUEL"),
                Link(rel="stylesheet", href="/static/css/output.css"),
                Script(src="/static/vendor/htmx/htmx.1.9.10.min.js"),
                Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True),
            ),
            Body(
                navbar,
                page_layout,
                cls="bg-base-100 text-base-content",
            ),
            **{"data-theme": "light"},
        )

    routes.append(askesis_settings)

    @rt("/askesis/api/submit")
    async def submit_message(request: Request):
        """Handle message submission (HTMX endpoint)."""
        form_data = await request.form()
        message = form_data.get("message", "")
        form_data.get("model", "sonnet-4.5")

        # Get user
        user_uid = get_current_user(request)
        user_name = user_uid.replace("user_", "").title() if user_uid else "User"

        if not message:
            return P("Please enter a message", cls="text-error text-sm")

        # Call AI service (mock for now)
        ai_response = "I'm processing your request..."

        if _askesis_service:
            try:
                result = await _askesis_service.answer_user_question(
                    user_uid or "demo_user", message
                )

                # Check for errors FIRST, use error message if available
                if result.is_error:
                    logger.error(f"Askesis service error: {result.error}")
                    # Use error message if available, otherwise fallback
                    ai_response = (
                        result.error.message
                        if hasattr(result.error, "message") and result.error.message
                        else "I'm having trouble right now. Please try again."
                    )
                else:
                    ai_response = result.value.get("answer", "No response generated.")

            except Exception as e:
                logger.error(f"Unexpected AI service error: {e}")
                ai_response = "I'm having trouble right now. Please try again."

        # Return message bubbles
        user_bubble = AskesisUI.render_message_bubble(user_name, message, is_ai=False)
        ai_bubble = AskesisUI.render_message_bubble("AI", ai_response, is_ai=True)

        return user_bubble, ai_bubble

    routes.append(submit_message)

    logger.info(f"✅ Askesis UI routes registered: {len(routes)} endpoints")
    return routes


def _render_minimal_nav(request) -> Any:
    """
    Minimal bottom navigation (optional).

    Uses create_navbar_for_request for session-aware admin detection.
    """
    return create_navbar_for_request(request)


# Export
__all__ = ["AskesisUI", "create_askesis_ui_routes"]
