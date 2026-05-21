"""Groups hub — tabbed view of content shared to each of a student's groups.

Mirrors the /profile tab pattern (Alpine-driven x-show panels, HTMX-loaded
block content) but with dynamic tabs: one per group the student belongs to,
capped at MAX_STUDENT_GROUPS. Each tab surfaces a single "Recent Shares"
block of UserEntry content peers shared via SHARED_WITH_GROUP.
"""

from fasthtml.common import Button, Div

from core.models.group.group import Group
from ui.patterns.empty_state import EmptyState
from ui.patterns.hub import HubBlockData, HubDomainBlock

_ACTIVE_STYLE = (
    "background-color: hsl(var(--primary));"
    " color: hsl(var(--primary-foreground));"
    " border-radius: 0.375rem;"
    " box-shadow: 0 1px 3px rgba(0,0,0,0.2);"
)
_INACTIVE_STYLE = (
    "background-color: transparent; color: hsl(var(--muted-foreground)); border-radius: 0.375rem;"
)
_TAB_BASE = "flex-1 text-center px-3 py-3 text-sm font-semibold cursor-pointer transition-all"
_TAB_BAR_STYLE = (
    "display: flex; width: 100%; gap: 4px; padding: 4px;"
    " background-color: hsl(var(--muted)); border-radius: 0.5rem; margin-bottom: 1.5rem;"
)


def _group_block(group: Group) -> HubBlockData:
    return HubBlockData(
        label="Recent Shares",
        slug=f"group-{group.uid}",
        icon="share-2",
        color="#8B5CF6",
        href=f"/groups/{group.uid}",
        preview_url=f"/api/groups/{group.uid}/shared/preview",
    )


def _tab_button(group: Group) -> Button:
    uid = group.uid
    cond = f"activeTab === '{uid}'"
    return Button(
        group.name,
        role="tab",
        cls=_TAB_BASE,
        **{
            ":aria-selected": cond,
            ":tabindex": f"{cond} ? 0 : -1",
            ":style": f"{cond} ? '{_ACTIVE_STYLE}' : '{_INACTIVE_STYLE}'",
            "@click": f"activeTab = '{uid}'",
        },
    )


def _tab_panel(group: Group) -> Div:
    return Div(
        HubDomainBlock(_group_block(group)),
        role="tabpanel",
        **{"x-show": f"activeTab === '{group.uid}'"},
    )


def GroupsHub(groups: list[Group], active_group_uid: str | None) -> Div:
    """Tabbed hub showing content shared with each of a student's groups.

    Args:
        groups: Groups the student is a member of (already capped to
            MAX_STUDENT_GROUPS by the route handler).
        active_group_uid: Which tab to show on load. Must be one of the
            group UIDs or None (used for the empty state).
    """
    if not groups:
        return Div(
            EmptyState(
                title="You are not in any groups yet",
                description=(
                    "Groups are how teachers organize students. Ask a teacher"
                    " to add you so you can see what your classmates are"
                    " sharing."
                ),
                icon="\U0001f465",
            )
        )

    active = active_group_uid if any(g.uid == active_group_uid for g in groups) else groups[0].uid

    return Div(
        Div(
            Div(
                *[_tab_button(g) for g in groups],
                role="tablist",
                style=_TAB_BAR_STYLE,
            ),
            *[_tab_panel(g) for g in groups],
            **{"x-data": f"{{ activeTab: '{active}' }}", "x-cloak": True},
        ),
    )


__all__ = ["GroupsHub"]
