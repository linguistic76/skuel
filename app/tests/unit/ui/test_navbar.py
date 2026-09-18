"""The top bar: every item a direct link, one sign-out door per width.

The navbar renders on every page, so what it carries is a global contract:
no dropdown (the periodic notes are reached from the Tasks+ sidebar's Journal
row and, inside a note, the period rail — never from the chrome), and sign-out
present exactly once at any viewport width — the desktop icon and the phone's
``/profile`` row trade places at the same breakpoint.
"""

import re

from fasthtml.common import to_xml

from ui.layouts.navbar import create_bottom_nav, create_navbar
from ui.profile.hub import ProfileHubView


def _authed_navbar() -> str:
    return to_xml(create_navbar(current_user="user_mike", is_authenticated=True))


def _authed_bottom_nav() -> str:
    return to_xml(create_bottom_nav(is_authenticated=True))


def test_navbar_carries_no_periodic_note_door() -> None:
    """Two doors to the same note drift apart; the sidebar and the in-note
    rail are the doors, so the chrome links to no journal."""
    html = _authed_navbar()
    assert "/journals/" not in html
    assert "aria-expanded" not in html


def _logout_tag(html: str) -> str:
    """The opening ``<a ... href="/logout" ...>`` tag, with its classes."""
    match = re.search(r"<a[^>]*href=\"/logout\"[^>]*>", html)
    assert match is not None, "no sign-out link rendered"
    return match.group(0)


def test_signout_is_desktop_only_and_profile_carries_the_phone_door() -> None:
    """Sign-out gives way on the phone — an account action belongs on the
    profile page — and /profile picks it up at exactly the width it disappears."""
    assert "hidden sm:inline-flex" in _logout_tag(_authed_navbar())
    assert "sm:hidden" in _logout_tag(to_xml(ProfileHubView()))


def test_submissions_is_a_nav_item_and_search_is_not() -> None:
    """Submissions is reached from the chrome at every width — a desktop
    center link and a bottom-nav tab, both from the one ``ICON_NAV_ITEMS``
    spec — and the search page is not: neither surface links to ``/search``."""
    top, bottom = _authed_navbar(), _authed_bottom_nav()
    assert 'href="/submissions"' in top
    assert 'href="/submissions"' in bottom
    assert "/search" not in top
    assert "/search" not in bottom


def test_submissions_link_highlights_across_the_section() -> None:
    """The MOC and every sub-page pass ``active_page="submissions"``, and the
    link keys on that slug — so the item is lit anywhere in the section."""
    html = to_xml(
        create_navbar(current_user="user_mike", is_authenticated=True, active_page="submissions")
    )
    match = re.search(r"<a[^>]*href=\"/submissions\"[^>]*>", html)
    assert match is not None
    assert "bg-accent text-accent-foreground" in match.group(0)
