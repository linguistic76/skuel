"""The chrome's geometry: one navbar height, a sidebar that meets it, a
bottom nav that grows with the phone's inset, and a page that pads for it.

Every number here is a class token, and the tokens are one fact each:

- The navbar's box is ``h-14`` (3.5rem) INCLUDING its bottom border, so the
  desktop sidebar's ``top-14`` meets it exactly and the chat pages'
  ``calc(100vh - 3.5rem)`` fills the rest — a strip or an overlap is what an
  inner-row height plus a wrapper border produces.
- The sidebar content column has no viewport-derived min-height: below lg it
  shares the viewport with the navbar, the section row and the bottom-nav
  padding, so any ``100vh - N`` floor is phantom scroll on a short page.
- The bottom nav's ``4rem`` is a MINIMUM: it pads itself by
  ``env(safe-area-inset-bottom)``, and a fixed height would take that padding
  out of the tabs. Main content and the offline banner clear the bar with the
  same ``4rem + env()`` expression, so the three move together.
- A page header's actions wrap under the title when they do not fit beside
  it, so a wide action neither pushes the page past the viewport nor wraps
  its own label.
- No web font is named anywhere in the stylesheet source: the type is the
  host's system stack by ruling, and a declared-but-unshipped family resolves
  to a per-device fallback that makes no row measurement portable.

Real-pixel checks (the sidebar top equals the navbar bottom at 1440, no
phantom scroll on an empty phone page, the bar's content box under an
emulated inset) live in the headless-Chrome chrome gate that every chrome PR
runs; these tests pin the tokens that gate measures.
"""

from __future__ import annotations

import re
from pathlib import Path

from fasthtml.common import Div, to_xml

from tests.unit.ui.test_vendored_asset_pins import precache_urls
from ui.layouts.base_page import BasePage, build_head
from ui.layouts.navbar import create_bottom_nav, create_navbar
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage

APP_ROOT = Path(__file__).resolve().parents[3]
STATIC = APP_ROOT / "static"

BOTTOM_NAV_CLEARANCE = "calc(4rem+env(safe-area-inset-bottom))"


def _opening_tag(html: str, pattern: str) -> str:
    match = re.search(pattern, html)
    assert match is not None, f"no tag matches {pattern!r}"
    return match.group(0)


def _classes(tag: str) -> list[str]:
    """The static class list — never Alpine's ``:class`` expression."""
    match = re.search(r'(?<![:\w-])class="([^"]*)"', tag)
    assert match is not None, f"no class attribute in {tag!r}"
    return match.group(1).split()


# --- navbar ------------------------------------------------------------------


def _navbar_tags(html: str) -> tuple[str, str]:
    """The sticky wrapper's opening tag and its first inner row's."""
    wrapper = _opening_tag(html, r"<(?:nav|div)[^>]*sticky top-0[^>]*>")
    inner = _opening_tag(html, r"<div[^>]*class=\"flex items-center h-[^\"]*\"[^>]*>")
    return wrapper, inner


def test_the_navbar_box_is_h14_border_included_for_every_role() -> None:
    for html in (
        to_xml(create_navbar(current_user="user_mike", is_authenticated=True)),
        to_xml(create_navbar(current_user="admin", is_authenticated=True, is_admin=True)),
        to_xml(create_navbar(is_authenticated=False)),
    ):
        wrapper, inner = _navbar_tags(html)
        assert "h-14" in _classes(wrapper)
        assert "border-b" in _classes(wrapper)
        assert "h-full" in _classes(inner)
        assert "h-14" not in _classes(inner)


# --- desktop sidebar ---------------------------------------------------------


def _sidebar_page() -> str:
    return to_xml(
        SidebarPage(
            title="Tasks+",
            items=[SidebarItem("Today", "/today", "today", icon="sun")],
            content=Div("body"),
            active="today",
        )
    )


def test_the_desktop_sidebar_starts_where_the_navbar_ends() -> None:
    html = _sidebar_page()
    aside = _opening_tag(html, r"<nav[^>]*aria-label=\"Tasks\+ sidebar\"[^>]*>")
    classes = _classes(aside)
    assert "fixed" in classes
    assert "top-14" in classes
    assert not any(c.startswith("top-") and c != "top-14" for c in classes)


def test_the_sidebar_content_column_has_no_viewport_min_height() -> None:
    html = _sidebar_page()
    column = _opening_tag(html, r"<div[^>]*id=\"sidebar-content\"[^>]*>")
    assert not any(c.startswith("min-h-") for c in _classes(column))
    assert "100vh" not in html


# --- bottom nav + the page that clears it -----------------------------------


def test_the_bottom_nav_height_is_a_minimum_padded_by_the_inset() -> None:
    tag = _opening_tag(to_xml(create_bottom_nav(is_authenticated=True)), r"<nav[^>]*>")
    classes = _classes(tag)
    assert "min-h-16" in classes
    assert "h-16" not in classes
    assert 'style="padding-bottom: env(safe-area-inset-bottom)"' in tag


def _authed_page(**kwargs: object) -> str:
    return to_xml(BasePage(Div("body"), is_authenticated=True, **kwargs))  # type: ignore[arg-type]


def test_main_and_the_offline_banner_clear_the_bar_by_the_same_expression() -> None:
    html = _authed_page()
    main = _opening_tag(html, r"<main[^>]*>")
    banner = _opening_tag(html, r"<div[^>]*x-data=\"offlineIndicator\"[^>]*>")
    assert f"pb-[{BOTTOM_NAV_CLEARANCE}]" in _classes(main)
    assert "sm:pb-0" in _classes(main)
    assert f"bottom-[{BOTTOM_NAV_CLEARANCE}]" in _classes(banner)
    assert "sm:bottom-0" in _classes(banner)
    assert "pb-16" not in html
    assert "bottom-16" not in html


def test_every_viewer_gets_the_bar_and_the_clearance() -> None:
    """The bar renders for every role and for an anonymous visitor, so the
    page always clears it — there is no viewer without a bar to pad for."""
    for html in (
        _authed_page(is_admin=True),
        to_xml(BasePage(Div("body"), is_authenticated=False)),
    ):
        assert 'aria-label="Primary navigation"' in html
        assert f"pb-[{BOTTOM_NAV_CLEARANCE}]" in _classes(_opening_tag(html, r"<main[^>]*>"))


# --- page header --------------------------------------------------------------


def test_page_header_actions_wrap_under_the_title_when_they_do_not_fit() -> None:
    html = to_xml(PageHeader("GradeBook", subtitle="sub", actions=Div("act")))
    row = _opening_tag(html, r"<div[^>]*class=\"flex flex-wrap[^\"]*\"[^>]*>")
    classes = _classes(row)
    assert "justify-between" in classes
    assert "gap-y-3" in classes


# --- deleted focus_trap.js ---------------------------------------------------


def test_no_focus_trap_script_is_served_or_precached() -> None:
    assert not (STATIC / "js" / "focus_trap.js").exists()
    assert "focus_trap" not in to_xml(build_head("SKUEL"))
    assert not any("focus_trap" in url for url in precache_urls())


# --- fonts ---------------------------------------------------------------------


def test_the_stylesheet_names_no_web_font() -> None:
    """A quoted family in a font declaration is a web font: none is shipped."""
    for sheet in ("input.css", "main.css"):
        source = (STATIC / "css" / sheet).read_text(encoding="utf-8")
        for match in re.finditer(r"(?:--font-\w+|font-family)\s*:\s*([^;]+);", source):
            assert "'" not in match.group(1) and '"' not in match.group(1), (
                f"{sheet}: {match.group(0)} names a font that is not shipped"
            )
