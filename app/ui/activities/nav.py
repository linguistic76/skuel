"""Activity Domain horizontal navigation.

Renders a visually distinct pill-bar showing all 6 Activity Domains,
each with its own color. Used at the top of every Activity Domain detail page.

Usage:
    from ui.activities.nav import ActivityDomainNav

    nav = ActivityDomainNav(current_domain="goals")
"""

from typing import TYPE_CHECKING

from fasthtml.common import A, Div, Span

if TYPE_CHECKING:
    from fasthtml.common import FT

# (key, label, icon, href, hex_color)
_ACTIVITY_DOMAINS: tuple[tuple[str, str, str, str, str], ...] = (
    ("tasks", "Tasks", "check-square", "/tasks", "#3B82F6"),      # Blue
    ("goals", "Goals", "target", "/goals", "#F59E0B"),             # Amber
    ("habits", "Habits", "repeat", "/habits", "#10B981"),          # Emerald
    ("events", "Events", "calendar", "/events", "#8B5CF6"),        # Violet
    ("choices", "Choices", "git-branch", "/choices", "#F97316"),   # Orange
    ("principles", "Principles", "compass", "/principles", "#EC4899"),  # Rose
)

_BASE_PILL = (
    "padding: 0.45rem 1.1rem; border-radius: 9999px; "
    "font-size: 0.75rem; font-weight: 700; letter-spacing: 0.07em; "
    "text-transform: uppercase; text-decoration: none; "
    "display: inline-flex; align-items: center; gap: 0.35rem; "
    "transition: opacity 0.15s ease;"
)


def ActivityDomainNav(current_domain: str) -> "FT":
    """Centered pill-bar with per-domain colors for all 6 Activity Domains.

    Active domain: solid color pill with white text and a soft drop shadow.
    Inactive domains: transparent background, colored text, semi-transparent border.

    Args:
        current_domain: The active domain key (e.g. "goals", "tasks").
    """
    items = []
    for key, label, icon, href, color in _ACTIVITY_DOMAINS:
        is_active = key == current_domain

        if is_active:
            pill_style = (
                f"{_BASE_PILL}"
                f"background: {color}; color: #fff; border: 1.5px solid {color}; "
                f"box-shadow: 0 2px 8px {color}55;"
            )
        else:
            pill_style = (
                f"{_BASE_PILL}"
                f"background: transparent; color: {color}; "
                f"border: 1.5px solid {color}55; opacity: 0.82;"
            )

        items.append(
            A(
                Span(cls="uk-icon", **{"uk-icon": f"icon: {icon}; ratio: 0.8"}),
                label,
                href=href,
                style=pill_style,
            )
        )

    return Div(
        Div(
            *items,
            style="display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: center;",
        ),
        style=(
            "padding: 1.1rem 0 1.4rem; "
            "border-bottom: 1px solid rgba(128,128,128,0.12); "
            "margin-bottom: 1.75rem;"
        ),
    )
