"""Home hub page — post-login landing with Submissions, GradeBook, and Library tabs."""

from fasthtml.common import Button, Div
from monsterui.franken import UkIcon  # type: ignore[import-untyped]

from ui.buttons import ButtonLink, ButtonT
from ui.gradebook.hub import GRADEBOOK_BLOCKS
from ui.library.hub import LIBRARY_BLOCKS
from ui.patterns.hub import HubDomainBlockList
from ui.workbench.hub import SUBMISSIONS_BLOCKS


_TAB_BTN_BASE = (
    "px-5 py-3 text-sm font-semibold border-b-3 cursor-pointer transition-colors"
    " focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
)
_TAB_BTN_ACTIVE = "border-primary text-primary"
_TAB_BTN_INACTIVE = "border-transparent text-muted-foreground hover:text-foreground hover:border-border"


def HomeHub() -> Div:
    """Home hub — Submissions, GradeBook, and Library previews in tabs."""
    return Div(
            # Tab bar
            Div(
                Button(
                    "Submissions",
                    role="tab",
                    cls=_TAB_BTN_BASE,
                    **{
                        ":aria-selected": "activeTab === 'submissions'",
                        ":tabindex": "activeTab === 'submissions' ? 0 : -1",
                        ":class": f"activeTab === 'submissions' ? '{_TAB_BTN_ACTIVE}' : '{_TAB_BTN_INACTIVE}'",
                        "@click": "activeTab = 'submissions'",
                    },
                ),
                Button(
                    "GradeBook",
                    role="tab",
                    cls=_TAB_BTN_BASE,
                    **{
                        ":aria-selected": "activeTab === 'gradebook'",
                        ":tabindex": "activeTab === 'gradebook' ? 0 : -1",
                        ":class": f"activeTab === 'gradebook' ? '{_TAB_BTN_ACTIVE}' : '{_TAB_BTN_INACTIVE}'",
                        "@click": "activeTab = 'gradebook'",
                    },
                ),
                Button(
                    "Library",
                    role="tab",
                    cls=_TAB_BTN_BASE,
                    **{
                        ":aria-selected": "activeTab === 'library'",
                        ":tabindex": "activeTab === 'library' ? 0 : -1",
                        ":class": f"activeTab === 'library' ? '{_TAB_BTN_ACTIVE}' : '{_TAB_BTN_INACTIVE}'",
                        "@click": "activeTab = 'library'",
                    },
                ),
                role="tablist",
                cls="flex border-b border-border mb-6",
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
        **{"x-data": "{ activeTab: 'submissions' }", "x-cloak": True},
    ),
    Div(
        ButtonLink(UkIcon("settings", height=14, width=14, cls="inline mr-1"), "Settings", href="/settings", variant=ButtonT.ghost, cls="text-muted-foreground"),
        cls="flex justify-end mt-4",
    ),
