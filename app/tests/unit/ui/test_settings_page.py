"""/settings — the account page, and below the desktop widths the chrome's overflow.

The sign-out row (below sm) and the role-gated doors (below lg) render
first, in the page shell, outside any HTMX fragment or ``x-cloak``: an admin
or teacher on a phone or tablet reaches /admin and /teaching/* from here and
nowhere else, and signing out never waits for the preferences fragment or
for Alpine.
"""

from __future__ import annotations

import re

import pytest
from fasthtml.common import to_xml

from core.utils.auth_context import AuthState, auth_state_var
from ui.settings import render_settings_page


def _page(*, is_admin: bool = False, is_teacher: bool = False) -> str:
    token = auth_state_var.set(
        AuthState(user_uid="user_x", is_admin=is_admin, is_teacher=is_teacher)
    )
    try:
        return to_xml(render_settings_page(request=None))  # type: ignore[arg-type]
    finally:
        auth_state_var.reset(token)


def _main(html: str) -> str:
    match = re.search(r"<main[^>]*>.*</main>", html, re.DOTALL)
    assert match is not None
    return match.group(0)


def test_signout_is_the_first_thing_in_the_page_and_not_in_a_fragment() -> None:
    main = _main(_page())
    first_link = re.search(r"<a[^>]*>", main)
    assert first_link is not None
    assert 'href="/logout"' in first_link.group(0)
    assert "sm:hidden" in first_link.group(0)
    before_row = main[: first_link.start()]
    assert "x-cloak" not in before_row
    assert "hx-get" not in before_row


def test_the_preferences_still_load_as_a_fragment() -> None:
    assert 'hx-get="/settings/content"' in _page()
    assert 'href="/settings/devices"' in _page()


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({}, []),
        ({"is_teacher": True}, ["/teaching/students"]),
        ({"is_admin": True, "is_teacher": True}, ["/teaching/students", "/admin"]),
    ],
)
def test_the_role_rows_are_below_lg_doors_gated_like_the_centre_links(
    flags: dict[str, bool], expected: list[str]
) -> None:
    main = _main(_page(**flags))
    rows = [
        tag
        for tag in re.findall(r"<a[^>]*>", main)
        if re.search(r'href="(/admin|/teaching/students)"', tag)
    ]
    assert [re.search(r'href="([^"]*)"', r).group(1) for r in rows] == expected  # type: ignore[union-attr]
    assert all("lg:hidden" in r for r in rows)


def test_the_page_lights_the_avatar() -> None:
    avatar = re.search(r'<a[^>]*href="/settings"[^>]*>', _page())
    assert avatar is not None and 'aria-current="page"' in avatar.group(0)
