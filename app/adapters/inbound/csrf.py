"""
CSRF Protection — Defense-in-Depth Double-Submit Token
=======================================================

Primary CSRF defense is `SameSite=Strict` on the session cookie (see
`adapters/inbound/auth/session.py:723`). This module adds a second line of
defense so the app stays safe if `SameSite` is ever loosened (cross-subdomain
SSO, OAuth embeds) or if an XSS on the same origin forges writes.

The `csrf_token` cookie is the single source of truth. Three layers mirror
it into the request so handlers can verify a match:

1. **Server-render** — `csrf_hidden_input()` (ui/patterns/csrf.py) emits a
   hidden form field seeded from a ContextVar this middleware sets per request
   (core/utils/csrf_token_context.py). Works with JS disabled.
2. **HTMX header** — `static/js/skuel.js` attaches `X-CSRF-Token` to every
   mutating HTMX request via the `htmx:configRequest` hook.
3. **Native form sync** — the same JS file also re-injects/refreshes the
   hidden input from the cookie on the capture-phase `submit` event. Covers
   native `<form method="POST">` when the server-rendered input went stale
   (service-worker-cached HTML, extension-mutated DOM, etc).

State-changing handlers wrapped with `@csrf_protected` pull the submitted
token from either header or form field, constant-time compare against the
cookie, and 403 on mismatch. Safe methods (GET/HEAD/OPTIONS) always pass.

Mint exemption
--------------
Static assets, manifest, service worker, and favicon never mint a new cookie
— the preload scanner and SW install race the HTML response, and a cookieless
subresource minting a replacement would desync the form/cookie pair.

Rollout
-------
`SKUEL_CSRF_ENFORCE=false` disables verification while leaving token issuance
in place. Default is `true` for new installs. The flag is a revert lever for
the 88-route cutover, not a permanent knob — delete after staging is green.

**Production override:** when ``SKUEL_ENVIRONMENT=production`` the flag is
ignored and CSRF is always enforced, regardless of ``SKUEL_CSRF_ENFORCE``.

See: `docs/roadmap/security-hardening-deferred.md` § 8 — the removal is tracked there.
"""

from __future__ import annotations

import hmac
import os
import secrets
from functools import wraps
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from adapters.inbound.fasthtml_types import Request
from core.utils.csrf_token_context import CSRF_FORM_FIELD, csrf_token_var
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.middleware.base import RequestResponseEndpoint

logger = get_logger("skuel.security.csrf")

# ============================================================================
# CONFIGURATION
# ============================================================================

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
# CSRF_FORM_FIELD lives in core/utils/csrf_token_context.py (the render
# surface UI form builders read) — imported above so verify stays in sync.
CSRF_ENFORCE_ENV = "SKUEL_CSRF_ENFORCE"
CSRF_TOKEN_BYTES = 32
CSRF_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # match session max_age

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Paths that must NEVER mint a token. Static assets, PWA manifest, service
# worker, and favicon are fetched by the browser in parallel with the HTML
# response — the preload scanner and service worker install can race the
# page's own Set-Cookie. If any of those subresource fetches arrives before
# the browser has stored the token, minting here would overwrite the cookie
# the HTML form was rendered with, causing a form/cookie mismatch on POST.
_MINT_EXEMPT_PREFIXES: tuple[str, ...] = ("/static/",)
_MINT_EXEMPT_PATHS: frozenset[str] = frozenset(
    {"/manifest.json", "/service-worker.js", "/favicon.ico", "/robots.txt"}
)


def _is_mint_exempt(path: str) -> bool:
    return path in _MINT_EXEMPT_PATHS or path.startswith(_MINT_EXEMPT_PREFIXES)


def is_csrf_enforced() -> bool:
    """Enforcement flag — default True; set SKUEL_CSRF_ENFORCE=false to disable."""
    return os.getenv(CSRF_ENFORCE_ENV, "true").strip().lower() not in ("false", "0", "no")


def _is_production() -> bool:
    return os.getenv("SKUEL_ENVIRONMENT", "local") == "production"


# ============================================================================
# TOKEN OPERATIONS
# ============================================================================


def mint_token() -> str:
    """Generate a cryptographically random CSRF token."""
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)


def get_csrf_token(request: Request) -> str | None:
    """Return the CSRF token for this request — from request.state if minted
    this cycle, otherwise from the incoming cookie. None if no token yet."""
    token = getattr(getattr(request, "state", None), "csrf_token", None)
    if token:
        return str(token)
    return request.cookies.get(CSRF_COOKIE_NAME)


async def _read_submitted_token(request: Request) -> str | None:
    """Pull the client-side token from the header first, then form field."""
    header_value = request.headers.get(CSRF_HEADER_NAME)
    if header_value:
        return header_value

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        try:
            form = await request.form()
        except Exception as exc:  # safety-net: malformed body must not crash verify
            logger.warning("Failed to parse form for CSRF field: %s", exc)
            return None
        field_value = form.get(CSRF_FORM_FIELD)
        return str(field_value) if field_value else None

    return None


async def verify_csrf(request: Request) -> tuple[bool, str]:
    """Constant-time compare the cookie token against the submitted token.

    Returns ``(ok, reason)``. ``reason`` is a short diagnostic string that
    identifies which check failed — useful for surfacing the specific failure
    in the 403 response and for log correlation.
    """
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not cookie_token:
        logger.warning("CSRF verify failed: no %s cookie on %s", CSRF_COOKIE_NAME, request.url.path)
        return False, "no_cookie"

    submitted = await _read_submitted_token(request)
    if not submitted:
        logger.warning(
            "CSRF verify failed: no %s header or %s field on %s",
            CSRF_HEADER_NAME,
            CSRF_FORM_FIELD,
            request.url.path,
        )
        return False, "no_submitted_token"

    ok = hmac.compare_digest(cookie_token, submitted)
    if not ok:
        logger.warning("CSRF verify failed: token mismatch on %s", request.url.path)
        return False, "token_mismatch"
    return True, "ok"


# ============================================================================
# MIDDLEWARE
# ============================================================================


class CSRFMiddleware(BaseHTTPMiddleware):
    """Mint a CSRF cookie on the first response of every new browser session.

    Idempotent: if the request already carries a `csrf_token` cookie, the
    middleware reuses it and does not rewrite the Set-Cookie header.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.cookies.get(CSRF_COOKIE_NAME)
        if incoming:
            request.state.csrf_token = incoming
            ctx_token = csrf_token_var.set(incoming)
            try:
                return await call_next(request)
            finally:
                csrf_token_var.reset(ctx_token)

        # Static assets and PWA subresources must never mint — see comment on
        # _MINT_EXEMPT_PREFIXES. Pass straight through with no Set-Cookie.
        if _is_mint_exempt(request.url.path):
            return await call_next(request)

        token = mint_token()
        request.state.csrf_token = token
        ctx_token = csrf_token_var.set(token)
        try:
            response = await call_next(request)
        finally:
            csrf_token_var.reset(ctx_token)
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=token,
            max_age=CSRF_COOKIE_MAX_AGE,
            httponly=False,
            samesite="strict",
            secure=_is_production(),
            path="/",
        )
        return response


# ============================================================================
# DECORATOR
# ============================================================================


def _forbidden_response(reason: str = "invalid") -> JSONResponse:
    return JSONResponse(
        content={
            "error": {
                "category": "forbidden",
                "code": "CSRF_INVALID",
                "message": "CSRF token missing or invalid",
                "reason": reason,
            }
        },
        status_code=403,
        headers={"X-Toast-Message": "Session expired - please reload", "X-Toast-Type": "error"},
    )


def csrf_protected(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Reject state-changing requests that lack a matching CSRF token.

    GET/HEAD/OPTIONS pass through unchecked. When ``SKUEL_CSRF_ENFORCE=false``
    the decorator is a no-op in non-production environments — useful for the
    transition commit that lands this module before all 88 POST routes are
    wired. Production always enforces regardless of the flag.
    """

    @wraps(func)
    async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
        if request.method in _SAFE_METHODS:
            return await func(request, *args, **kwargs)
        if not is_csrf_enforced() and not _is_production():
            return await func(request, *args, **kwargs)
        ok, reason = await verify_csrf(request)
        if not ok:
            return _forbidden_response(reason)
        return await func(request, *args, **kwargs)

    return wrapper


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "CSRFMiddleware",
    "csrf_protected",
    "get_csrf_token",
    "is_csrf_enforced",
    "mint_token",
    "verify_csrf",
]
