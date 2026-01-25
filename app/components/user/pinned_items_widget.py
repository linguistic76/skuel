"""
Pinned Items Widget
===================

Dashboard widget showing user's pinned entities (tasks, goals, KUs, etc.).

Usage:
    from components.user.pinned_items_widget import PinnedItemsWidget

    # In dashboard/profile page
    await PinnedItemsWidget(user_uid="user.mike", user_relationship_service=services.user_relationships)
"""

from fasthtml.common import H3, A, Div, Li, Span, Ul


async def PinnedItemsWidget(user_uid: str, user_relationship_service):
    """
    Display pinned entities on user dashboard.

    Args:
        user_uid: User UID
        user_relationship_service: UserRelationshipService instance to fetch pins

    Returns:
        Widget component with pinned items list
    """
    # Fetch pinned entities
    pins_result = await user_relationship_service.get_pinned_entities(user_uid)

    # Handle errors or empty state
    if pins_result.is_error:
        return Div(
            H3("📌 Pinned Items", cls="text-lg font-bold mb-2"),
            Div(
                "Unable to load pinned items.",
                cls="text-sm text-error",
            ),
            cls="card bg-base-200 p-4 mb-4",
        )

    pinned_uids = pins_result.value

    if not pinned_uids:
        return Div(
            H3("📌 Pinned Items", cls="text-lg font-bold mb-2"),
            Div(
                "No pinned items yet. Click ",
                Span("📌", cls="font-bold"),
                " on any task, goal, or knowledge unit to pin it here for quick access.",
                cls="text-sm text-base-content/70",
            ),
            cls="card bg-base-200 p-4 mb-4",
        )

    # Render pinned items with links
    items = []
    for uid in pinned_uids:
        # Parse entity type from UID (e.g., "task.123" -> "task")
        entity_type = uid.split(".")[0] if "." in uid else "unknown"

        # Build link URL
        url = f"/{entity_type}s/{uid}"  # e.g., "/tasks/task.123"

        # Get icon based on entity type
        icon = _get_entity_icon(entity_type)

        items.append(
            Li(
                A(
                    Span(icon, cls="mr-2"),
                    Span(uid, cls="text-sm"),
                    href=url,
                    cls="link link-hover flex items-center",
                ),
                cls="mb-2",
            )
        )

    return Div(
        H3("📌 Pinned Items", cls="text-lg font-bold mb-2"),
        Ul(
            *items,
            cls="list-none pl-0",
        ),
        Div(
            Span(f"{len(pinned_uids)} pinned", cls="text-xs text-base-content/60"),
            cls="mt-2 pt-2 border-t border-base-300",
        ),
        cls="card bg-base-200 p-4 mb-4",
    )


def _get_entity_icon(entity_type: str) -> str:
    """
    Get emoji icon for entity type.

    Args:
        entity_type: Entity type (task, goal, habit, ku, etc.)

    Returns:
        Emoji icon string
    """
    icons = {
        "task": "✓",
        "goal": "🎯",
        "habit": "🔁",
        "event": "📅",
        "choice": "🔀",
        "principle": "⚖️",
        "ku": "📚",
        "ls": "🪜",
        "lp": "🛤️",
        "assignment": "📋",
        "journal": "📓",
    }
    return icons.get(entity_type, "📌")


async def PinnedItemsCompactWidget(user_uid: str, user_relationship_service, max_items: int = 5):
    """
    Compact version of pinned items widget (for sidebars).

    Args:
        user_uid: User UID
        user_relationship_service: UserRelationshipService instance
        max_items: Maximum items to display (default: 5)

    Returns:
        Compact widget component
    """
    # Fetch pinned entities
    pins_result = await user_relationship_service.get_pinned_entities(user_uid)

    if pins_result.is_error or not pins_result.value:
        return Div(
            Span("📌 Pinned", cls="text-xs font-semibold text-base-content/60 uppercase"),
            Div("None", cls="text-sm text-base-content/50 mt-1"),
            cls="mb-4",
        )

    pinned_uids = pins_result.value[:max_items]  # Limit to max_items

    # Render pinned items (compact)
    items = []
    for uid in pinned_uids:
        entity_type = uid.split(".")[0] if "." in uid else "unknown"
        url = f"/{entity_type}s/{uid}"
        icon = _get_entity_icon(entity_type)

        # Extract just the ID part for compact display
        short_id = uid.split(".")[-1] if "." in uid else uid

        items.append(
            Li(
                A(
                    Span(icon, cls="mr-1"),
                    Span(short_id, cls="text-xs truncate"),
                    href=url,
                    cls="link link-hover flex items-center text-sm",
                ),
                cls="mb-1",
            )
        )

    return Div(
        Span("📌 Pinned", cls="text-xs font-semibold text-base-content/60 uppercase mb-2 block"),
        Ul(
            *items,
            cls="list-none pl-0",
        ),
        cls="mb-4",
    )
