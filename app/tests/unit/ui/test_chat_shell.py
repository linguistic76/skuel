"""The chat pages' shell (``ui/patterns/chat_shell.py``): one height, one sidebar frame,
two pages.

Below ``lg`` a phone opens on the 62px rail and the open panel overlays the chat; at
``lg`` and up the sidebar pushes the chat and opens by default (Mike, 2026-11-01:
"(a)-as-overlay"). The behaviour is pinned in jsdom by tests/js/chat-shell.test.js
on the markup rendered here (tests/js/fixtures/chat-shell.html); regenerate it with
``SKUEL_WRITE_JS_FIXTURES=1 uv run pytest tests/unit/ui/test_chat_shell.py``.
"""

import os
from pathlib import Path

from fasthtml.common import Button, Div, to_xml

from ui.askesis.chat import _sidebar as askesis_sidebar
from ui.patterns.chat_shell import (
    CHAT_SHELL_HEIGHT,
    CHAT_SIDEBAR_WIDE_QUERY,
    chat_sidebar,
    chat_sidebar_open_default,
    chat_sidebar_set,
)

_APP_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE = _APP_ROOT / "tests" / "js" / "fixtures" / "chat-shell.html"
_KEY = "journal-sidebar"


def _fixture_markup() -> str:
    """A chat shell the way both pages build one: the root seeds ``sidebarOpen``, the
    frame holds a panel with the collapse button and a rail with the expand button, and
    the chat column sits beside it."""
    return to_xml(
        Div(
            chat_sidebar(
                panel=[
                    Button(
                        "close",
                        type="button",
                        aria_label="Collapse sidebar",
                        **{"@click": chat_sidebar_set(False, _KEY)},
                    )
                ],
                rail=[
                    Button(
                        "open",
                        type="button",
                        aria_label="Expand sidebar",
                        **{"@click": chat_sidebar_set(True, _KEY)},
                    )
                ],
            ),
            Div("chat", id="chat"),
            cls="flex",
            **{"x-data": f"{{ sidebarOpen: {chat_sidebar_open_default(_KEY)} }}"},
        )
    )


def test_js_fixture_matches_the_rendered_markup() -> None:
    rendered = _fixture_markup()
    if os.environ.get("SKUEL_WRITE_JS_FIXTURES") == "1":
        _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        _FIXTURE.write_text(rendered)
    assert _FIXTURE.exists() and _FIXTURE.read_text() == rendered, (
        f"{_FIXTURE} is stale — regenerate with SKUEL_WRITE_JS_FIXTURES=1 "
        "uv run pytest tests/unit/ui/test_chat_shell.py"
    )


def test_the_breakpoint_is_tailwinds_lg() -> None:
    """The query the scripts read and the ``lg:`` / ``max-lg:`` classes the frame
    carries must name the same width, or the overlay and the push overlap."""
    assert CHAT_SIDEBAR_WIDE_QUERY == "(min-width: 1024px)"
    html = _fixture_markup()
    assert "max-lg:absolute" in html
    assert "lg:w-auto" in html


def test_a_phone_opens_on_the_rail_and_a_wide_screen_remembers() -> None:
    wide = "window.matchMedia('(min-width: 1024px)').matches"
    assert chat_sidebar_open_default() == wide
    assert (
        chat_sidebar_open_default(_KEY) == f"{wide} && localStorage.getItem('{_KEY}') !== 'false'"
    )
    assert chat_sidebar_set(True) == "sidebarOpen = true"
    assert chat_sidebar_set(False, _KEY) == (
        f"sidebarOpen = false; if ({wide}) localStorage.setItem('{_KEY}', 'false')"
    )


def test_both_chat_pages_build_their_sidebar_through_the_frame() -> None:
    """The width toggle lives in one place: a page that hand-rolls its own sidebar
    again would miss the phone overlay."""
    toggle = "sidebarOpen ? '274px' : '62px'"
    holders = sorted(
        str(path.relative_to(_APP_ROOT))
        for path in (_APP_ROOT / "ui").rglob("*.py")
        if toggle in path.read_text()
    )
    assert holders == ["ui/patterns/chat_shell.py"]
    for page in ("ui/journals/chat_page.py", "ui/askesis/chat.py"):
        assert "chat_sidebar(" in (_APP_ROOT / page).read_text()


def test_askesis_new_chat_is_a_door_in_the_panel_and_on_the_rail() -> None:
    """Askesis keeps no session, so a new chat is a fresh /askesis; the rail's one-tap
    New chat is why a phone gets the rail."""
    html = to_xml(askesis_sidebar("ada", "All knowledge"))
    assert html.count('href="/askesis"') == 2


def test_both_chat_shells_fit_between_the_navbar_and_the_bottom_nav() -> None:
    """Below sm the phone bottom nav covers the last 4rem of the viewport; a shell
    sized to the viewport less the top navbar alone puts its composer under it."""
    assert "7.5rem+env(safe-area-inset-bottom)" in CHAT_SHELL_HEIGHT
    assert "sm:h-[calc(100dvh-3.5rem)]" in CHAT_SHELL_HEIGHT
    for page in ("ui/journals/chat_page.py", "ui/askesis/chat.py"):
        source = (_APP_ROOT / page).read_text()
        assert "{CHAT_SHELL_HEIGHT}" in source
        assert "100vh - 3.5rem" not in source
