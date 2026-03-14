"""Recommendation card pattern for action suggestions.

Displays an action recommendation with impact/effort assessment and
CTA buttons. Maps to UserContextIntelligence outputs.
"""

from fasthtml.common import H4, Div, P, Span

from ui.buttons import Button, ButtonT
from ui.layout import Size


def RecommendationCard(
    title: str,
    description: str,
    impact: str = "Medium",
    effort: str = "Medium",
    action_label: str = "Apply",
    learn_more: bool = True,
) -> Div:
    """Action recommendation with impact/effort and CTA buttons.

    Args:
        title: Recommendation title
        description: Detailed description
        impact: Impact level (High, Medium, Low)
        effort: Required effort (High, Medium, Low)
        action_label: Primary action button label
        learn_more: Show "Learn More" button

    Returns:
        Div with recommendation display
    """
    return Div(
        H4(title, cls="font-semibold text-foreground mb-2"),
        P(description, cls="text-muted-foreground text-sm mb-3"),
        Div(
            Span(f"Impact: {impact}", cls="text-success font-medium"),
            Span(f"Effort: {effort}", cls="text-primary font-medium"),
            cls="flex gap-4 mb-3 text-sm",
        ),
        Div(
            Button(action_label, variant=ButtonT.primary, size=Size.sm),
            Button("Learn More", variant=ButtonT.outline, size=Size.sm) if learn_more else None,
            cls="flex gap-2",
        ),
        cls="p-4 border border-border rounded bg-background shadow-sm",
    )
