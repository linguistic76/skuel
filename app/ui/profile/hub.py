"""Profile hub page — 4-tab personal space.

/profile is the student's home: four tabs sharing the /library colored-header
block style, mirroring the loop: Activities (live it), Curriculum (study),
Submissions (submit), Reports (grade). Curriculum, Activities, and Reports
show collapsible domain accordions (first section open, previews lazy-load on
reveal); Submissions is a simple button panel mirroring the /submissions
sidebar categories. Default is "activities".
"""

from __future__ import annotations

from fasthtml.common import A, Button, Div, Span

from ui.activities.hub import ACTIVITY_BLOCKS
from ui.components import Icon
from ui.gradebook.hub import GRADEBOOK_BLOCKS
from ui.library.hub import LIBRARY_BLOCKS
from ui.patterns.hub import HubAccordionBlockList
from ui.workbench.hub import SubmissionsTabPanel

_DEFAULT_TAB_SLUG = "activities"
_VALID_TABS = frozenset({"curriculum", "activities", "reports", "submissions"})


def normalize_tab(slug: str | None) -> str:
    """Coerce a query-string tab value to a known slug; default to activities."""
    return slug if slug in _VALID_TABS else _DEFAULT_TAB_SLUG


def _signout_row() -> A:
    """Sign out — the phone's only door, since the navbar icon is desktop-only.

    ``sm:hidden`` mirrors the navbar button's ``hidden sm:inline-flex``
    (``ui/layouts/navbar.py``): exactly one sign-out door at every width, never
    two. The Notes picker took the sixth top-bar slot, and an account action is
    what a profile page is for.
    """
    return A(
        Icon("log-out", cls="size-4", aria_hidden="true"),
        Span("Sign out"),
        href="/logout",
        cls=(
            "sm:hidden flex items-center justify-center gap-2 mb-4 px-3 py-2 rounded-md"
            " border border-border text-sm text-muted-foreground hover:bg-accent"
            " hover:text-foreground"
        ),
    )


def ProfileHubView(active_tab: str = _DEFAULT_TAB_SLUG) -> Div:
    """Profile hub — 4 tabs (Curriculum / Activities / Submissions / Reports)."""
    active_tab = normalize_tab(active_tab)
    tabs_js = "[" + ", ".join(f"'{slug}'" for slug, _ in _TAB_SPEC) + "]"
    return Div(
        # Outside the x-cloak block on purpose: signing out must not wait for
        # Alpine to boot the tabs.
        _signout_row(),
        Div(
            _tab_bar(),
            _tab_panels(),
            **{"x-data": f"{{ activeTab: '{active_tab}', tabs: {tabs_js} }}", "x-cloak": True},
        ),
    )


# ---------------------------------------------------------------------------
# Tab bar — underline style (Alpine-driven activeTab state)
# ---------------------------------------------------------------------------

_TAB_BASE = "px-4 py-2.5 text-sm font-medium cursor-pointer transition-colors -mb-px"

_TAB_SPEC: tuple[tuple[str, str], ...] = (
    ("activities", "Activities"),
    ("curriculum", "Curriculum"),
    ("submissions", "Submissions"),
    ("reports", "Reports"),
)


# Roving tabindex (WAI-ARIA tabs pattern): only the active tab is in the tab
# order; arrow keys move activation AND focus between tabs.
_FOCUS_ACTIVE_TAB = "$nextTick(() => document.getElementById('profile-tab-' + activeTab).focus())"


def _tab_bar() -> Div:
    return Div(
        *[_tab_button(slug, label) for slug, label in _TAB_SPEC],
        role="tablist",
        cls="flex border-b border-border mb-6",
        **{
            "aria-label": "Profile sections",
            "@keydown.arrow-right.prevent": (
                "activeTab = tabs[(tabs.indexOf(activeTab) + 1) % tabs.length]; "
                + _FOCUS_ACTIVE_TAB
            ),
            "@keydown.arrow-left.prevent": (
                "activeTab = tabs[(tabs.indexOf(activeTab) - 1 + tabs.length) % tabs.length]; "
                + _FOCUS_ACTIVE_TAB
            ),
            "@keydown.home.prevent": f"activeTab = tabs[0]; {_FOCUS_ACTIVE_TAB}",
            "@keydown.end.prevent": f"activeTab = tabs[tabs.length - 1]; {_FOCUS_ACTIVE_TAB}",
        },
    )


def _tab_button(slug: str, label: str) -> Button:
    return Button(
        label,
        role="tab",
        id=f"profile-tab-{slug}",
        type="button",
        aria_controls=f"profile-panel-{slug}",
        cls=_TAB_BASE,
        **{
            ":aria-selected": f"activeTab === '{slug}'",
            ":tabindex": f"activeTab === '{slug}' ? 0 : -1",
            ":class": f"activeTab === '{slug}' ? 'border-b-2 border-primary text-foreground font-semibold' : 'border-b-2 border-transparent text-muted-foreground hover:text-foreground'",
            "@click": f"activeTab = '{slug}'",
        },
    )


def _tab_panels() -> Div:
    def _panel(slug: str, content: Div) -> Div:
        return Div(
            content,
            role="tabpanel",
            id=f"profile-panel-{slug}",
            aria_labelledby=f"profile-tab-{slug}",
            tabindex="0",
            **{"x-show": f"activeTab === '{slug}'"},
        )

    return Div(
        _panel("activities", HubAccordionBlockList(ACTIVITY_BLOCKS)),
        _panel("curriculum", HubAccordionBlockList(LIBRARY_BLOCKS)),
        _panel("submissions", SubmissionsTabPanel()),
        _panel("reports", HubAccordionBlockList(GRADEBOOK_BLOCKS)),
    )


__all__ = ["ProfileHubView", "normalize_tab"]
