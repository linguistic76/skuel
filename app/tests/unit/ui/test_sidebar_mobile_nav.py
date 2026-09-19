"""The section nav — the below-lg half of every sidebar page — is a nav list.

Its links navigate between PAGES, so the row is ``<nav><ul role="list">`` of
``<li><a aria-current="page">`` — never an ARIA tabs widget (``role="tab"``
+ ``aria-selected`` describe same-page panels; a screen reader told "tab" expects
the page to stay). The current link is marked server-side, every item is
``shrink-0`` so the ROW overflows and never the page, and one parse-time script
centres the lit link and stamps the overflow state the CSS fade reads.

The desktop sidebar is the other half of the same contract: a ``<nav>`` whose
rows carry the same ``aria-current``.
"""

from __future__ import annotations

import re

from fasthtml.common import Div, to_xml

from ui.patterns.sidebar import (
    SidebarItem,
    SidebarNav,
    SidebarPage,
    alpine_mobile_section_renderer,
)

ITEMS = [
    SidebarItem("Today", "/today", "today", icon="sun"),
    SidebarItem("Tasks", "/tasks", "tasks", icon="check-square"),
    SidebarItem("Goals", "/goals", "goals", icon="target"),
]


def _section_nav(html: str) -> str:
    """The below-lg block's markup — its wrapper up to its inline script."""
    start = html.index('class="section-nav')
    end = html.index("<script>", start)
    return html[start:end]


def _links(block: str) -> list[str]:
    return re.findall(r"<a[^>]*>", block)


def test_the_row_is_a_nav_list_of_page_links_not_a_tabs_widget() -> None:
    html = to_xml(SidebarNav(ITEMS, active="goals", title="Tasks+"))
    block = _section_nav(html)

    assert '<nav aria-label="Tasks+">' in block
    assert re.search(r'<ul role="list" class="[^"]*\boverflow-x-auto\b', block)
    assert 'role="tab"' not in block
    assert 'role="tablist"' not in block
    assert "aria-selected" not in block
    # Every link sits in its own non-shrinking list item.
    assert len(re.findall(r'<li class="shrink-0">', block)) == len(ITEMS)
    assert len(_links(block)) == len(ITEMS)


def test_the_current_page_is_the_one_link_marked_aria_current() -> None:
    html = to_xml(SidebarNav(ITEMS, active="goals", title="Tasks+"))
    block = _section_nav(html)

    current = [a for a in _links(block) if 'aria-current="page"' in a]
    assert len(current) == 1
    assert 'href="/goals"' in current[0]
    assert "border-primary" in current[0]
    # The lit link is the only one styled as lit.
    assert sum("border-primary" in a for a in _links(block)) == 1


def test_no_page_is_current_when_the_active_slug_matches_nothing() -> None:
    html = to_xml(SidebarNav(ITEMS, active="activity", title="Tasks+"))

    assert "aria-current" not in _section_nav(html)


def test_the_centring_script_follows_the_row_and_sets_scrollleft_not_scrollintoview() -> None:
    html = to_xml(SidebarNav(ITEMS, active="tasks", title="Tasks+"))

    # Directly after the </nav>, so `document.currentScript.previousElementSibling`
    # is the nav it measures.
    assert re.search(r"</nav>\s*<script>", html)
    script = html[html.index("<script>", html.index('class="section-nav')) :]
    script = script[: script.index("</script>")]
    assert "document.currentScript.previousElementSibling" in script
    assert "scrollLeft" in script
    assert "scrollIntoView" not in script
    assert "'data-overflow'" in script
    assert "'data-at-end'" in script


def test_the_desktop_sidebar_is_a_nav_whose_current_row_is_marked() -> None:
    html = to_xml(SidebarNav(ITEMS, active="tasks", title="Tasks+"))
    desktop = html[: html.index('class="section-nav')]

    assert 'aria-label="Tasks+ sidebar"' in desktop
    assert 'role="navigation"' not in desktop
    assert re.search(r'<nav[^>]*aria-label="Tasks\+ sidebar"', desktop)
    current = [a for a in re.findall(r"<a[^>]*>", desktop) if 'aria-current="page"' in a]
    assert len(current) == 1
    assert 'href="/tasks"' in current[0]


def test_an_itemless_sidebar_renders_no_section_nav() -> None:
    """Explore passes no items — no empty bordered strip below lg."""
    html = to_xml(SidebarNav([], active="", title="Explore"))

    assert "section-nav" not in html
    assert "<script>" not in html


def test_extra_mobile_sections_render_without_a_row_when_there_are_no_items() -> None:
    html = to_xml(
        SidebarNav([], active="", title="Explore", extra_mobile_sections=[Div("back", id="back")])
    )

    assert "section-nav" in html
    assert 'id="back"' in html
    assert "<ul" not in html[html.index("section-nav") :]


def test_a_custom_mobile_renderer_still_fills_a_list_and_gets_no_centring_script() -> None:
    """The teaching student page switches sections in Alpine inside an x-cloak
    wrapper, where the row has no geometry until Alpine boots."""
    html = to_xml(
        SidebarNav(
            ITEMS,
            active="tasks",
            title="Student",
            mobile_item_renderer=alpine_mobile_section_renderer("section"),
        )
    )
    block = html[html.index('class="section-nav') :]

    assert '<ul role="list"' in block
    assert len(re.findall(r'<li class="shrink-0">', block)) == len(ITEMS)
    assert "<script>" not in block


def test_the_icon_carries_one_aria_hidden() -> None:
    """Icon() owns the attribute: a caller's kwarg replaces it, never doubles it."""
    html = to_xml(SidebarNav(ITEMS, active="tasks", title="Tasks+"))
    svg = re.search(r"<svg[^>]*>", html)
    assert svg is not None
    assert svg.group(0).count("aria-hidden") == 1


def test_sidebar_item_has_no_children_field() -> None:
    """No nested items: a nested row would need an accordion with a keyboard path."""
    assert "children" not in SidebarItem.__dataclass_fields__


def test_the_full_page_carries_both_halves() -> None:
    html = to_xml(SidebarPage(Div("body"), items=ITEMS, active="today", title="Tasks+"))

    assert 'aria-label="Tasks+ sidebar"' in html
    assert '<nav aria-label="Tasks+">' in html
    assert len(re.findall(r'<a[^>]*aria-current="page"', html)) == 2
