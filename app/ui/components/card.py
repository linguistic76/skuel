from typing import Any

from fasthtml.common import Div

from ui.components._util import _cls

__all__ = ["Card", "CardBody", "CardFooter", "CardHeader", "CardTitle"]


def Card(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return Div(
        *c, cls=_cls("rounded-lg border bg-card text-card-foreground shadow-xs", cls), **kwargs
    )


def CardHeader(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return Div(*c, cls=_cls("flex flex-col space-y-1.5 p-6", cls), **kwargs)


def CardTitle(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return Div(*c, cls=_cls("text-2xl font-semibold leading-none tracking-tight", cls), **kwargs)


def CardBody(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return Div(*c, cls=_cls("p-6 pt-0", cls), **kwargs)


def CardFooter(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return Div(*c, cls=_cls("flex items-center p-6 pt-0", cls), **kwargs)
