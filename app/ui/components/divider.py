from enum import StrEnum
from typing import Any

from fasthtml.common import Div, Span

from ui.components._util import _cls

__all__ = ["Divider", "DividerLine", "DividerSplit", "DividerT"]


class DividerT(StrEnum):
    default = ""
    vertical = "vertical"


def Divider(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Horizontal divider, optionally with a centred label.

    Without content: renders a plain `<hr>`-style border line.
    With content: renders "──── label ────" with the text centred between two rules.
    """
    if c:
        return Div(
            Div(cls="flex-1 border-t border-border"),
            Span(*c, cls="px-3 text-sm text-muted-foreground whitespace-nowrap"),
            Div(cls="flex-1 border-t border-border"),
            cls=_cls("flex items-center my-4", cls),
            **kwargs,
        )
    return Div(cls=_cls("border-t border-border my-4", cls), **kwargs)


def DividerLine(cls: str = "", **kwargs: Any) -> Any:
    """Plain horizontal rule with no label."""
    return Div(cls=_cls("border-t border-border", cls), **kwargs)


def DividerSplit(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Alias for Divider with centred label — matches MonsterUI DividerSplit signature."""
    return Divider(*c, cls=cls, **kwargs)
