"""Empty state pattern for when there's no data to display.

Empty states provide helpful feedback when a list or section has no
content, along with optional actions to create the first item.
"""

from typing import Any

from fasthtml.common import Div

from ui.buttons import ButtonLink
from ui.layout import Stack
from ui.text import BodyText


def EmptyState(
    title: str,
    description: str = "",
    action_text: str | None = None,
    action_href: str | None = None,
    icon: str | None = None,
    **kwargs: Any,
) -> Div:
    """Empty state display with optional call-to-action.

    Args:
        title: Main message (e.g., "No tasks yet")
        description: Optional explanatory text
        action_text: Optional button text (e.g., "Create your first task")
        action_href: Optional URL for the action button
        icon: Optional icon/emoji to display above the title
        **kwargs: Additional attributes passed to the container Div

    Returns:
        A centered Div with the empty state content

    Example:
        EmptyState(
            title="No tasks yet",
            description="Tasks help you track what needs to be done.",
            action_text="Create your first task",
            action_href="/tasks/create",
            icon="📝",
        )
    """
    content = []

    if icon:
        content.append(
            Div(icon, cls="text-5xl mb-4", aria_hidden="true")
        )  # Decorative - title conveys meaning

    # Use a smaller, centered title for empty states
    content.append(Div(title, cls="text-xl font-semibold text-base-content"))

    if description:
        content.append(BodyText(description, muted=True))

    if action_text and action_href:
        content.append(Div(ButtonLink(action_text, href=action_href), cls="mt-6"))

    # Merge with kwargs cls
    base_cls = "text-center py-12"
    extra_cls = kwargs.pop("cls", "")
    full_cls = f"{base_cls} {extra_cls}".strip()

    return Div(
        Stack(*content, gap=2),
        cls=full_cls,
        **kwargs,
    )
