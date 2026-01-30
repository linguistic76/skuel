"""
Breadcrumbs - Ancestor Navigation Trail
========================================

Shows path from root to current entity.

Usage:
    Breadcrumbs(
        path=[
            {"uid": "goal1", "title": "Career", "url": "/goals/goal1"},
            {"uid": "goal2", "title": "Python Mastery", "url": "/goals/goal2"},
            {"uid": "goal3", "title": "Django Framework", "url": None},  # Current (no link)
        ]
    )

See: /docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md
"""

from typing import Any

from fasthtml.common import A, Div, Li, Span


def Breadcrumbs(
    path: list[dict[str, Any]],
    separator: str = "›",
    show_home: bool = True,
    home_url: str = "/",
    **kwargs: Any,
) -> Div:
    """
    Render breadcrumb navigation trail.

    Args:
        path: List of {uid, title, url} dicts (last item is current page)
        separator: Separator between items (default: ›, rendered via CSS)
        show_home: Show home icon at start
        home_url: URL for home link

    Returns:
        Breadcrumbs navigation container
    """
    crumbs = []

    # Home link
    if show_home:
        crumbs.append(Li(A("🏠", href=home_url, cls="hover:underline")))

    # Path items
    for i, item in enumerate(path):
        is_last = i == len(path) - 1

        if is_last or not item.get("url"):
            # Current page (no link)
            crumbs.append(
                Li(
                    Span(item["title"], cls="text-base-content/70"),
                    cls="breadcrumb-current",
                )
            )
        else:
            # Linked ancestor
            crumbs.append(Li(A(item["title"], href=item["url"], cls="hover:underline")))

    return Div(*crumbs, cls="breadcrumbs text-sm", **kwargs)
