"""One navigation, one rule — the global chrome for every role.

The navbar renders on every page, so what it carries is a global contract:

- ONE navbar for every role: no admin fork, no hamburger, no ``href="#"``.
- The section doors (``ICON_NAV_ITEMS``) render twice from one spec — the
  desktop centre links (sm+) and the phone bottom-nav tabs (<sm) — identical
  for every authenticated role; an anonymous visitor gets the two
  ``requires_auth=False`` doors, never an empty ``Div``.
- The role doors (``MAIN_NAV_ITEMS``) render twice from one spec too — the
  centre links (lg+; they do not fit beside the section doors at 640) and
  the ``lg:hidden`` rows on /settings (<lg).
- Exactly one global item lights per page, keyed by SECTION: Tasks+ on every
  Tasks+ page, the Library door on both its keys, nothing doubled.
- The chrome carries one door per section — the section's landing, which is
  also the section nav's first row: that landing is the ONE sanctioned
  overlap between the chrome and any ``*_SIDEBAR_ITEMS`` list.
- Sign-out is present exactly once at any width: the desktop icon and the
  phone's /settings row trade places at the same breakpoint.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from fasthtml.common import to_xml

from ui.layouts.nav_config import ICON_NAV_ITEMS, MAIN_NAV_ITEMS
from ui.layouts.navbar import create_bottom_nav, create_navbar, role_nav_rows, signout_row

_UI_ROOT = Path(__file__).resolve().parents[3] / "ui"

_ROLES: dict[str, dict[str, bool]] = {
    "member": {},
    "teacher": {"is_teacher": True},
    "admin": {"is_admin": True, "is_teacher": True},
}


def _navbar(active_page: str = "", **role: bool) -> str:
    return to_xml(
        create_navbar(
            current_user="user_mike", is_authenticated=True, active_page=active_page, **role
        )
    )


def _bottom_nav(active_page: str = "", is_authenticated: bool = True) -> str:
    return to_xml(create_bottom_nav(is_authenticated=is_authenticated, active_page=active_page))


def _links(html: str, container: str) -> list[str]:
    """Opening ``<a>`` tags inside the first element matching ``container``."""
    match = re.search(container + r".*?</(?:nav|div)>", html, re.DOTALL)
    assert match is not None, f"no {container!r} in the chrome"
    return re.findall(r"<a[^>]*>", match.group(0))


def _centre_links(html: str) -> list[str]:
    return _links(html, r'<div class="hidden sm:flex[^"]*"[^>]*>')


def _tabs(html: str) -> list[str]:
    return _links(html, r'<nav aria-label="Primary navigation"[^>]*>')


def _href(tag: str) -> str:
    match = re.search(r'href="([^"]*)"', tag)
    assert match is not None, tag
    return match.group(1)


def _lit(tags: list[str]) -> list[str]:
    return [_href(t) for t in tags if 'aria-current="page"' in t]


# --- one navbar, no fork -----------------------------------------------------


@pytest.mark.parametrize("role", list(_ROLES))
def test_every_role_gets_the_same_navbar_shape(role: str) -> None:
    """No admin branch: the brand, the centre links and the icon cluster
    render for an admin exactly as for a member; no hamburger, no ``#``."""
    html = _navbar(**_ROLES[role])
    assert 'href="/explore"' in html
    assert 'aria-label="Main navigation"' in html
    assert [_href(t) for t in _centre_links(html)][: len(ICON_NAV_ITEMS)] == [
        item.href for item in ICON_NAV_ITEMS
    ]
    assert 'href="#"' not in html
    assert "mobileMenuOpen" not in html
    assert 'href="/settings"' in html
    assert 'href="/askesis"' in html


def test_the_role_doors_are_centre_links_gated_by_role() -> None:
    member = [_href(t) for t in _centre_links(_navbar())]
    teacher = [_href(t) for t in _centre_links(_navbar(**_ROLES["teacher"]))]
    admin = [_href(t) for t in _centre_links(_navbar(**_ROLES["admin"]))]
    assert "/teaching/students" not in member and "/admin" not in member
    assert "/teaching/students" in teacher and "/admin" not in teacher
    assert "/teaching/students" in admin and "/admin" in admin


def test_the_role_doors_are_settings_rows_from_the_same_spec() -> None:
    """Below lg the role doors are hidden from the centre, so the /settings
    rows are the role doors — the same items, the same gate, each surface
    hidden exactly where the other shows (``hidden lg:block`` ↔ ``lg:hidden``)."""
    role_hrefs = {item.href for item in MAIN_NAV_ITEMS}
    for role, flags in _ROLES.items():
        rows = [
            to_xml(r)
            for r in role_nav_rows(
                is_admin=flags.get("is_admin", False), is_teacher=flags.get("is_teacher", False)
            )
        ]
        centre = [t for t in _centre_links(_navbar(**flags)) if _href(t) in role_hrefs]
        assert [_href(r) for r in rows] == [_href(t) for t in centre], role
        assert all("hidden lg:block" in t for t in centre), role
        assert all("lg:hidden" in r and "sm:hidden" not in r for r in rows), role


# --- the section doors: one spec, both surfaces -------------------------------


@pytest.mark.parametrize("role", list(_ROLES))
def test_the_bottom_nav_is_four_identical_tabs_for_every_authenticated_role(role: str) -> None:
    tabs = _tabs(_bottom_nav())
    assert [_href(t) for t in tabs] == [item.href for item in ICON_NAV_ITEMS]
    assert len(tabs) == 4
    # The label is the accessible name — no sr-only "Go to X" doubling it.
    assert "Go to " not in _bottom_nav()
    # The same four as the centre links, in the same order.
    centre = [_href(t) for t in _centre_links(_navbar(**_ROLES[role]))]
    assert centre[: len(tabs)] == [_href(t) for t in tabs]


def test_an_anonymous_visitor_gets_the_public_doors_not_an_empty_div() -> None:
    html = _bottom_nav(is_authenticated=False)
    assert 'aria-label="Primary navigation"' in html
    assert [_href(t) for t in _tabs(html)] == [
        item.href for item in ICON_NAV_ITEMS if not item.requires_auth
    ]
    anon_top = to_xml(create_navbar(is_authenticated=False))
    assert [_href(t) for t in _centre_links(anon_top)] == [_href(t) for t in _tabs(html)]


def test_tasks_plus_is_the_first_door_and_lands_on_today() -> None:
    first = ICON_NAV_ITEMS[0]
    assert first.label == "Tasks+"
    assert first.href == "/today"
    assert first.page_keys == frozenset({"activity"})


def test_the_chrome_carries_no_calendar_or_today_door() -> None:
    """Monthly and Today are ROWS of the Tasks+ section: a Calendar or Today
    item in the chrome would be a second door to a page the section nav
    already lights. The Tasks+ door is the section's one door at every width."""
    for html in (_navbar(), _navbar(**_ROLES["admin"]), _bottom_nav()):
        assert 'href="/cal"' not in html
        assert ">Today<" not in html
        assert ">Calendar<" not in html


# --- exactly one lit item per page, keyed by section --------------------------


def _every_key() -> set[str]:
    keys = {key for item in ICON_NAV_ITEMS for key in item.page_keys}
    return keys | {item.page_key for item in MAIN_NAV_ITEMS}


@pytest.mark.parametrize("key", sorted(_every_key()))
def test_each_section_key_lights_exactly_one_door_per_surface(key: str) -> None:
    html = _navbar(key, **_ROLES["admin"])
    lit_centre = _lit(_centre_links(html))
    assert len(lit_centre) == 1, (key, lit_centre)
    lit_tabs = _lit(_tabs(_bottom_nav(key)))
    is_icon_key = any(key in item.page_keys for item in ICON_NAV_ITEMS)
    assert lit_tabs == (lit_centre if is_icon_key else []), (key, lit_tabs)


def test_the_library_door_lights_on_both_its_keys() -> None:
    """Its landing (/explore/library) lights ``explore``; /library/* lights
    ``library`` — under a single key the tab never lit on its own landing."""
    for key in ("explore", "library"):
        assert _lit(_centre_links(_navbar(key))) == ["/explore/library"], key
        assert _lit(_tabs(_bottom_nav(key))) == ["/explore/library"], key


@pytest.mark.parametrize("key", ["today", "calendar", "tasks", "gradebook", "journals", "profile"])
def test_a_page_slug_lights_no_global_door(key: str) -> None:
    """Rows light by slug, doors by section: a slug is not a section key."""
    assert _lit(_centre_links(_navbar(key))) == []
    assert _lit(_tabs(_bottom_nav(key))) == []


def test_the_avatar_opens_settings_and_lights_there() -> None:
    lit = re.search(r'<a[^>]*href="/settings"[^>]*>', _navbar("settings"))
    assert lit is not None and 'aria-current="page"' in lit.group(0)
    unlit = re.search(r'<a[^>]*href="/settings"[^>]*>', _navbar("activity"))
    assert unlit is not None and "aria-current" not in unlit.group(0)
    assert 'href="/profile"' not in _navbar()


# --- the landing is the one sanctioned overlap --------------------------------


def _sidebar_item_lists() -> dict[str, list]:
    """Every ``*_SIDEBAR_ITEMS`` constant under ``ui/``, found by name so a
    new sidebar is covered the day it is written."""
    found: dict[str, list] = {}
    for path in _UI_ROOT.rglob("*.py"):
        for name in re.findall(r"^([A-Z_]+_SIDEBAR_ITEMS)\b", path.read_text(), re.MULTILINE):
            module = ".".join(path.relative_to(_UI_ROOT.parent).with_suffix("").parts)
            found[f"{module}.{name}"] = getattr(importlib.import_module(module), name)
    assert len(found) >= 8, sorted(found)
    return found


def test_beyond_the_landing_no_url_is_both_a_door_and_a_row() -> None:
    """A section door's href is the section's landing, which is also the
    section nav's first row — two levels of one navigation. Any other URL in
    both is a duplicate."""
    doors = {item.href for item in ICON_NAV_ITEMS} | {item.href for item in MAIN_NAV_ITEMS}
    for name, items in _sidebar_item_lists().items():
        overlap = {item.href for item in items} & doors
        assert overlap <= {items[0].href}, (name, overlap)


def test_every_door_that_opens_a_sidebar_opens_on_its_first_row() -> None:
    """The overlap is sanctioned only AS the landing: a door whose href sits
    in a sidebar sits in its first row."""
    doors = {item.href for item in ICON_NAV_ITEMS} | {item.href for item in MAIN_NAV_ITEMS}
    for name, items in _sidebar_item_lists().items():
        for position, item in enumerate(items):
            if item.href in doors:
                assert position == 0, (name, item.href)


# --- sign-out: one door per width --------------------------------------------


def _logout_tag(html: str) -> str:
    """The opening ``<a ... href="/logout" ...>`` tag, with its classes."""
    match = re.search(r"<a[^>]*href=\"/logout\"[^>]*>", html)
    assert match is not None, "no sign-out link rendered"
    return match.group(0)


@pytest.mark.parametrize("role", list(_ROLES))
def test_signout_is_desktop_only_and_settings_carries_the_phone_door(role: str) -> None:
    assert "hidden sm:inline-flex" in _logout_tag(_navbar(**_ROLES[role]))
    assert "sm:hidden" in _logout_tag(to_xml(signout_row()))
    assert _navbar(**_ROLES[role]).count('href="/logout"') == 1


# --- the chrome links to no journal -------------------------------------------


def test_navbar_carries_no_periodic_note_door() -> None:
    """Two doors to the same note drift apart; the sidebar and the in-note
    rail are the doors, so the chrome links to no journal."""
    html = _navbar()
    assert "/journals/" not in html
    assert "aria-expanded" not in html


def test_search_is_not_in_the_chrome() -> None:
    assert "/search" not in _navbar()
    assert "/search" not in _bottom_nav()
