"""The top bar: every item a direct link, one sign-out door per width.

The navbar renders on every page, so what it carries is a global contract:
no dropdown (the periodic notes are reached from the Tasks+ sidebar's Journal
row and, inside a note, the period rail — never from the chrome), and sign-out
present exactly once at any viewport width — the desktop icon and the phone's
``/profile`` row trade places at the same breakpoint.
"""

import re

from fasthtml.common import to_xml

from ui.layouts.navbar import create_navbar
from ui.profile.hub import ProfileHubView


def _authed_navbar() -> str:
    return to_xml(create_navbar(current_user="user_mike", is_authenticated=True))


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
