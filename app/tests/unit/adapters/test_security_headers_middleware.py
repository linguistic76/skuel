"""SecurityHeadersMiddleware pins (adapters/inbound/middleware.py).

Public-facing hardening: every HTTP response carries the browser security
headers (frame denial, nosniff, referrer policy, permissions policy, and the
observe-first report-only CSP); existing headers are never overwritten; HSTS
is deliberately absent (Caddy's job at the TLS edge).
"""

from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient

from adapters.inbound.middleware import SecurityHeadersMiddleware


def _app_with_headers(extra_headers: list[tuple[bytes, bytes]] | None = None) -> Any:
    async def plain_app(scope: Any, receive: Any, send: Any) -> None:
        headers = [(b"content-type", b"text/html")] + (extra_headers or [])
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": b"ok"})

    return SecurityHeadersMiddleware(plain_app)


class TestSecurityHeaders:
    def test_all_headers_stamped(self) -> None:
        response = TestClient(_app_with_headers()).get("/")

        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["Permissions-Policy"] == (
            "microphone=(self), camera=(), geolocation=()"
        )

    def test_csp_is_report_only(self) -> None:
        # Observe-first: violations report to the console without breaking the
        # page. Promote to enforcing only after the console stays clean.
        response = TestClient(_app_with_headers()).get("/")

        csp = response.headers["Content-Security-Policy-Report-Only"]
        assert "default-src 'self'" in csp
        assert "'unsafe-eval'" in csp  # Alpine evaluates x-data expressions
        assert "frame-ancestors 'none'" in csp
        assert "Content-Security-Policy" not in {
            k for k in response.headers if k.lower() == "content-security-policy"
        }

    def test_existing_header_is_not_overwritten(self) -> None:
        response = TestClient(_app_with_headers([(b"x-frame-options", b"SAMEORIGIN")])).get("/")

        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"

    def test_hsts_deliberately_absent(self) -> None:
        # TLS termination — and therefore HSTS — belongs to Caddy at the edge.
        response = TestClient(_app_with_headers()).get("/")

        assert "Strict-Transport-Security" not in response.headers
