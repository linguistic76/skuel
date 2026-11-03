"""fastcore: only the stubbed submodules are typed; every other name stays Any."""

from typing import Any

# Every name this stub does not declare stays Any, explicitly.
def __getattr__(name: str) -> Any: ...  # boundary: fasthtml-untyped
