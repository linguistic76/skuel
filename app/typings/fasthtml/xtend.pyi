"""Types for fasthtml.xtend: the tags it redefines over fasthtml.components."""

from typing import Any

from fastcore.xml import FT

def A(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Form(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Script(code: str = "", **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements
def Style(*c: Any, **kwargs: Any) -> FT: ...  # boundary: fasthtml-elements

# Every name this stub does not declare stays Any, explicitly.
def __getattr__(name: str) -> Any: ...  # boundary: fasthtml-untyped
