from enum import StrEnum
from typing import Any

import fasthtml.common as fh

from ui.components._util import _cls

__all__ = [
    "Table",
    "Thead",
    "Tbody",
    "Tr",
    "Th",
    "Td",
    "TableT",
    "TableFromLists",
    "TableFromDicts",
]


class TableT(StrEnum):
    """Table style modifier tokens. Compose via cls=(TableT.striped,)."""

    default = ""
    striped = "[&_tbody_tr:nth-child(odd)]:bg-muted/50"
    hover = "[&_tbody_tr:hover]:bg-muted/50"


def Table(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return fh.Table(*c, cls=_cls("w-full caption-bottom text-sm", cls), **kwargs)


def Thead(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return fh.Thead(*c, cls=_cls("[&_tr]:border-b", cls), **kwargs)


def Tbody(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return fh.Tbody(*c, cls=_cls("[&_tr:last-child]:border-0", cls), **kwargs)


def Tr(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return fh.Tr(
        *c,
        cls=_cls(
            "border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted", cls
        ),
        **kwargs,
    )


def Th(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return fh.Th(
        *c,
        cls=_cls(
            "h-12 px-4 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0",
            cls,
        ),
        **kwargs,
    )


def Td(*c: Any, cls: str | tuple = "", **kwargs: Any) -> Any:  # boundary: fasthtml-elements
    return fh.Td(*c, cls=_cls("p-4 align-middle [&:has([role=checkbox])]:pr-0", cls), **kwargs)


def TableFromLists(
    header_row: list[str],
    data_rows: list[list[Any]],
    cls: str | tuple = "",
    **kwargs: Any,
) -> Any:
    """Build a styled table from a header list and a list of row lists."""
    head = Thead(Tr(*[Th(h) for h in header_row]))
    body = Tbody(*[Tr(*[Td(cell) for cell in row]) for row in data_rows])
    return Table(head, body, cls=cls, **kwargs)


def TableFromDicts(
    data: list[dict[str, Any]],
    cls: str | tuple = "",
    header_map: dict[str, str] | None = None,
    **kwargs: Any,
) -> Any:
    """Build a styled table from a list of dicts. Keys of the first dict become headers."""
    if not data:
        return Table(cls=cls, **kwargs)
    keys = list(data[0].keys())
    headers = [header_map.get(k, k) if header_map else k for k in keys]
    rows = [[str(row.get(k, "")) for k in keys] for row in data]
    return TableFromLists(headers, rows, cls=cls, **kwargs)
