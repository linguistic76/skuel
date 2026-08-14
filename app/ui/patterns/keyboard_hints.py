"""Keyboard-hint strip pattern — the bottom "j/k move · ↵ open" bar.

One chip + bar style for every page with keyboard shortcuts (Today board,
Explore reading plan), replacing per-page copies that had drifted in kbd chip
styling and padding.

The bar is hidden on coarse-pointer (touch) devices, where the shortcuts
can't be typed. Gated with not-pointer-coarse (not pointer-fine) so that
pointer:none environments — keyboard-only users — still see the hints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, Kbd, Span

if TYPE_CHECKING:
    from fasthtml.common import FT

# Keycap chips carry the visual weight (dark text on a raised light cap);
# the bar itself stays quiet — inverse of the old ghost-on-white treatment.
_KBD_CLS = (
    "px-1.5 py-0.5 border border-border rounded-sm bg-card "
    "text-foreground font-medium shadow-[0_1px_0_hsl(var(--border))]"
)


def keyboard_hint(label: str, *keys: str) -> FT:
    """One hint chip group: the key caps followed by their action label."""
    return Span(*[Kbd(key, cls=_KBD_CLS) for key in keys], f" {label}")


def keyboard_hints_bar(*children: Any, cls: str = "", **attrs: Any) -> FT:
    """The hint strip container (pass ``keyboard_hint(...)`` chips + extras)."""
    base_cls = (
        "mt-8 px-4 py-3.5 bg-muted/40 border border-muted rounded-lg "
        "hidden not-pointer-coarse:flex items-center gap-6 text-xs text-muted-foreground "
        "font-mono flex-wrap"
    )
    return Div(
        *children,
        cls=f"{base_cls} {cls}".strip(),
        **attrs,
    )
