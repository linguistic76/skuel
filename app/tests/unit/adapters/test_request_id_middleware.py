"""RequestIDMiddleware pins (adapters/inbound/middleware.py).

Request correlation: every HTTP response carries x-request-id, the matching
ID is visible in request_id_context for everything inside the middleware
(where the add_request_context structlog processor reads it), and the
contextvar is reset once the request finishes. Also pins the registration
order contract with RequestTimingMiddleware — timing's finally-block log
lines must still see the request ID (scripts/dev/bootstrap.py adds Timing
first so RequestID wraps it).
"""

from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient

import adapters.inbound.middleware as middleware_module
from adapters.inbound.middleware import RequestIDMiddleware, RequestTimingMiddleware
from core.utils.logging import request_id_context


def _ok_app(captured: dict[str, str]) -> Any:
    async def app(scope: Any, receive: Any, send: Any) -> None:
        captured["during"] = request_id_context.get("")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


class TestRequestIDMiddleware:
    def test_header_matches_contextvar_and_resets_after(self) -> None:
        captured: dict[str, str] = {}
        mid = RequestIDMiddleware(_ok_app(captured))

        async def outer(scope: Any, receive: Any, send: Any) -> None:
            # Runs in the same task context: observes the contextvar AFTER
            # RequestIDMiddleware's finally-block reset.
            await mid(scope, receive, send)
            captured["after"] = request_id_context.get("")

        response = TestClient(outer).get("/")

        request_id = response.headers["x-request-id"]
        assert len(request_id) == 8
        assert captured["during"] == request_id
        assert captured["after"] == ""

    def test_timing_logs_fire_with_request_id_when_wrapped(self, monkeypatch: Any) -> None:
        # Production order (bootstrap adds Timing BEFORE RequestID, so
        # RequestID is the outer layer): timing's finally-block emission must
        # still see the contextvar. The inverse order silently loses it.
        seen_at_log_time: list[str] = []

        class _CaptureLogger:
            def info(self, *args: Any, **kwargs: Any) -> None:
                seen_at_log_time.append(request_id_context.get(""))

            warning = info

        monkeypatch.setattr(middleware_module, "logger", _CaptureLogger())

        captured: dict[str, str] = {}
        app = RequestIDMiddleware(RequestTimingMiddleware(_ok_app(captured)))
        response = TestClient(app).get("/")

        assert seen_at_log_time == [response.headers["x-request-id"]]
