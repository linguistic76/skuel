from typing import Any

from fasthtml.common import I

from ui.components._util import _cls

__all__ = ["Icon"]


def Icon(name: str, cls: str = "", size: int = 16, **kwargs: Any) -> Any:
    """Lucide icon rendered via the data-lucide attribute.

    Requires lucide.js in page headers and lucide.createIcons() called after DOM
    is ready (wired in skuel.js via alpine:initialized and htmx:afterSwap events).

    Args:
        name: Lucide icon name (e.g. "check", "x", "chevron-down").
        cls: Additional Tailwind classes (e.g. size overrides, color utilities).
        size: Icon dimension in pixels. Emits w-[Npx] h-[Npx] by default.
              Pass cls="w-4 h-4" directly when you want standard Tailwind sizes
              to keep those classes in the scanner's static pass.
        **kwargs: Any HTML attribute passes through.
    """
    dim = f"w-[{size}px] h-[{size}px]"
    return I(data_lucide=name, cls=_cls(dim, cls), **kwargs)
