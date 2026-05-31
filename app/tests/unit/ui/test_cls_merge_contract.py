"""Regression guard for the `cls=` / `**kwargs` collision bug class.

A UI helper that hardcodes `cls="..."` AND splats `**kwargs` into the same
element raises `TypeError: got multiple values for keyword argument 'cls'` the
moment a caller passes `cls=`. That bug 500'd the `/insights` page via
`SmallText(..., cls=...)` (PR #154). This test exercises every helper that is
expected to accept and *merge* a caller-supplied `cls`, so the pattern cannot
silently reappear.

The contract under test, for each helper:
  1. Passing `cls=<sentinel>` does NOT raise.
  2. The sentinel class survives into the rendered HTML.
  3. The helper's own base class is still present (merge, not replace).
"""

from collections.abc import Callable

import pytest

from ui.feedback import StatusBadge
from ui.layouts.dashboard import DashboardSection
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.empty_state import EmptyState
from ui.patterns.tree_view import TreeView
from ui.text import (
    BodyText,
    Caption,
    PageTitle,
    SectionTitle,
    SmallText,
    Subtitle,
    TruncatedText,
)

SENTINEL = "zzcls-sentinel"

# (name, factory taking cls=, expected base class fragment that must survive)
CASES: list[tuple[str, Callable[[str], object], str]] = [
    # Typography helpers (ui/text.py)
    ("PageTitle", lambda c: PageTitle("Title", cls=c), "mb-8"),
    ("SectionTitle", lambda c: SectionTitle("Section", cls=c), "text-2xl"),
    ("Subtitle", lambda c: Subtitle("Sub", cls=c), "text-base"),
    ("BodyText", lambda c: BodyText("Body", cls=c), "leading-relaxed"),
    ("SmallText", lambda c: SmallText("Small", cls=c), "text-sm"),
    ("Caption", lambda c: Caption("Caption", cls=c), "text-xs"),
    ("TruncatedText", lambda c: TruncatedText("Trunc", cls=c), "line-clamp-1"),
    # Pattern / layout helpers
    ("StatusBadge", lambda c: StatusBadge("active", cls=c), "bg-"),
    ("Breadcrumbs", lambda c: Breadcrumbs([{"title": "Home", "url": "/"}], cls=c), "breadcrumbs"),
    ("TreeView", lambda c: TreeView("root", "goal", "/api/{uid}", cls=c), "tree-container"),
    ("EmptyState", lambda c: EmptyState("Nothing here", cls=c), "text-center"),
    ("DashboardSection", lambda c: DashboardSection("Section", cls=c), "mt-8"),
]


@pytest.mark.parametrize("name,factory,base_cls", CASES, ids=[c[0] for c in CASES])
def test_cls_merges_without_collision(
    name: str, factory: Callable[[str], object], base_cls: str
) -> None:
    # 1. Must not raise TypeError on cls=.
    rendered = str(factory(SENTINEL))
    # 2. Caller-supplied class survives.
    assert SENTINEL in rendered, f"{name}: caller cls= was dropped"
    # 3. Base class survives (merge, not replace).
    assert base_cls in rendered, f"{name}: base class {base_cls!r} lost after merge"


@pytest.mark.parametrize("name,factory,base_cls", CASES, ids=[c[0] for c in CASES])
def test_no_cls_still_renders(name: str, factory: Callable[[str], object], base_cls: str) -> None:
    # The default (cls="") path must keep the base class and never leak a literal
    # "None" into the class attribute (the trailing-strip must yield clean output).
    rendered = str(factory(""))
    assert base_cls in rendered, f"{name}: base class missing on default path"
    assert 'class="None' not in rendered, f"{name}: literal None leaked into class"
    assert "None None" not in rendered, f"{name}: None artifact in merged class"
