"""
CSRF Protection — Defense-in-Depth Double-Submit Token
=======================================================

Primary CSRF defense is `SameSite=Strict` on the session cookie (see
`adapters/inbound/auth/session.py:723`). This module adds a second line of
defense so the app stays safe if `SameSite` is ever loosened (cross-subdomain
SSO, OAuth embeds) or if an XSS on the same origin forges writes.

Mechanism
---------
- On first response per browser, `CSRFMiddleware` mints a 32-byte URL-safe
  token and sets it in the `csrf_token` cookie. The cookie is readable by
  JavaScript (`HttpOnly=False`) so the HTMX layer can echo it back.
- State-changing POST/PUT/DELETE handlers wrapped with `@csrf_protected`
  require the request to carry the same token via `X-CSRF-Token` header or
  `csrf_token` form field. Constant-time compare; mismatch → 403.
- Safe methods (GET, HEAD, OPTIONS) always pass.

Rollout
-------
`SKUEL_CSRF_ENFORCE=false` disables verification while leaving token issuance
in place. Default is `true` for new installs; staging/production must run
with enforcement on. The flag is a revert lever for the 88-route cutover,
not a permanent knob — delete after staging is green.

See: `plans/user-entry-deferred-security-items.md` § Commit G
"""

from __future__ import annotations

import hmac
import os
import secrets
from contextvars import ContextVar
from functools import wraps
from typing import TYPE_CHECKING, Any

from fasthtml.common import Input
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger("skuel.security.csrf")

# ============================================================================
# CONFIGURATION
# ============================================================================

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_ENFORCE_ENV = "SKUEL_CSRF_ENFORCE"
CSRF_TOKEN_BYTES = 32
CSRF_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # match session max_age

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# ContextVar lets form generators fetch the current request's token without a
# plumbed `request` argument. Scope is per request/task (set in middleware).
_current_csrf_token: ContextVar[str | None] = ContextVar("_current_csrf_token", default=None)


def current_csrf_token() -> str | None:
    """Return the CSRF token for the in-flight request, or None if no middleware."""
    return _current_csrf_token.get()


def csrf_hidden_input() -> Any:
    """Return a hidden <input name="csrf_token"> populated from the contextvar.

    Drop this as the first child of any hand-built ``Form()`` that posts to a
    ``@csrf_protected`` route. Forms routed through ``FormGenerator`` receive
    the field automatically — only hand-built forms (e.g., login/register)
    need this helper.
    """
    token = _current_csrf_token.get() or ""
    return Input(type="hidden", name=CSRF_FORM_FIELD, value=token)


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


async def verify_csrf(request: Request) -> bool:
    """Constant-time compare the cookie token against the submitted token."""
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not cookie_token:
        logger.warning("CSRF verify failed: no %s cookie on %s", CSRF_COOKIE_NAME, request.url.path)
        return False

    submitted = await _read_submitted_token(request)
    if not submitted:
        logger.warning(
            "CSRF verify failed: no %s header or %s field on %s",
            CSRF_HEADER_NAME,
            CSRF_FORM_FIELD,
            request.url.path,
        )
        return False

    ok = hmac.compare_digest(cookie_token, submitted)
    if not ok:
        logger.warning("CSRF verify failed: token mismatch on %s", request.url.path)
    return ok


# ============================================================================
# MIDDLEWARE
# ============================================================================


class CSRFMiddleware(BaseHTTPMiddleware):
    """Mint a CSRF cookie on the first response of every new browser session.

    Idempotent: if the request already carries a `csrf_token` cookie, the
    middleware reuses it and does not rewrite the Set-Cookie header.
    """

    async def dispatch(
        self, request: Any, call_next: Callable[[Any], Awaitable[Response]]
    ) -> Response:
        incoming = request.cookies.get(CSRF_COOKIE_NAME)
        if incoming:
            request.state.csrf_token = incoming
            ctx_token = _current_csrf_token.set(incoming)
            try:
                return await call_next(request)
            finally:
                _current_csrf_token.reset(ctx_token)

        token = mint_token()
        request.state.csrf_token = token
        ctx_token = _current_csrf_token.set(token)
        try:
            response = await call_next(request)
        finally:
            _current_csrf_token.reset(ctx_token)
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


def _forbidden_response() -> JSONResponse:
    return JSONResponse(
        content={
            "error": {
                "category": "forbidden",
                "code": "CSRF_INVALID",
                "message": "CSRF token missing or invalid",
            }
        },
        status_code=403,
        headers={"X-Toast-Message": "Session expired - please reload", "X-Toast-Type": "error"},
    )


def csrf_protected(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Reject state-changing requests that lack a matching CSRF token.

    GET/HEAD/OPTIONS pass through unchecked. When `SKUEL_CSRF_ENFORCE=false`
    the decorator is a no-op — useful for the transition commit that lands
    this module before all 88 POST routes are wired.
    """

    @wraps(func)
    async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
        if request.method in _SAFE_METHODS:
            return await func(request, *args, **kwargs)
        if not is_csrf_enforced():
            return await func(request, *args, **kwargs)
        if not await verify_csrf(request):
            return _forbidden_response()
        return await func(request, *args, **kwargs)

    return wrapper


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_FORM_FIELD",
    "CSRF_HEADER_NAME",
    "CSRFMiddleware",
    "csrf_hidden_input",
    "csrf_protected",
    "current_csrf_token",
    "get_csrf_token",
    "is_csrf_enforced",
    "mint_token",
    "verify_csrf",
]
