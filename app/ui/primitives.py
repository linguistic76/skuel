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

from ui.components import ButtonT, Icon
from ui.components._util import _cls
from ui.components.button import _BTN_BASE, _BTN_SIZES

# Default subtitle class for option rows (description text)
_SUBTITLE_CLS = "block text-[12.5px] text-muted-foreground mt-[6px] leading-[1.35]"


def safe_external_url(url: str | None) -> str | None:
    """Return ``url`` only if it uses an allowlisted external scheme.

    Data-sourced URLs (e.g. Resource ``source_url`` from vault descriptors)
    must never reach an ``href`` unfiltered — a ``javascript:`` or ``data:``
    value would become stored XSS on click. Only http/https survive; anything
    else (including scheme-relative and whitespace tricks) returns None so the
    caller renders plain text instead of a link.
    """
    if not url:
        return None
    normalized = url.strip().lower()
    if normalized.startswith(("http://", "https://")):
        return url.strip()
    return None


def icon_tile(
    icon: str, bg_cls: str, icon_cls: str, size: str = "md"
) -> Any:  # boundary: fasthtml-elements
    """Rounded semantic icon tile.

    Args:
        icon:     Icon name (see ``ui/components/icon.py``).
        bg_cls:   Background class, e.g. ``"bg-blue-50"``.
        icon_cls: Icon colour class, e.g. ``"text-blue-600"``.
        size:     ``"md"`` (34×34, default) or ``"lg"`` (42×42).
    """
    dims = "w-[34px] h-[34px] rounded-[8px]" if size == "md" else "w-[42px] h-[42px] rounded-[10px]"
    return Div(
        Icon(icon, cls=f"w-[18px] h-[18px] {icon_cls}"),
        cls=f"{dims} flex-none flex items-center justify-center {bg_cls}",
    )


_SECTION_LABEL_CLS = (
    "block text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-[9px]"
)


def section_label(
    text: str,
    *,
    tag: Any = P,  # boundary: fasthtml-elements
    id: str | None = None,
    cls: str = "",
) -> Any:  # boundary: fasthtml-elements
    """Uppercase tracking section divider label.

    Args:
        text: Label copy.
        tag:  Element constructor — ``P`` (default) or ``H2`` for section
              headings that anchor in-page links.
        id:   Anchor id, for headings targeted by a ``#fragment`` link.
        cls:  Extra classes appended to the base style (e.g. ``"mt-[18px]"``).
    """
    attrs: dict[str, str] = {"id": id} if id is not None else {}
    attrs["cls"] = f"{_SECTION_LABEL_CLS} {cls}".strip()
    return tag(text, **attrs)


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
        Icon(icon, cls="w-4 h-4 flex-none"),
        Span(label, cls="btn-label"),
        cls=f"{base} {cls}".strip(),
        **kwargs,
    )


def card_row(*content: Any, cls: str = "") -> Any:  # boundary: fasthtml-elements
    """Flex row with gap-[13px] — standard icon-tile + text content row."""
    extra = f" {cls}" if cls else ""
    return Div(*content, cls=f"flex items-center gap-[13px]{extra}")


def dropdown_separator() -> Any:  # boundary: fasthtml-elements
    """Thin divider for compact dropdown menus."""
    return Div(cls="h-px bg-slate-100 my-1 mx-2")


def dropdown_menu(
    *content: Any, cls: str = "", **kwargs: Any
) -> Any:  # boundary: fasthtml-elements
    """Canonical floating menu shell for custom Alpine dropdowns."""
    base = (
        "absolute top-[calc(100%+6px)] left-0 right-0 z-30 "
        "bg-card border border-border rounded-[13px] p-[6px] flex flex-col gap-[3px] "
        "shadow-[0_12px_32px_rgba(15,23,42,0.13)]"
    )
    return Div(*content, cls=f"{base} {cls}".strip(), **kwargs)


def ButtonLink(
    *c: Any,
    href: str,
    cls: str | tuple = ButtonT.default,
    size: str = "md",
    **kwargs: Any,
) -> Any:  # boundary: fasthtml-elements
    """A-element styled as a SKUEL button.

    Pass a ButtonT style variant as cls (e.g. ``cls=ButtonT.ghost``) and
    use size= for geometry (``"xs"``, ``"sm"``, ``"md"``, ``"lg"``, ``"xl"``).
    Tuple cls is accepted for backward compatibility during the M4 migration.
    """
    size_cls = _BTN_SIZES.get(size, _BTN_SIZES["md"])
    return A(*c, href=href, cls=_cls(_BTN_BASE, size_cls, cls), **kwargs)


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
        icon: Icon name for the tile (see ``ui/components/icon.py``).
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
        Icon("check", cls="w-4 h-4 text-blue-600"),
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


def UploadDropzone(
    title: str,
    hint: Any,
    *,
    icon: str = "upload",
    show_expr: str,
    click_handler: str,
    dragover_handler: str | None = None,
    drop_handler: str | None = None,
    dragleave_handler: str | None = None,
    active_expr: str | None = None,
    cls: str = "",
) -> Any:  # boundary: fasthtml-elements
    """Canonical empty file-upload target with optional drag state bindings."""
    attrs: dict[str, Any] = {
        "x-show": show_expr,
        "@click": click_handler,
    }
    if dragover_handler:
        attrs["@dragover"] = dragover_handler
    if drop_handler:
        attrs["@drop"] = drop_handler
    if dragleave_handler:
        attrs["@dragleave"] = dragleave_handler
    if active_expr:
        attrs[":class"] = f"{active_expr} ? 'border-blue-600 bg-blue-50' : ''"

    base = (
        "border-[1.5px] border-dashed border-slate-300 rounded-[12px] bg-slate-50 "
        "px-6 py-[34px] text-center cursor-pointer flex flex-col items-center gap-1 "
        "hover:border-blue-600 hover:bg-blue-50 transition-colors"
    )
    hint_content = hint if isinstance(hint, tuple) else (hint,)
    return Div(
        Div(
            Icon(icon, cls="w-6 h-6 text-blue-600"),
            cls=(
                "w-[46px] h-[46px] rounded-[12px] border border-border bg-background "
                "flex items-center justify-center mb-3"
            ),
        ),
        P(title, cls="text-[14.5px] font-semibold text-foreground mb-1"),
        P(*hint_content, cls="text-[13px] text-muted-foreground"),
        cls=f"{base} {cls}".strip(),
        **attrs,
    )


def SelectedFileCard(
    *,
    file_name_expr: str,
    meta: str | None = None,
    meta_expr: str | None = None,
    show_expr: str,
    replace_handler: str,
    remove_handler: str,
    replace_label: str = "Replace",
    cls: str = "",
) -> Any:  # boundary: fasthtml-elements
    """Canonical filled file-upload state with replace and remove actions."""
    meta_attrs = {"x-text": meta_expr} if meta_expr else {}
    base = "flex items-center gap-[14px] px-4 py-[14px] border border-border rounded-[12px] bg-card"
    return Div(
        Div(
            Icon("file-text", cls="w-5 h-5 text-blue-600"),
            cls="w-[42px] h-[42px] rounded-[10px] bg-blue-50 flex items-center justify-center flex-none",
        ),
        Div(
            Span(
                cls="block text-sm font-semibold text-foreground truncate leading-snug",
                **{"x-text": file_name_expr},
            ),
            Span(
                meta or "",
                cls="block text-xs text-slate-400 font-mono mt-[2px]",
                **meta_attrs,
            ),
            cls="flex-1 min-w-0",
        ),
        Button(
            replace_label,
            type="button",
            cls=(
                "flex-none border border-border rounded-[8px] px-3 py-[7px] "
                "text-[13px] font-semibold bg-card text-foreground cursor-pointer "
                "hover:bg-slate-50 transition-colors"
            ),
            **{"@click": replace_handler},
        ),
        Button(
            Icon("x", cls="w-4 h-4"),
            type="button",
            cls=(
                "flex-none w-8 h-8 rounded-[8px] border-0 bg-transparent "
                "text-slate-400 cursor-pointer flex items-center justify-center "
                "hover:bg-slate-100 hover:text-slate-600 transition-colors"
            ),
            **{"@click": remove_handler},
        ),
        cls=f"{base} {cls}".strip(),
        **{"x-show": show_expr},
        **{"x-cloak": True},
    )
