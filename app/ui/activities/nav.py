"""Activity Domain horizontal navigation — LA Times editorial style.

Renders a full-width background band with centered domain links.
Active domain is indicated by a thick colored bottom border.
Used at the top of every Activity Domain detail page.

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
    ("tasks", "Tasks", "check-square", "/tasks", "#3B82F6"),
    ("goals", "Goals", "target", "/goals", "#F59E0B"),
    ("habits", "Habits", "repeat", "/habits", "#10B981"),
    ("events", "Events", "calendar", "/events", "#8B5CF6"),
    ("choices", "Choices", "git-branch", "/choices", "#F97316"),
    ("principles", "Principles", "compass", "/principles", "#EC4899"),
)


def ActivityDomainNav(current_domain: str) -> "FT":
    """Full-width editorial nav band for all 6 Activity Domains.

    Inactive items: muted gray text, no decoration.
    Active item: domain color text + 3px colored bottom border.

    Breaks out of uk-container-small padding via .activity-domain-nav-bar CSS.

    Args:
        current_domain: The active domain key (e.g. "goals", "tasks").
    """
    items = []
    for key, label, icon, href, color in _ACTIVITY_DOMAINS:
        is_active = key == current_domain

        if is_active:
            link_cls = "activity-domain-nav-link activity-domain-nav-link-active"
            link_style = f"color: {color}; border-bottom-color: {color};"
        else:
            link_cls = "activity-domain-nav-link"
            link_style = ""

        items.append(
            A(
                Span(cls="uk-icon", **{"uk-icon": f"icon: {icon}; ratio: 0.75"}),
                label,
                href=href,
                cls=link_cls,
                style=link_style,
            )
        )

    return Div(
        Div(
            *items,
            style="display: flex; justify-content: center; flex-wrap: wrap;",
        ),
        cls="activity-domain-nav-bar",
    )
