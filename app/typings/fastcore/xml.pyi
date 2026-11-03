"""Types for fastcore.xml: the FT tree that every FastHTML tag builds.

The tag functions mirror the module's own tag list; tests/unit/test_fasthtml_stubs.py
compares every declaration here with the installed package.
"""

import builtins
from collections.abc import Callable, Iterator
from typing import Any, Literal, Self, overload

from fastcore.basics import NotStr as NotStr

class FT:
    """A 'Fast Tag': `tag`, `children`, `attrs`. An unknown attribute reads or writes `attrs`."""

    tag: str
    children: tuple[Any, ...]  # boundary: fasthtml-elements
    attrs: dict[str, Any]  # boundary: fasthtml-elements
    void_: bool
    listeners_: builtins.list[Callable[[FT], object]]
    def __init__(
        self,
        tag: str,
        cs: tuple[Any, ...],  # boundary: fasthtml-elements
        attrs: dict[str, Any] | None = None,  # boundary: fasthtml-elements
        void_: bool = False,
        **kwargs: Any,  # boundary: fasthtml-elements
    ) -> None: ...
    def on(self, f: Callable[[FT], object]) -> None: ...
    def changed(self) -> Self: ...
    def __setattr__(self, k: str, v: Any) -> None: ...  # boundary: fasthtml-elements
    def __getattr__(self, k: str) -> Any: ...  # boundary: fasthtml-elements
    def get(self, k: str, default: Any = None) -> Any: ...  # boundary: fasthtml-elements
    def __iter__(self) -> Iterator[Any]: ...  # boundary: fasthtml-elements
    def __getitem__(self, idx: int | slice) -> Any: ...  # boundary: fasthtml-elements
    def __setitem__(self, i: int, o: Any) -> None: ...  # boundary: fasthtml-elements
    def __call__(self, *c: Any, **kw: Any) -> Self: ...  # boundary: fasthtml-elements
    def set(self, *c: Any, **kw: Any) -> Self: ...  # boundary: fasthtml-elements
    def __html__(self) -> Safe: ...
    def _repr_html_(self) -> Safe: ...
    # fasthtml.components patches these onto FT: concatenation renders to a string.
    def __add__(self, b: object) -> str: ...
    def __radd__(self, b: object) -> str: ...
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...
    @property
    def list(self) -> builtins.list[Any]: ...  # boundary: fasthtml-elements

class Safe(str):
    def __html__(self) -> Self: ...

def ft(tag: str, *c: Any, void_: bool = False, **kw: Any) -> FT: ...  # boundary: fasthtml-elements
def to_xml(
    *elms: Any,  # boundary: fasthtml-elements
    lvl: int = 0,
    indent: bool = True,
    do_escape: bool = True,
) -> Safe: ...

# `Html` prepends a doctype tag unless `doctype=False`: the default is a pair, not one FT.
@overload
def Html(
    *c: Any,  # boundary: fasthtml-elements
    doctype: Literal[False],
    **kwargs: Any,  # boundary: fasthtml-elements
) -> FT: ...
@overload
def Html(
    *c: Any,  # boundary: fasthtml-elements
    doctype: Literal[True] = True,
    **kwargs: Any,  # boundary: fasthtml-elements
) -> tuple[FT, FT]: ...
@overload
def Html(
    *c: Any,  # boundary: fasthtml-elements
    doctype: bool,
    **kwargs: Any,  # boundary: fasthtml-elements
) -> FT | tuple[FT, FT]: ...
def A(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Article(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Aside(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Audio(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def B(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Body(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Br(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Button(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Canvas(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Caption(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Code(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Col(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Colgroup(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Dd(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Details(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Div(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Dl(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Dt(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Em(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Embed(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Fieldset(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Figcaption(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Figure(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Footer(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Form(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def H1(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def H2(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def H3(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def H4(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def H5(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def H6(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Head(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Header(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Hr(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def I(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Iframe(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Img(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Input(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Label(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Legend(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Li(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Link(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Main(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Mark(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Math(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Meta(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Nav(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Noscript(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Object(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Ol(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Option(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def P(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Param(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Pre(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def S(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Script(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Section(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Select(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Slot(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Small(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Source(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Span(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Strike(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Strong(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Style(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Sub(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Summary(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Sup(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Svg(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Table(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Tbody(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Td(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Template(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Textarea(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Tfoot(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Th(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Thead(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Title(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Tr(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def U(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Ul(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Video(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements

# Every name this stub does not declare stays Any, explicitly.
def __getattr__(name: str) -> Any: ...  # boundary: fasthtml-untyped
