from typing import Any

import fasthtml.common as fh
from fasthtml.common import Div

from ui.components._util import _cls

__all__ = ["Accordion", "AccordionItem"]


def Accordion(
    *items: Any, cls: str = "", multiple: bool = True, **kwargs: Any
) -> Any:  # boundary: fasthtml-elements
    """Container for AccordionItem children.

    Args:
        *items: AccordionItem elements.
        cls: Additional Tailwind classes.
        multiple: Accepted for API compatibility; each item manages its own
                  Alpine x-data state so multiple-open is always the behaviour.
        **kwargs: Any HTML attribute passes through.
    """
    return Div(*items, cls=_cls("divide-y divide-border", cls), **kwargs)


def AccordionItem(
    title: Any,
    *body: Any,
    open: bool = False,
    cls: str = "",
    title_cls: str = "",
    **kwargs: Any,
) -> Any:
    """Single accordion panel driven by Alpine.js x-data state.

    Args:
        title: Header content (str or FT element).
        *body: Panel body content.
        open: Whether the panel starts expanded.
        cls: Additional Tailwind classes for the outer wrapper.
        title_cls: Additional classes for the trigger button.
        **kwargs: Any HTML attribute passes through to the outer wrapper.
    """
    open_str = "true" if open else "false"
    btn_cls = _cls(
        "flex w-full items-center justify-between py-4 text-sm font-medium"
        " transition-all hover:underline text-left",
        title_cls,
    )
    return Div(
        fh.Button(
            title,
            cls=btn_cls,
            **{"@click": "open = !open", ":class": "open ? 'text-primary' : ''"},
        ),
        Div(*body, cls="pb-4 pt-0", **{"x-show": "open", "x-transition": ""}),
        cls=_cls("py-1", cls),
        **{"x-data": f"{{open: {open_str}}}"},
        **kwargs,
    )
