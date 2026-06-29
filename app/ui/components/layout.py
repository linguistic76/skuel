from typing import Any

from fasthtml.common import Div

from ui.components._util import _cls

__all__ = ["Center", "DivCentered", "DivFullySpaced"]


def DivFullySpaced(*c: Any, cls: str = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    """Flex row with content spread to opposite ends (justify-between)."""
    return Div(*c, cls=_cls("flex items-center justify-between", cls), **kwargs)


def DivCentered(*c: Any, cls: str = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    """Flex row with content centred horizontally and vertically."""
    return Div(*c, cls=_cls("flex items-center justify-center", cls), **kwargs)


def Center(*c: Any, cls: str = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    """Block-level centre: horizontally centred with text-align: center."""
    return Div(*c, cls=_cls("mx-auto text-center", cls), **kwargs)
