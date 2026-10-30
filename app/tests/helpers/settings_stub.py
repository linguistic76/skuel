"""The settings a unit test hands a module that reads ``get_settings()``.

The unit tier refuses the real config (``tests/unit/conftest.py``), so a module
that reads it is stubbed where it looks the name up — a route boundary deciding
``show_details`` from ``application.debug``:

    monkeypatch.setattr(boundary, "get_settings", settings_stub(debug=False))
"""

from collections.abc import Callable
from types import SimpleNamespace


def settings_stub(*, debug: bool = False) -> Callable[[], SimpleNamespace]:
    """A ``get_settings`` stand-in answering ``application.debug``."""
    settings = SimpleNamespace(application=SimpleNamespace(debug=debug))

    def get_settings() -> SimpleNamespace:
        return settings

    return get_settings
