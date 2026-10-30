from typing import Any

from fasthtml.common import Div

from ui.components._util import _cls

__all__ = ["Card", "CardBody", "CardFooter", "CardHeader", "CardTitle"]

# A body or footer directly after another card part drops its top padding: that part's
# bottom padding already spaces them. The sibling selector reads the rendered card, so a
# header that renders nothing gives the body its top back.
_AFTER_HEADER = "[[data-slot=card-header]+&]:pt-0"
_AFTER_BODY = "[[data-slot=card-body]+&]:pt-0"


def Card(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return Div(
        *c, cls=_cls("rounded-lg border bg-card text-card-foreground shadow-xs", cls), **kwargs
    )


def CardHeader(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return Div(
        *c,
        cls=_cls("flex flex-col space-y-1.5 p-6", cls),
        data_slot="card-header",
        **kwargs,
    )


def CardTitle(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return Div(*c, cls=_cls("text-2xl font-semibold leading-none tracking-tight", cls), **kwargs)


def CardBody(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return Div(*c, cls=_cls("p-6", _AFTER_HEADER, cls), data_slot="card-body", **kwargs)


def CardFooter(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return Div(*c, cls=_cls("flex items-center p-6", _AFTER_HEADER, _AFTER_BODY, cls), **kwargs)
