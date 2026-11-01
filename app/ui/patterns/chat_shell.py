"""The chat pages' shell: Journals and Askesis.

**Height.** The shell fills the screen between the top navbar (3.5rem) and, below
``sm``, the phone bottom nav (4rem plus the home-indicator inset), so the composer sits
above the bottom nav instead of under it.

**Sidebar.** One frame, two states: the open **panel** (274px: the page's header,
new-chat door, history, identity) and the closed **rail** (62px: expand, new chat, the
avatar).

- At ``lg`` and up the sidebar sits in the row and pushes the chat: 274px open, 62px
  closed, and it opens by default.
- Below ``lg`` it opens closed. The rail keeps its 62px slot in the row, and the open
  panel overlays the chat instead of taking its width. A tap outside the panel or
  Escape closes it.

The page's Alpine root owns ``sidebarOpen``; seed it with :func:`chat_sidebar_open_default`
so a phone starts on the rail.
"""

from typing import Any

from fasthtml.common import Div

# The shell's height: the viewport less the top navbar, and below sm the bottom nav too
# (BasePage pads main by the bottom nav's height there, so the page never scrolls).
CHAT_SHELL_HEIGHT = (
    "h-[calc(100dvh-(7.5rem+env(safe-area-inset-bottom)))] sm:h-[calc(100dvh-3.5rem)]"
)

# The breakpoint below which the open panel overlays the chat (Tailwind's ``lg``).
CHAT_SIDEBAR_WIDE_QUERY = "(min-width: 1024px)"
_WIDE = f"window.matchMedia('{CHAT_SIDEBAR_WIDE_QUERY}').matches"


def chat_sidebar_open_default(remembered_key: str | None = None) -> str:
    """The JS expression that seeds ``sidebarOpen``: open on a wide screen, closed on a
    phone. With ``remembered_key``, a wide screen honours the localStorage choice
    :func:`chat_sidebar_set` remembered under that key."""
    if remembered_key is None:
        return _WIDE
    return f"{_WIDE} && localStorage.getItem('{remembered_key}') !== 'false'"


def chat_sidebar_set(open_: bool, remembered_key: str | None = None) -> str:
    """The ``@click`` expression that opens or closes the sidebar. A choice made on a
    wide screen is remembered under ``remembered_key``; one made on a phone is not, so
    closing the overlay never collapses the sidebar on the desktop."""
    value = "true" if open_ else "false"
    if remembered_key is None:
        return f"sidebarOpen = {value}"
    return (
        f"sidebarOpen = {value}; if ({_WIDE}) localStorage.setItem('{remembered_key}', '{value}')"
    )


def chat_sidebar(
    panel: list[Any],  # boundary: fasthtml-elements
    rail: list[Any],  # boundary: fasthtml-elements
) -> Div:
    """The sidebar frame around a page's ``panel`` and ``rail`` (each a list of children)."""
    close_overlay = f"if (sidebarOpen && !{_WIDE}) sidebarOpen = false"
    return Div(
        Div(
            Div(*panel, cls="flex flex-col h-full bg-muted/50", **{"x-show": "sidebarOpen"}),
            Div(
                *rail,
                cls="flex flex-col items-center gap-3 py-3 px-2 h-full bg-muted/50",
                **{"x-show": "!sidebarOpen", "x-cloak": True},
            ),
            # The sidebar is opaque and its panel and rail carry the tint: below lg the open
            # panel floats over the chat, and a translucent wash would show the chat through.
            # Before Alpine runs, the width is the default state's: the rail on a phone,
            # the panel on a wide screen. Alpine's :style then takes over.
            style="width: var(--chat-sidebar-w);",
            cls=(
                "[--chat-sidebar-w:62px] lg:[--chat-sidebar-w:274px] h-full bg-background"
                " border-r border-muted overflow-hidden transition-[width] duration-300"
                " max-lg:absolute max-lg:inset-y-0 max-lg:left-0 max-lg:z-30"
            ),
            **{
                ":style": "{ width: sidebarOpen ? '274px' : '62px' }",
                ":class": "sidebarOpen ? 'max-lg:shadow-xl' : ''",
                "@click.outside": close_overlay,
                "@keydown.escape.window": close_overlay,
            },
        ),
        # The slot holds the rail's width in the row below lg, so the chat never moves
        # when the panel opens over it; at lg the sidebar itself sets the width.
        cls="relative shrink-0 w-[62px] lg:w-auto",
    )


__all__ = [
    "CHAT_SHELL_HEIGHT",
    "CHAT_SIDEBAR_WIDE_QUERY",
    "chat_sidebar",
    "chat_sidebar_open_default",
    "chat_sidebar_set",
]
