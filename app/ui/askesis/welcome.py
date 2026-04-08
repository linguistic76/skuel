"""Askesis centered welcome screen."""

from typing import Any

from fasthtml.common import H1, Div, P, Span

from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.forms import Select, Textarea
from ui.layout import Size


def render_centered_welcome() -> Any:
    """
    Clean, centered welcome screen - login page inspired.

    Key design:
    - Centered greeting + minimal input + hidden shortcuts
    - 2-3x more whitespace than typical dashboard
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
                    cls="text-base text-center text-muted-foreground mb-12",
                ),
                cls="mt-32",
            ),
            # Chat input form (centered, clean like login form)
            Card(
                _render_chat_form(),
                cls="shadow-md",
            ),
            # Hidden shortcuts button (progressive disclosure)
            Div(
                Button(
                    "Show quick shortcuts",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    **{
                        "onclick": "document.getElementById('shortcuts').classList.toggle('hidden')",
                    },
                ),
                cls="text-center mt-6",
            ),
            # Shortcuts menu (hidden by default)
            Div(
                Div(
                    Button("Write", variant=ButtonT.outline, size=Size.sm),
                    Button("Learn", variant=ButtonT.outline, size=Size.sm),
                    Button("Code", variant=ButtonT.outline, size=Size.sm),
                    Button("Plan", variant=ButtonT.outline, size=Size.sm),
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
            cls="max-w-2xl mx-auto",
        ),
        cls="min-h-screen bg-background px-4 py-8",
    )


def _render_chat_form() -> Any:
    """Build the chat input form with model selector and loading indicator."""
    from fasthtml.common import Form, Option

    return Form(
        Div(
            Textarea(
                name="message",
                placeholder="Type your message here...",
                cls="min-h-[100px] resize-none focus:outline-none focus:ring-2 focus:ring-primary",
                required=True,
                rows=4,
                id="chat-input",
            ),
            cls="mb-4",
        ),
        Div(
            # Left: Model selector
            Select(
                Option("Sonnet 4.5", value="sonnet-4.5"),
                Option("Opus 3", value="opus-3"),
                Option("Haiku 3", value="haiku-3"),
                name="model",
                cls="text-sm",
                size=Size.sm,
                full_width=False,
            ),
            # Right: Primary action
            Button(
                "Send Message",
                type="submit",
                variant=ButtonT.primary,
                cls="px-8",
                id="send-btn",
            ),
            cls="flex items-center justify-between",
        ),
        # Loading indicator (hidden by default)
        Div(
            Div(
                Div(
                    cls="inline-block h-5 w-5 animate-spin rounded-full border-4 border-solid border-primary border-r-transparent",
                ),
                Span(
                    "Processing your message with AI...",
                    cls="ml-3 font-medium text-base text-primary",
                ),
                cls="flex items-center justify-center gap-2",
            ),
            id="loading-indicator",
            cls="hidden mt-4 p-4 bg-primary/10 border border-primary/20 rounded-lg",
        ),
        hx_post="/askesis/api/submit",
        hx_target="#chat-messages",
        hx_swap="beforeend",
        hx_indicator="#loading-indicator",
        hx_disabled_elt="#send-btn",
        **{
            "hx-on::after-request": "this.reset(); document.getElementById('chat-messages').classList.remove('hidden');"
        },
        cls="space-y-4",
    )
