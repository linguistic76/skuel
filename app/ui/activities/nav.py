"""Activity Domain horizontal navigation — LA Times editorial style.

Renders a full-width background band with centered domain links.
Active domain is indicated by a thick colored bottom border.
Used at the top of every Activity Domain detail page.

Usage:
    from ui.activities.nav import ActivityDomainNav

    nav = ActivityDomainNav(current_domain="goals")
"""

from typing import TYPE_CHECKING

from fasthtml.common import A, Div
from monsterui.franken import UkIcon

if TYPE_CHECKING:
    from fasthtml.common import FT

# (key, label, icon, href, hex_color)
_ACTIVITY_DOMAINS: tuple[tuple[str, str, str, str, str], ...] = (
    ("tasks", "Tasks", "check-square", "/tasks", "#3B82F6"),
    ("goals", "Goals", "target", "/goals", "#F59E0B"),
    ("habits", "Habits", "repeat", "/habits", "#10B981"),
    ("events", "Events", "calendar", "/events", "#8B5CF6"),
    ("choices", "Choices", "git-branch", "/choices", "#F97316"),
    ("principles", "Principles", "compass", "/principles", "#EC4899"),
)

# Breakout from uk-container-small padding (UIKit default gutter = 30px)
# plus BasePage top padding flush
_BAND_STYLE = (
    "margin-top: -1rem; "  # flush against main navbar (BasePage p-4)
    "margin-left: -30px; "  # negate UIKit container gutter
    "margin-right: -30px; "
    "width: calc(100% + 60px); "
    "background-color: var(--background); "
    "border-top: 1px solid var(--border); "
    "border-bottom: 2px solid var(--border); "
    "margin-bottom: 2rem; "
)

_LINK_BASE = (
    "display: inline-flex !important; "
    "align-items: center; "
    "gap: 0.4rem; "
    "padding: 0.75rem 1.1rem; "
    "font-size: 0.72rem; "
    "font-weight: 600; "
    "letter-spacing: 0.07em; "
    "text-transform: uppercase; "
    "text-decoration: none !important; "
    "border-bottom: 3px solid transparent; "
    "white-space: nowrap; "
    "color: var(--muted-foreground); "
    "transition: opacity 0.15s; "
)


def ActivityDomainNav(current_domain: str) -> "FT":
    """Full-width editorial nav band for all 6 Activity Domains.

    Sits flush against the main navbar via negative top margin.
    Inactive items: muted gray text. Active: domain color + bottom border.

    Args:
        current_domain: The active domain key (e.g. "goals", "tasks").
    """
    items = []
    for key, label, icon, href, color in _ACTIVITY_DOMAINS:
        is_active = key == current_domain

        if is_active:
            link_style = (
                f"{_LINK_BASE}"
                f"color: {color} !important; "
                f"border-bottom-color: {color}; "
                "font-weight: 800; "
            )
        else:
            link_style = _LINK_BASE

        items.append(
            A(
                UkIcon(icon, cls="size-3"),
                label,
                href=href,
                style=link_style,
            )
        )

    return Div(
        Div(
            *items,
            style="display: flex; justify-content: center; flex-wrap: wrap;",
        ),
        style=_BAND_STYLE,
    )
