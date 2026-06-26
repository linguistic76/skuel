"""
Shared UI Primitives
=====================

Low-level building blocks that emerged from the /submit and Askesis UX redesigns.
Import these instead of duplicating the class strings across modules.

Design language reference:
- Container:  border border-border rounded-[12px] bg-card
- Selection:  bg-blue-50 (active) / hover:bg-slate-100 (hover)
- Typography: text-[14px] font-semibold (title) / text-[12.5px] text-muted-foreground (body)

See: ui/journals/forms.py, ui/user_entry/forms.py, ui/askesis/chat.py
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import A, Button, Div, P, Span
from monsterui.franken import ButtonT, UkIcon

# Default subtitle class for option rows (description text)
_SUBTITLE_CLS = "block text-[12.5px] text-muted-foreground mt-[6px] leading-[1.35]"


def icon_tile(
    icon: str, bg_cls: str, icon_cls: str, size: str = "md"
) -> Any:  # boundary: fasthtml-elements
    """Rounded semantic icon tile.

    Args:
        icon:     Lucide icon name.
        bg_cls:   Background class, e.g. ``"bg-blue-50"``.
        icon_cls: Icon colour class, e.g. ``"text-blue-600"``.
        size:     ``"md"`` (34×34, default) or ``"lg"`` (42×42).
    """
    dims = "w-[34px] h-[34px] rounded-[8px]" if size == "md" else "w-[42px] h-[42px] rounded-[10px]"
    return Div(
        UkIcon(icon, cls=f"w-[18px] h-[18px] {icon_cls}"),
        cls=f"{dims} flex-none flex items-center justify-center {bg_cls}",
    )


def section_label(text: str) -> Any:  # boundary: fasthtml-elements
    """Uppercase tracking section divider label."""
    return P(
        text,
        cls="block text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-[9px]",
    )


def primary_btn(
    label: str, icon: str = "send", cls: str = "", **kwargs: Any
) -> Any:  # boundary: fasthtml-elements
    """bg-foreground primary action button with optional leading icon.

    Pass ``type="submit"`` for form submit buttons.
    The label is wrapped in a ``.btn-label`` span so JS can swap loading text.
    """
    base = (
        "flex items-center gap-2 bg-foreground text-background text-[14px] font-semibold "
        "px-[18px] py-[11px] rounded-[9px] shadow-sm hover:opacity-90 transition-opacity"
    )
    return Button(
        UkIcon(icon, cls="w-4 h-4 flex-none"),
        Span(label, cls="btn-label"),
        cls=f"{base} {cls}".strip(),
        **kwargs,
    )


def card_row(*content: Any, cls: str = "") -> Any:  # boundary: fasthtml-elements
    """Flex row with gap-[13px] — standard icon-tile + text content row."""
    extra = f" {cls}" if cls else ""
    return Div(*content, cls=f"flex items-center gap-[13px]{extra}")


def ButtonLink(
    *c: Any,
    href: str,
    cls: str | ButtonT = ButtonT.default,
    **kwargs: Any,
) -> Any:  # boundary: fasthtml-elements
    """A-element styled as a MonsterUI button.

    Pass a ButtonT variant as cls (e.g. ``cls=ButtonT.ghost``), a tuple of
    ButtonT values (e.g. ``cls=(ButtonT.ghost, ButtonT.sm)``), or a raw
    CSS class string.
    """
    if isinstance(cls, tuple):
        cls_str = " ".join(
            f"uk-button {part}" if i == 0 else str(part) for i, part in enumerate(cls)
        )
    else:
        cls_str = f"uk-button {cls}"
    return A(*c, href=href, cls=cls_str, **kwargs)


def SelectableOptionRow(
    icon: str,
    tile_bg: str,
    icon_cls: str,
    title: str,
    subtitle: str,
    selected_expr: str,
    click_handler: str,
    *,
    disabled: bool = False,
    title_extra: Any = None,
    subtitle_cls: str = _SUBTITLE_CLS,
) -> Any:  # boundary: fasthtml-elements
    """Selectable option row: icon tile + title + subtitle + checkmark indicator.

    Active state (bg-blue-50) and hover state (bg-transparent hover:bg-slate-100)
    are canonical here — never duplicate in call sites.

    Args:
        icon: Lucide icon name for the tile.
        tile_bg: Tile background class, e.g. ``"bg-blue-50"``.
        icon_cls: Icon colour class, e.g. ``"text-blue-600"``.
        title: Primary text.
        subtitle: Secondary text beneath the title (omit for no subtitle).
        selected_expr: Alpine expression that evaluates true when selected,
            e.g. ``"processingMode === 'transcribe_only'"``.
        click_handler: Alpine @click expression, e.g. ``"selectMode('key')"``.
        disabled: Greys out the row and suppresses interaction.
        title_extra: Optional element rendered alongside the title (e.g. a badge).
        subtitle_cls: CSS for the subtitle span; override for mono filenames etc.
    """
    title_content: Any
    if title_extra is not None:
        title_content = Span(
            Span(title, cls="text-[14px] font-semibold text-foreground"),
            title_extra,
            cls="flex items-center gap-2",
        )
    else:
        title_content = Span(title, cls="text-[14px] font-semibold text-foreground")

    body = Div(
        title_content,
        Span(subtitle, cls=subtitle_cls) if subtitle else None,
        cls="flex-1 min-w-0",
    )

    base_cls = (
        "w-full flex items-start gap-3 px-3 py-[14px] rounded-[9px] border-0 "
        "text-left font-[inherit] "
    )

    if disabled:
        return Button(
            icon_tile(icon, tile_bg, icon_cls),
            body,
            type="button",
            cls=base_cls + "cursor-not-allowed opacity-70 bg-transparent",
        )

    check = Span(
        UkIcon("check", cls="w-4 h-4 text-blue-600"),
        cls="flex-none pt-[3px] flex",
        **{"x-show": selected_expr},
        **{"x-cloak": True},
    )
    return Button(
        icon_tile(icon, tile_bg, icon_cls),
        body,
        check,
        type="button",
        cls=base_cls + "cursor-pointer transition-colors",
        **{"@click": click_handler},
        **{":class": f"{selected_expr} ? 'bg-blue-50' : 'bg-transparent hover:bg-slate-100'"},
    )
