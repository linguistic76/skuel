"""
Per-user rate limiting — minimal in-memory token bucket.

Adapter-level concern. Keyed on ``UserUID`` (not IP), so each authenticated
user gets their own bucket regardless of how many processes share the host.

Process-local only. A multi-worker deployment gets one bucket per worker —
acceptable for the coarse "don't hammer /upload" guard this module provides.
A shared backend (Redis) is the upgrade path when we need a cluster-wide cap.

See: /home/mike/.claude/plans/user-entry-upload-security-review.md (Finding 7)
"""

from __future__ import annotations

import time
from collections import deque
from functools import wraps
from typing import TYPE_CHECKING, Any

from core.constants import LLMQuota
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorContext, Errors

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from adapters.inbound.fasthtml_types import Request

logger = get_logger("skuel.adapters.rate_limit")

# Shown to a MEMBER+ user who exhausted their daily AI quota. Deliberately
# distinct from the subscription denial ("AI features require a paid
# subscription") — this user HAS the subscription; telling them to upgrade
# would be wrong and confusing. Sliding window, so it frees up gradually.
LLM_QUOTA_MESSAGE = "Daily AI limit reached. Your quota frees up over the next 24 hours."

# Process-local store: user_uid → timestamps of recent hits.
_BUCKETS: dict[str, deque[float]] = {}


def _check_and_record(user_uid: str, limit: int, window_s: float) -> bool:
    """Return True if the call is within the limit; False if rate-limited.

    Sliding window: drop timestamps older than ``window_s`` from the user's
    bucket, then reject if the remaining count is at or above ``limit``.
    """
    now = time.monotonic()
    cutoff = now - window_s
    bucket = _BUCKETS.setdefault(user_uid, deque())
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def allow_key(key: str, limit: int, window_s: float) -> bool:
    """Sliding-window check for a caller-composed key (e.g. ``ws-handshake:{ip}``).

    The public primitive behind the decorators, for surfaces they cannot wrap
    (WebSocket handlers take a WebSocket, not a Request). Namespace the key —
    buckets are shared across the process.
    """
    return _check_and_record(key, limit, window_s)


def llm_quota_allowed(user_uid: str) -> bool:
    """Check-and-record one unit against the user's daily LLM quota (MEMBER+).

    One call = one unit, recorded at the moment of the check — callers place
    this immediately before the money-spending AI call so denied requests
    (tier, ownership) never burn quota. In-memory like every bucket in this
    module: single process, resets on deploy/restart — acceptable for a
    coarse daily cost ceiling (see ``core.constants.LLMQuota``).

    Namespaced key ("llm-quota:<uid>") so the daily quota never collides with
    the per-route burst buckets that key on the bare user_uid.
    """
    allowed = _check_and_record(
        f"llm-quota:{user_uid}", LLMQuota.DAILY_LIMIT, float(LLMQuota.WINDOW_SECONDS)
    )
    if not allowed:
        logger.warning(
            "Daily LLM quota exhausted for user %s (limit=%d/24h)",
            user_uid,
            LLMQuota.DAILY_LIMIT,
        )
    return allowed


def llm_quota_exceeded_error() -> ErrorContext:
    """The standard quota-exceeded denial — an ``Errors.forbidden`` variant.

    Distinct from the subscription denial: no ``required_role`` (the caller
    already holds MEMBER+) and a message that says "limit", not "upgrade".
    """
    return Errors.forbidden(action="AI request", reason=LLM_QUOTA_MESSAGE)


def rate_limited(
    *,
    per_user: int,
    window_s: float,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorate an async route handler with a per-user sliding-window limit.

    The wrapped handler must accept ``request`` as its first parameter and
    ``request.session`` must carry ``user_uid`` (standard SKUEL auth state).
    Unauthenticated requests are let through so ``require_authenticated_user``
    inside the handler remains the single source of auth errors.

    On limit exceeded, returns HTTP 429 via starlette's ``Response`` with a
    plain-text body — suitable for HTMX fragments (the client just swaps in
    the message) and JSON clients alike.
    """
    from starlette.responses import Response  # local import — adapter-only

    def decorator(handler: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(handler)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            user_uid = _extract_user_uid(request)
            if user_uid is not None and not _check_and_record(user_uid, per_user, window_s):
                logger.warning(
                    "Rate limit exceeded for user %s on %s (limit=%d, window=%ss)",
                    user_uid,
                    getattr(request, "url", "<unknown>"),
                    per_user,
                    window_s,
                )
                retry_after = max(1, int(window_s))
                return Response(
                    f"Rate limit exceeded: max {per_user} requests per {int(window_s)}s",
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
            return await handler(request, *args, **kwargs)

        return wrapper

    return decorator


def rate_limited_ip(
    *,
    bucket: str,
    per_ip: int,
    window_s: float,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Per-IP sliding-window limit for unauthenticated endpoints.

    Uses namespaced keys ("ip:<bucket>:<ip>") in the shared _BUCKETS store so
    IP and user-uid buckets never collide. Requests from 'unknown' IP pass through.
    """
    from starlette.responses import Response

    def decorator(handler: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(handler)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            ip = _extract_ip(request)
            if ip != "unknown":
                key = f"ip:{bucket}:{ip}"
                if not _check_and_record(key, per_ip, window_s):
                    logger.warning(
                        "IP rate limit exceeded for %s on %s (limit=%d, window=%ss)",
                        ip,
                        getattr(request, "url", "<unknown>"),
                        per_ip,
                        window_s,
                    )
                    retry_after = max(1, int(window_s))
                    return Response(
                        f"Rate limit exceeded: max {per_ip} requests per {int(window_s)}s",
                        status_code=429,
                        headers={"Retry-After": str(retry_after)},
                    )
            return await handler(request, *args, **kwargs)

        return wrapper

    return decorator


def _extract_user_uid(request: Request) -> str | None:
    """Read ``user_uid`` from the session without throwing for unauth requests."""
    session = getattr(request, "session", None)
    if not isinstance(session, dict):
        return None
    uid = session.get("user_uid")
    return str(uid) if uid else None


def _extract_ip(request: Request) -> str:
    """Read the client IP, falling back to 'unknown'."""
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client else None
    return str(host) if host else "unknown"


def reset_buckets_for_testing() -> None:
    """Clear the module-level bucket store. Tests only."""
    _BUCKETS.clear()


__all__ = [
    "LLM_QUOTA_MESSAGE",
    "allow_key",
    "llm_quota_allowed",
    "llm_quota_exceeded_error",
    "rate_limited",
    "rate_limited_ip",
    "reset_buckets_for_testing",
]
