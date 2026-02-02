"""
IndentedList - Static Hierarchy Display
========================================

Renders a simple indented list without expand/collapse.
Fast rendering for shallow hierarchies.

Usage:
    IndentedList(
        items=[
            {"uid": "1", "title": "Root", "depth": 0},
            {"uid": "2", "title": "Child 1", "depth": 1},
            {"uid": "3", "title": "Child 2", "depth": 1},
            {"uid": "4", "title": "Grandchild", "depth": 2},
        ],
        entity_type="goal",
    )

See: /docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md
"""

from typing import Any

from fasthtml.common import A, Div, Span


def IndentedList(
    items: list[dict[str, Any]],
    entity_type: str,
    link_pattern: str | None = None,  # e.g., "/goals/{uid}"
    **kwargs: Any,
) -> Div:
    """
    Render static indented list.

    Args:
        items: List of {uid, title, depth} dicts
        entity_type: For icon selection
        link_pattern: Optional URL pattern (use {uid} placeholder)

    Returns:
        Indented list container
    """
    entity_icons = {
        "goal": "🎯",
        "habit": "🔄",
        "event": "📅",
        "choice": "🤔",
        "principle": "⚖️",
        "lp": "🛤️",
    }
    icon = entity_icons.get(entity_type, "📄")

    if not items:
        return Div(
            Span("No items", cls="text-base-content/60 text-sm italic text-center py-4"),
            cls="indented-list bg-base-100 rounded-lg border border-base-300 p-4",
            **kwargs,
        )

    list_items = []
    for item in items:
        uid = item["uid"]
        title = item.get("title", "Untitled")
        depth = item.get("depth", 0)
        indent = depth * 24

        # Content (link or plain text)
        if link_pattern:
            url = link_pattern.replace("{uid}", uid)
            content = A(
                Span(icon, cls="mr-2"),
                Span(title),
                href=url,
                cls="hover:bg-base-200 rounded px-2 py-1 flex items-center",
            )
        else:
            content = Div(
                Span(icon, cls="mr-2"),
                Span(title),
                cls="px-2 py-1 flex items-center",
            )

        list_items.append(
            Div(
                content,
                style=f"padding-left: {indent}px",
                cls="text-sm",
            )
        )

    return Div(
        *list_items,
        cls="indented-list space-y-1 bg-base-100 rounded-lg border border-base-300 p-2",
        **kwargs,
    )
