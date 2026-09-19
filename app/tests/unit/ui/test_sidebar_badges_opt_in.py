"""The sidebar badge loader is opt-in and fires on reveal, not on load.

``GET /api/sidebar/badges`` builds the user's whole context, and its fragments
target only the Tasks+ domain rows — so only a sidebar that passes
``badges=True`` carries the loader and the ``sidebar-badge-{slug}`` slots, and
the loader's trigger is ``intersect once``: the desktop sidebar is
``display:none`` below lg, which never intersects, so a phone makes no badge
request at all.
"""

from __future__ import annotations

import re

from fasthtml.common import Div, to_xml

from ui.activities.nav import ACTIVITY_SIDEBAR_ITEMS, render_activity_sidebar_page
from ui.admin.layout import create_admin_page
from ui.library.nav import render_library_sidebar_page
from ui.patterns.sidebar import SidebarItem, SidebarNav, SidebarPage

ITEMS = [
    SidebarItem("Tasks", "/tasks", "tasks", icon="check-square"),
    SidebarItem("Goals", "/goals", "goals", icon="target"),
]

BADGES_REQUEST = 'hx-get="/api/sidebar/badges"'


def _desktop_nav(html: str) -> str:
    """The desktop sidebar's opening tag — where the loader's attributes sit."""
    match = re.search(r'<nav [^>]*aria-label="[^"]* sidebar"[^>]*>', html)
    assert match, html[:500]
    return match.group(0)


def test_a_sidebar_carries_no_loader_and_no_slots_by_default() -> None:
    html = to_xml(SidebarNav(items=ITEMS, active="tasks", title="Plain"))

    assert BADGES_REQUEST not in html
    assert "hx-trigger" not in _desktop_nav(html)
    assert "sidebar-badge-" not in html


def test_opting_in_puts_the_loader_on_the_desktop_nav_with_an_intersect_trigger() -> None:
    html = to_xml(SidebarNav(items=ITEMS, active="tasks", title="Plain", badges=True))
    nav = _desktop_nav(html)

    assert BADGES_REQUEST in nav
    assert 'hx-trigger="intersect once"' in nav
    assert 'hx-swap="none"' in nav
    assert html.count(BADGES_REQUEST) == 1  # the section nav never requests badges
    assert "load" not in re.search(r'hx-trigger="([^"]*)"', nav).group(1)  # type: ignore[union-attr]


def test_opting_in_renders_one_slot_per_row_on_the_desktop_side_only() -> None:
    html = to_xml(SidebarNav(items=ITEMS, active="tasks", title="Plain", badges=True))

    assert html.count('id="sidebar-badge-tasks"') == 1
    assert html.count('id="sidebar-badge-goals"') == 1
    section_nav = html[html.index('class="section-nav') :]
    assert "sidebar-badge-" not in section_nav


def test_sidebar_page_forwards_the_opt_in() -> None:
    off = to_xml(SidebarPage(content=Div("x"), items=ITEMS, active="tasks", title="Plain"))
    on = to_xml(
        SidebarPage(content=Div("x"), items=ITEMS, active="tasks", title="Plain", badges=True)
    )

    assert BADGES_REQUEST not in off
    assert BADGES_REQUEST in on


def test_the_tasks_plus_sidebar_opts_in_with_a_slot_on_every_row() -> None:
    html = to_xml(render_activity_sidebar_page(Div("x"), active="tasks"))

    assert 'hx-trigger="intersect once"' in _desktop_nav(html)
    for item in ACTIVITY_SIDEBAR_ITEMS:
        assert html.count(f'id="sidebar-badge-{item.slug}"') == 1, item.slug


def test_other_sidebars_never_request_badges() -> None:
    library = to_xml(render_library_sidebar_page(Div("x"), active="exercises"))
    admin = to_xml(create_admin_page(Div("x"), active_section="users", title="Users"))

    assert BADGES_REQUEST not in library
    assert BADGES_REQUEST not in admin
    assert "sidebar-badge-" not in library
    assert "sidebar-badge-" not in admin
