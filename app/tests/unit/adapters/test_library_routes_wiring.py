"""Library hub wiring: no orchestrator, no routes.

``create_library_routes`` hands ``services.library_orchestrator`` to the hub's UI
routes. When the container holds none, nothing registers — the routes would
otherwise answer every request by calling into ``None``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fasthtml.common import fast_app

from adapters.inbound.library_routes import create_library_routes


def _paths(app: object) -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}  # type: ignore[attr-defined]


def test_no_orchestrator_registers_nothing() -> None:
    app, rt = fast_app(pico=False, default_hdrs=False)
    before = _paths(app)

    create_library_routes(rt, SimpleNamespace(library_orchestrator=None))

    assert _paths(app) == before


def test_an_orchestrator_registers_the_hub() -> None:
    app, rt = fast_app(pico=False, default_hdrs=False)

    create_library_routes(rt, SimpleNamespace(library_orchestrator=MagicMock()))

    assert "/library" in _paths(app)
