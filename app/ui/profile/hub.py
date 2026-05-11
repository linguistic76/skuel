"""Profile hub page — 4-tab personal space.

/profile is the student's home: four tabs sharing the /library colored-header
block style. Default is "activities" — the 6 Activity Domains as preview
blocks. The other three tabs (Submissions / GradeBook / Library) carry the
loop stages: submit, grade, study.
"""

from __future__ import annotations

from fasthtml.common import Button, Div

from ui.activities.activity_hub import ACTIVITY_BLOCKS
from ui.gradebook.hub import GRADEBOOK_BLOCKS
from ui.library.hub import LIBRARY_BLOCKS
from ui.patterns.hub import HubDomainBlockList
from ui.workbench.hub import SUBMISSIONS_BLOCKS

ACTIVITIES_TAB_SLUG = "activities"
_VALID_TABS = frozenset({ACTIVITIES_TAB_SLUG, "submissions", "gradebook", "library"})


def normalize_tab(slug: str | None) -> str:
    """Coerce a query-string tab value to a known slug; default to activities."""
    return slug if slug in _VALID_TABS else ACTIVITIES_TAB_SLUG


def ProfileHubView(active_tab: str = ACTIVITIES_TAB_SLUG) -> Div:
    """Profile hub — 4 tabs (Activity Domains / Submissions / GradeBook / Library)."""
    active_tab = normalize_tab(active_tab)
    return Div(
        _tab_bar(),
        _tab_panels(),
        **{"x-data": f"{{ activeTab: '{active_tab}' }}", "x-cloak": True},
    )


# ---------------------------------------------------------------------------
# Tab bar — segmented control (Alpine-driven activeTab state)
# ---------------------------------------------------------------------------

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

_TAB_SPEC: tuple[tuple[str, str], ...] = (
    (ACTIVITIES_TAB_SLUG, "Activity Domains"),
    ("submissions", "Submissions"),
    ("gradebook", "GradeBook"),
    ("library", "Library"),
)


def _tab_bar() -> Div:
    return Div(
        *[_tab_button(slug, label) for slug, label in _TAB_SPEC],
        role="tablist",
        style=(
            "display: flex; width: 100%; gap: 4px; padding: 4px;"
            " background-color: hsl(var(--muted)); border-radius: 0.5rem; margin-bottom: 1.5rem;"
        ),
    )


def _tab_button(slug: str, label: str) -> Button:
    return Button(
        label,
        role="tab",
        cls=_TAB_BASE,
        **{
            ":aria-selected": f"activeTab === '{slug}'",
            ":tabindex": f"activeTab === '{slug}' ? 0 : -1",
            ":style": f"activeTab === '{slug}' ? '{_ACTIVE_STYLE}' : '{_INACTIVE_STYLE}'",
            "@click": f"activeTab = '{slug}'",
        },
    )


def _tab_panels() -> Div:
    return Div(
        Div(
            HubDomainBlockList(ACTIVITY_BLOCKS),
            role="tabpanel",
            **{"x-show": f"activeTab === '{ACTIVITIES_TAB_SLUG}'"},
        ),
        Div(
            HubDomainBlockList(SUBMISSIONS_BLOCKS),
            role="tabpanel",
            **{"x-show": "activeTab === 'submissions'"},
        ),
        Div(
            HubDomainBlockList(GRADEBOOK_BLOCKS),
            role="tabpanel",
            **{"x-show": "activeTab === 'gradebook'"},
        ),
        Div(
            HubDomainBlockList(LIBRARY_BLOCKS),
            role="tabpanel",
            **{"x-show": "activeTab === 'library'"},
        ),
    )


__all__ = ["ACTIVITIES_TAB_SLUG", "ProfileHubView", "normalize_tab"]
