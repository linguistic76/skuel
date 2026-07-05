"""Profile hub page — 3-tab personal space.

/profile is the student's home: three tabs sharing the /library colored-header
block style. Curriculum (study) and Reports (grade) show domain preview
blocks; Submissions (submit) is a simple button panel mirroring the
/submissions sidebar categories. Default is "submissions".
"""

from __future__ import annotations

from fasthtml.common import Button, Div

from ui.gradebook.hub import GRADEBOOK_BLOCKS
from ui.library.hub import LIBRARY_BLOCKS
from ui.patterns.hub import HubDomainBlockList
from ui.workbench.hub import SubmissionsTabPanel

_DEFAULT_TAB_SLUG = "submissions"
_VALID_TABS = frozenset({"curriculum", "reports", "submissions"})


def normalize_tab(slug: str | None) -> str:
    """Coerce a query-string tab value to a known slug; default to submissions."""
    return slug if slug in _VALID_TABS else _DEFAULT_TAB_SLUG


def ProfileHubView(active_tab: str = _DEFAULT_TAB_SLUG) -> Div:
    """Profile hub — 3 tabs (Curriculum / Reports / Submissions)."""
    active_tab = normalize_tab(active_tab)
    return Div(
        _tab_bar(),
        _tab_panels(),
        **{"x-data": f"{{ activeTab: '{active_tab}' }}", "x-cloak": True},
    )


# ---------------------------------------------------------------------------
# Tab bar — underline style (Alpine-driven activeTab state)
# ---------------------------------------------------------------------------

_TAB_BASE = "px-4 py-2.5 text-[14px] font-medium cursor-pointer transition-colors -mb-px"

_TAB_SPEC: tuple[tuple[str, str], ...] = (
    ("curriculum", "Curriculum"),
    ("reports", "Reports"),
    ("submissions", "Submissions"),
)


def _tab_bar() -> Div:
    return Div(
        *[_tab_button(slug, label) for slug, label in _TAB_SPEC],
        role="tablist",
        cls="flex border-b border-border mb-6",
    )


def _tab_button(slug: str, label: str) -> Button:
    return Button(
        label,
        role="tab",
        cls=_TAB_BASE,
        **{
            ":aria-selected": f"activeTab === '{slug}'",
            ":tabindex": f"activeTab === '{slug}' ? 0 : -1",
            ":class": f"activeTab === '{slug}' ? 'border-b-2 border-primary text-foreground font-semibold' : 'border-b-2 border-transparent text-muted-foreground hover:text-foreground'",
            "@click": f"activeTab = '{slug}'",
        },
    )


def _tab_panels() -> Div:
    return Div(
        Div(
            HubDomainBlockList(LIBRARY_BLOCKS),
            role="tabpanel",
            **{"x-show": "activeTab === 'curriculum'"},
        ),
        Div(
            HubDomainBlockList(GRADEBOOK_BLOCKS),
            role="tabpanel",
            **{"x-show": "activeTab === 'reports'"},
        ),
        Div(
            SubmissionsTabPanel(),
            role="tabpanel",
            **{"x-show": "activeTab === 'submissions'"},
        ),
    )


__all__ = ["ProfileHubView", "normalize_tab"]
