"""Types for the fasthtml.core names first-party code reads."""

from collections.abc import Mapping
from typing import Any

from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import Response

class FtResponse:
    """An FT tree with a status, headers and a response class; FastHTML renders it per request."""

    content: Any  # boundary: fasthtml-elements
    status_code: int
    headers: Mapping[str, str] | None
    cls: type[Response]
    media_type: str | None
    background: BackgroundTask | None
    def __init__(
        self,
        content: Any,  # boundary: fasthtml-elements
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        cls: type[Response] = ...,
        media_type: str | None = None,
        background: BackgroundTask | None = None,
    ) -> None: ...
    def __response__(self, req: Request) -> Response: ...

# Every name this stub does not declare stays Any, explicitly.
def __getattr__(name: str) -> Any: ...  # boundary: fasthtml-untyped
