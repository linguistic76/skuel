"""Real-token CSRF helper for route tests.

The route suites (unit, integration, and infrastructure) call
``@csrf_protected`` handlers directly with fabricated request stubs
(``SimpleNamespace``), not through a ``TestClient``. For real CSRF
verification to pass, a stub needs what a browser round-trip would give
it: the ``csrf_token`` cookie ``CSRFMiddleware`` minted, echoed back in
the ``X-CSRF-Token`` header. ``attach_csrf`` equips a stub with exactly
that — one freshly minted token on both sides — so ``verify_csrf`` runs
its real constant-time compare instead of being bypassed via
``SKUEL_CSRF_ENFORCE=false``.

For ``TestClient``-based flows, skip this helper: GET any page first (the
middleware sets the cookie), then send the token back as the header or
form field — see ``tests/integration/test_csrf_end_to_end.py``.

Usage:
    from tests.fixtures.csrf import attach_csrf

    def _request(...):
        return attach_csrf(SimpleNamespace(method="POST", ...))
"""

from __future__ import annotations

from typing import Any

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token


def attach_csrf(request: Any) -> Any:
    """Attach a real, matching CSRF cookie+header pair to a request stub.

    Merges into existing ``cookies``/``headers`` dicts (preserving e.g. an
    ``HX-Request`` header) and creates them when the stub lacks either
    attribute. Returns the same stub so factories can wrap their return.
    """
    token = mint_token()

    cookies = getattr(request, "cookies", None)
    if cookies is None:
        cookies = {}
        request.cookies = cookies
    cookies[CSRF_COOKIE_NAME] = token

    headers = getattr(request, "headers", None)
    if headers is None:
        headers = {}
        request.headers = headers
    headers[CSRF_HEADER_NAME] = token

    return request
