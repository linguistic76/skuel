"""Types for fasthtml.components: every HTML tag function returns FT.

The tag functions mirror the module's own tag list; tests/unit/test_fasthtml_stubs.py
compares every declaration here with the installed package.
"""

from typing import Any

from fastcore.xml import FT

def ft_html(tag: str, *c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def ft_hx(tag: str, *c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def A(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Abbr(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Address(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Area(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Article(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Aside(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Audio(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def B(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Base(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Bdi(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Bdo(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Blockquote(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Body(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Br(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Button(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Canvas(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Caption(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Cite(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Code(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Col(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Colgroup(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Data(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Datalist(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Dd(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Del(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Details(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Dfn(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Dialog(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Div(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Dl(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Dt(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Em(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Embed(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Fencedframe(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
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
def Hgroup(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Hr(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def HxPartial(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def I(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Iframe(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Img(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Input(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Ins(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Kbd(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Label(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Legend(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Li(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Link(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Main(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Map(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Mark(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Menu(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Meta(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Meter(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Nav(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Noscript(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Object(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Ol(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Optgroup(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Option(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Output(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def P(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Picture(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def PortalExperimental(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Pre(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Progress(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Q(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Rp(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Rt(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Ruby(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def S(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Samp(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Script(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Search(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Section(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Select(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Slot(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Small(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Source(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Span(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Strong(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Style(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Sub(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Summary(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Sup(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Table(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Tbody(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Td(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Template(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Textarea(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Tfoot(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Th(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Thead(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Time(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Title(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Tr(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Track(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def U(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Ul(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Var(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Video(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Wbr(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements

# Every name this stub does not declare stays Any, explicitly.
def __getattr__(name: str) -> Any: ...  # boundary: fasthtml-untyped
