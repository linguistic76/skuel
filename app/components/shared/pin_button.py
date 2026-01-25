"""
Pin Button Component
====================

Reusable pin/unpin button for any entity (tasks, goals, KUs, assignments, etc.).

Usage:
    from components.shared.pin_button import PinButton

    # In entity card/detail view
    card = Div(
        # ... entity content ...
        PinButton(entity_uid="task.123", is_pinned=True),
        cls="card"
    )
"""

from fasthtml.common import Button, Span

from core.ui.daisy_components import ButtonT


def PinButton(entity_uid: str, is_pinned: bool = False, show_text: bool = False, size: str = "sm"):
    """
    Pin/unpin button with HTMX integration.

    Args:
        entity_uid: UID of entity to pin (e.g., "task.123", "goal.456", "ku.python")
        is_pinned: Whether entity is currently pinned
        show_text: Show "Pin"/"Unpin" text alongside icon
        size: Button size - "xs", "sm", "md", "lg" (default: "sm")

    Returns:
        Button component with HTMX handlers for pin/unpin

    Examples:
        # Icon only (default)
        PinButton(entity_uid="task.123", is_pinned=False)

        # With text
        PinButton(entity_uid="goal.456", is_pinned=True, show_text=True)

        # Large button
        PinButton(entity_uid="ku.python", is_pinned=False, size="md")
    """
    icon = "📌" if is_pinned else "○"  # Filled pin vs outline circle
    text = "Unpin" if is_pinned else "Pin"
    action = "Unpin" if is_pinned else "Pin"

    # Build button content
    content = [Span(icon, cls="mr-1" if show_text else "")]
    if show_text:
        content.append(Span(text))

    # HTMX attributes for pin/unpin
    htmx_attrs = {
        "id": f"pin-btn-{entity_uid}",
        "hx_swap": "outerHTML",
        "hx_target": f"#pin-btn-{entity_uid}",
        "title": action,
    }

    if is_pinned:
        # Unpin action (DELETE)
        htmx_attrs["hx_delete"] = f"/api/user/pins/{entity_uid}"
    else:
        # Pin action (POST)
        htmx_attrs["hx_post"] = "/api/user/pins"
        htmx_attrs["hx_vals"] = f'{{"entity_uid": "{entity_uid}"}}'

    # Button style
    button_class = f"btn btn-{size} {'btn-primary' if is_pinned else 'btn-ghost'}"

    return Button(
        *content,
        cls=button_class,
        **htmx_attrs,
    )


def PinButtonToggle(entity_uid: str, is_pinned: bool = False):
    """
    Render a pin button that the server can swap back after API call.

    This is what the server returns after pin/unpin API calls to update the UI.

    Args:
        entity_uid: UID of entity
        is_pinned: New pinned state (after toggle)

    Returns:
        Updated PinButton component
    """
    return PinButton(entity_uid=entity_uid, is_pinned=is_pinned)
