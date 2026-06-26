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

from fasthtml.common import Button, Div, P, Span
from monsterui.franken import UkIcon


def icon_tile(icon: str, bg_cls: str, icon_cls: str, size: str = "md") -> Any:
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


def section_label(text: str) -> Any:
    """Uppercase tracking section divider label."""
    return P(
        text,
        cls="block text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-[9px]",
    )


def primary_btn(label: str, icon: str = "send", cls: str = "", **kwargs: Any) -> Any:
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


def card_row(*content: Any, cls: str = "") -> Any:
    """Flex row with gap-[13px] — standard icon-tile + text content row."""
    extra = f" {cls}" if cls else ""
    return Div(*content, cls=f"flex items-center gap-[13px]{extra}")
