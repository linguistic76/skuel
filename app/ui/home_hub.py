"""Home hub page — post-login landing with Submissions, GradeBook, and Library tabs."""

from fasthtml.common import Button, Div
from monsterui.franken import UkIcon  # type: ignore[import-untyped]

from ui.buttons import ButtonLink, ButtonT
from ui.gradebook.hub import GRADEBOOK_BLOCKS
from ui.library.hub import LIBRARY_BLOCKS
from ui.patterns.hub import HubDomainBlockList
from ui.workbench.hub import SUBMISSIONS_BLOCKS

_ACTIVE_STYLE = (
    "background-color: hsl(var(--primary));"
    " color: hsl(var(--primary-foreground));"
    " border-radius: 0.375rem;"
    " box-shadow: 0 1px 3px rgba(0,0,0,0.2);"
)
_INACTIVE_STYLE = (
    "background-color: transparent;"
    " color: hsl(var(--muted-foreground));"
    " border-radius: 0.375rem;"
)
_TAB_BASE = "px-5 py-2 text-sm font-semibold cursor-pointer transition-all"


def HomeHub(active_tab: str = "submissions") -> Div:
    """Home hub — Submissions, GradeBook, and Library previews in tabs.

    Args:
        active_tab: Which tab to show on load. One of 'submissions', 'gradebook', 'library'.
    """
    return Div(
        Div(
            # Tab bar — segmented-control using inline styles via Alpine :style to
            # bypass CSS class compilation. MonsterUI CSS variables drive the colors.
            Div(
                Button(
                    "Submissions",
                    role="tab",
                    cls=_TAB_BASE,
                    **{
                        ":aria-selected": "activeTab === 'submissions'",
                        ":tabindex": "activeTab === 'submissions' ? 0 : -1",
                        ":style": f"activeTab === 'submissions' ? '{_ACTIVE_STYLE}' : '{_INACTIVE_STYLE}'",
                        "@click": "activeTab = 'submissions'",
                    },
                ),
                Button(
                    "GradeBook",
                    role="tab",
                    cls=_TAB_BASE,
                    **{
                        ":aria-selected": "activeTab === 'gradebook'",
                        ":tabindex": "activeTab === 'gradebook' ? 0 : -1",
                        ":style": f"activeTab === 'gradebook' ? '{_ACTIVE_STYLE}' : '{_INACTIVE_STYLE}'",
                        "@click": "activeTab = 'gradebook'",
                    },
                ),
                Button(
                    "Library",
                    role="tab",
                    cls=_TAB_BASE,
                    **{
                        ":aria-selected": "activeTab === 'library'",
                        ":tabindex": "activeTab === 'library' ? 0 : -1",
                        ":style": f"activeTab === 'library' ? '{_ACTIVE_STYLE}' : '{_INACTIVE_STYLE}'",
                        "@click": "activeTab = 'library'",
                    },
                ),
                role="tablist",
                style="display: inline-flex; gap: 4px; padding: 4px; background-color: hsl(var(--muted)); border-radius: 0.5rem; margin-bottom: 1.5rem;",
            ),
            # Submissions panel
            Div(
                HubDomainBlockList(SUBMISSIONS_BLOCKS),
                role="tabpanel",
                **{"x-show": "activeTab === 'submissions'"},
            ),
            # GradeBook panel
            Div(
                HubDomainBlockList(GRADEBOOK_BLOCKS),
                role="tabpanel",
                **{"x-show": "activeTab === 'gradebook'"},
            ),
            # Library panel
            Div(
                HubDomainBlockList(LIBRARY_BLOCKS),
                role="tabpanel",
                **{"x-show": "activeTab === 'library'"},
            ),
            **{"x-data": f"{{ activeTab: '{active_tab}' }}", "x-cloak": True},
        ),
        Div(
            ButtonLink(
                UkIcon("settings", height=14, width=14, cls="inline mr-1"),
                "Settings",
                href="/settings",
                variant=ButtonT.ghost,
                cls="text-muted-foreground",
            ),
            cls="flex justify-end mt-4",
        ),
    )
