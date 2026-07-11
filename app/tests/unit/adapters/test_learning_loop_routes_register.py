"""Real-FastHTML registration guard for the learning-loop detail routes.

FastHTML's route decorator RESOLVES handler annotations at registration
time — a TYPE_CHECKING-only name in a handler signature (e.g. ``-> "FT"``)
passes MyPy, unit tests (fake rt recorders), and CI, then crashes bootstrap
with ``name 'FT' is not defined`` (post-#600 hotfix). Registering against a
REAL FastHTML app catches that class of failure where it lives.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fasthtml.common import fast_app

from adapters.inbound.learning_loop_routes import (
    create_learning_loop_detail_routes,
    create_learning_loop_fragment_routes,
)


def test_detail_and_fragment_routes_register_on_real_fasthtml() -> None:
    app, rt = fast_app()

    create_learning_loop_detail_routes(
        app,
        rt,
        orchestrator=MagicMock(),
        vector_search_service=MagicMock(),
        zpd_service=MagicMock(),
    )
    create_learning_loop_fragment_routes(app, rt, orchestrator=MagicMock())

    registered = {getattr(r, "path", None) for r in app.routes}
    assert "/explore/next-step/related" in registered
    assert "/explore/ku/{uid}/related" in registered
    assert "/explore/ps/{uid}/related" in registered
