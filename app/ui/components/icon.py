from typing import Any

from fasthtml.common import NotStr

from ui.components._icon_data import ICON_PATHS
from ui.components._util import _cls

__all__ = ["Icon"]

# Constant lucide SVG shell — geometry (the inner <path>/<circle>) comes from ICON_PATHS.
_FALLBACK = "help-circle"


def Icon(name: str, cls: str = "", size: int = 16, **kwargs: Any) -> Any:
    """Lucide icon rendered as server-side inline SVG.

    The icon geometry is emitted directly into the HTML from the generated
    ``ICON_PATHS`` registry (``scripts/gen_icons.py``), so icons render with no
    client-side JS — no ``lucide.createIcons()`` scan and no MutationObserver.

    Sizing: the default ``size`` is applied via the SVG ``width``/``height``
    *attributes*, NOT a ``w-[Npx]`` class. A width/height utility in ``cls``
    (``w-6 h-6``, ``size-5``) therefore always wins — a CSS class overrides a
    presentational attribute — so ``cls`` sizing and the ``size`` default never
    fight over Tailwind's class-order cascade.

    Args:
        name: Lucide icon name (e.g. "check", "x", "chevron-down"). Unknown names
              fall back to a visible "help-circle" rather than rendering blank.
        cls: Additional Tailwind classes (size overrides, color utilities).
        size: Default icon dimension in pixels (used when ``cls`` carries no size util).
        **kwargs: Extra HTML attributes, rendered as ``key="value"`` on the <svg>.
    """
    inner = ICON_PATHS.get(name) or ICON_PATHS[_FALLBACK]
    classes = _cls(cls)
    class_attr = f' class="{classes}"' if classes else ""
    extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in kwargs.items())
    # boundary: fasthtml-elements — inline SVG snippet (not a full document); NotStr
    # passes the markup through unescaped so the <path> geometry renders.
    return NotStr(
        f'<svg{class_attr} width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true"{extra}>{inner}</svg>'
    )
