"""Home hub page — post-login landing with Submissions, GradeBook, and navigational cards.

Inlines Submissions and GradeBook HTMX preview blocks in a tabbed interface,
followed by a 2x2 card grid linking to Tasks+, Explore, Library, and Settings.
"""

from fasthtml.common import Button, Div

from ui.gradebook.hub import GRADEBOOK_BLOCKS
from ui.patterns.hub import HubCardData, HubContainerGrid, HubDomainBlockList
from ui.patterns.page_header import PageHeader
from ui.workbench.hub import SUBMISSIONS_BLOCKS

_HOME_CARDS: list[HubCardData] = [
    HubCardData(
        icon="\u2713",
        name="Tasks +",
        href="/tasks",
        description="Your tasks, goals, habits, and more at a glance",
    ),
    HubCardData(
        icon="\U0001f9ed",
        name="Explore",
        href="/explore",
        description="Discover knowledge units and path steps",
    ),
    HubCardData(
        icon="\U0001f4da",
        name="Library",
        href="/library",
        description="Browse exercises, resources, and curriculum",
    ),
    HubCardData(
        icon="\u2699\ufe0f",
        name="Settings",
        href="/settings",
        description="Preferences, display, notifications",
    ),
]


_TAB_BTN_BASE = (
    "px-4 py-2 text-sm font-medium rounded-full transition-colors focus:outline-none"
    " focus-visible:ring-2 focus-visible:ring-primary"
)
_TAB_BTN_ACTIVE = "bg-primary text-primary-foreground"
_TAB_BTN_INACTIVE = "text-muted-foreground hover:text-foreground"


def HomeHub() -> Div:
    """Home hub — Submissions + GradeBook previews in tabs, then 4 navigational cards."""
    return Div(
        PageHeader("Home", subtitle="Welcome to SKUEL"),
        Div(
            # Tab bar
            Div(
                Button(
                    "Submissions",
                    role="tab",
                    x_bind_aria_selected="activeTab === 'submissions'",
                    x_bind_tabindex="activeTab === 'submissions' ? 0 : -1",
                    x_bind_class=f"activeTab === 'submissions' ? '{_TAB_BTN_ACTIVE}' : '{_TAB_BTN_INACTIVE}'",
                    x_on_click="setActiveTab('submissions')",
                    x_on_keydown="handleTabKeydown($event, 'submissions')",
                    cls=_TAB_BTN_BASE,
                ),
                Button(
                    "GradeBook",
                    role="tab",
                    x_bind_aria_selected="activeTab === 'gradebook'",
                    x_bind_tabindex="activeTab === 'gradebook' ? 0 : -1",
                    x_bind_class=f"activeTab === 'gradebook' ? '{_TAB_BTN_ACTIVE}' : '{_TAB_BTN_INACTIVE}'",
                    x_on_click="setActiveTab('gradebook')",
                    x_on_keydown="handleTabKeydown($event, 'gradebook')",
                    cls=_TAB_BTN_BASE,
                ),
                role="tablist",
                cls="flex gap-1 mb-5",
            ),
            # Submissions panel
            Div(
                HubDomainBlockList(SUBMISSIONS_BLOCKS),
                role="tabpanel",
                x_show="activeTab === 'submissions'",
                x_cloak=True,
            ),
            # GradeBook panel
            Div(
                HubDomainBlockList(GRADEBOOK_BLOCKS),
                role="tabpanel",
                x_show="activeTab === 'gradebook'",
                x_cloak=True,
            ),
            x_data="accessibleTabs({ activeTab: 'submissions' })",
            cls="mb-8",
        ),
        HubContainerGrid(_HOME_CARDS, cols=2),
    )
