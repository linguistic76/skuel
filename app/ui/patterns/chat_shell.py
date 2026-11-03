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

**Side panel.** The right-hand twin of the sidebar, for a page that has one (the Journals
upload panel): 320px in the row at ``lg`` and up, always shown. Below ``lg`` it leaves the
row and the chat takes the width; the page's toggle button (:func:`chat_side_panel_toggle`,
shown only below ``lg``) opens it as an overlay from the right, and a tap outside it or
Escape closes it. Opening one overlay closes the other: a tap on either's door is outside
the other. The page's Alpine root owns ``panelOpen``, seeded ``false`` and not remembered.
The root carries ``relative``, the overlay's containing block.
"""

from typing import Any

from fasthtml.common import FT, Div

from ui.alpine import js_literal

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
) -> FT:
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


# The side panel's id, which its toggle names in aria-controls, and the attribute that marks
# the toggle: the toggle sits outside the panel, so the panel's tap-outside close must not
# count a tap on it — the toggle itself opens and closes the panel.
_PANEL_ID = "chat-side-panel"
_PANEL_TOGGLE = "data-chat-panel-toggle"


def chat_side_panel_toggle() -> dict[str, str | bool]:
    """The attributes of the button that opens and closes the side panel below ``lg``.
    The button itself carries ``lg:hidden``: at ``lg`` the panel is always in the row."""
    return {
        "@click": "panelOpen = !panelOpen",
        "aria-expanded": "false",
        ":aria-expanded": "panelOpen",
        "aria-controls": _PANEL_ID,
        _PANEL_TOGGLE: True,
    }


def chat_side_panel(
    content: list[Any],  # boundary: fasthtml-elements
    closes_on_swap_into: str | None = None,
) -> FT:
    """The side panel frame around a page's ``content`` (a list of children).

    ``closes_on_swap_into`` names the element id whose htmx swap closes the panel: a
    panel whose work lands in the chat (a processed upload) closes onto the result.
    A swap anywhere else (the panel's own status line) leaves it open."""
    close_overlay = f"if (panelOpen && !{_WIDE}) panelOpen = false"
    on_swap = (
        {
            "@htmx:after-swap.window": (
                f"if ($event.detail.target.id === {js_literal(closes_on_swap_into)})"
                " panelOpen = false"
            )
        }
        if closes_on_swap_into is not None
        else {}
    )
    return Div(
        Div(*content, cls="h-full overflow-y-auto p-4 bg-muted/50"),
        id=_PANEL_ID,
        # Opaque, with the tint on the child, for the same reason as the sidebar: below lg
        # the panel floats over the chat. It is hidden below lg until it is open — a class,
        # not x-show, so it is in the row at lg whatever the state, and closed on a phone
        # before Alpine runs. The panel stays in the DOM either way (its forms bind by id).
        # It never covers the rail, so on the narrowest phone there is still a door to tap.
        cls=(
            "w-[320px] shrink-0 border-l border-muted bg-background"
            " max-lg:absolute max-lg:inset-y-0 max-lg:right-0 max-lg:z-30 max-lg:shadow-xl"
            " max-lg:max-w-[calc(100%-62px)] max-lg:hidden max-lg:data-open:block"
        ),
        **{
            ":data-open": "panelOpen",
            "@click.outside": f"if (!$event.target.closest('[{_PANEL_TOGGLE}]')) {{ {close_overlay} }}",
            "@keydown.escape.window": close_overlay,
            **on_swap,
        },
    )


__all__ = [
    "CHAT_SHELL_HEIGHT",
    "CHAT_SIDEBAR_WIDE_QUERY",
    "chat_side_panel",
    "chat_side_panel_toggle",
    "chat_sidebar",
    "chat_sidebar_open_default",
    "chat_sidebar_set",
]
