"""Askesis chat message components."""

from typing import Any

from fasthtml.common import Div, P, Span


def render_message_bubble(sender: str, message: str, is_ai: bool = False) -> Any:
    """
    Clean message bubble with subtle styling.

    AI messages get a left border accent; user messages get muted background.
    """
    avatar_cls = (
        "inline-flex items-center justify-center w-8 h-8 rounded-full text-sm font-semibold"
    )

    if is_ai:
        return Div(
            Div(
                Span(sender[0].upper(), cls=f"{avatar_cls} bg-primary text-primary-content"),
                cls="mr-3",
            ),
            Div(
                P(sender, cls="text-xs text-muted-foreground mb-1"),
                P(message, cls="text-base text-foreground"),
                cls="flex-1",
            ),
            cls="flex items-start p-4 bg-background border-l-2 border-primary rounded-lg",
        )
    else:
        return Div(
            Div(
                Span(sender[0].upper(), cls=f"{avatar_cls} bg-secondary text-foreground"),
                cls="mr-3",
            ),
            Div(
                P(sender, cls="text-xs text-muted-foreground mb-1"),
                P(message, cls="text-base text-foreground"),
                cls="flex-1",
            ),
            cls="flex items-start p-4 bg-muted border border-border rounded-lg",
        )
