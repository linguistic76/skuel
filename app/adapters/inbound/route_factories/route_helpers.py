"""
Route Helpers - Shared Utilities for Route Factories
=====================================================

Extracted common patterns to eliminate duplication across factories.
Each helper follows SKUEL's Result[T] pattern: returns Result internally;
boundary_handler converts to HTTP at the route level.

Helpers:
    check_required_role       - Role-based access control (used by CRUD)
    verify_entity_ownership   - Ownership verification returning 404 on failure (API)
    require_ownership_verifier - The verifier a uid-taking route factory needs, or a
                                registration-time refusal
    require_owned_entity      - Ownership verification returning a bare Response (UI): 404 not
                                owned / missing, the error's own status otherwise
    refuse                    - A rendered refusal from a failed owner-scoped read: 404 body
                                for NOT_FOUND, an unavailable body at the error's status otherwise
    refuse_not_found          - The rendered 404 primitive (page or fragment)
    refuse_unavailable        - The rendered non-404 primitive (page or fragment)
    parse_int_param_strict    - Integer param → Result (missing = default, malformed or
                                out of bounds = 400, above its cap = the cap)
    parse_float_param_strict  - Number param → Result (the same rule, no cap)
    parse_bool_param_strict   - Boolean param → Result (true/1/yes/on, false/0/no/off)
    parse_date_param_strict   - ISO date param → Result
    parse_pagination_params   - Limit/offset pair → Result[PaginationParams]
    parse_csv_query_param     - Comma-separated list from query params
    split_csv                 - Comma-separated list from a string value
    refuse_malformed          - The bare 400 an HTML route answers for a malformed param

See: /docs/patterns/AUTH_PATTERNS.md, /docs/patterns/OWNERSHIP_VERIFICATION.md,
     /docs/patterns/API_VALIDATION_PATTERNS.md
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, cast, overload

from fasthtml.common import FT, FtResponse
from starlette.responses import Response

from adapters.inbound.auth.session import require_authenticated_user
from adapters.inbound.boundary import status_for_error
from adapters.inbound.fasthtml_types import Request
from core.models.enums import UserRole
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorCategory, ErrorContext, Errors, Result

if TYPE_CHECKING:
    from core.ports.service_protocols import OwnershipVerifier

logger = get_logger("skuel.routes.helpers")


async def check_required_role(
    request: Request,
    require_role: UserRole | None,
    user_service_getter: Callable | None,
    domain: str,
) -> Result[None]:
    """
    Check if the authenticated user has the required role.

    Returns Result.ok(None) if no role is configured or user is authorized.
    Returns Result.fail with Forbidden error if user lacks the required role.

    Args:
        request: FastHTML request object
        require_role: Required role (None = no check needed)
        user_service_getter: Callable returning UserService (required when require_role is set)
        domain: Domain name for error messages

    See: /docs/patterns/AUTH_PATTERNS.md
    """
    if not require_role:
        return Result.ok(None)

    if not user_service_getter:
        return Result.fail(
            Errors.system(
                message="Role check requires user_service_getter",
                operation="check_required_role",
            )
        )

    user_uid = require_authenticated_user(request)

    user_service = user_service_getter()
    result = await user_service.get_user(user_uid)

    if result.is_error or not result.value:
        return Result.fail(
            Errors.forbidden(
                action=f"access {domain}",
                reason="User not found or access denied",
            )
        )

    user = result.value

    if not user.has_permission(require_role):
        return Result.fail(
            Errors.forbidden(
                action=f"access {domain}",
                reason=f"Requires {require_role.value} role or higher",
                required_role=require_role.value,
            )
        )

    return Result.ok(None)


def require_ownership_verifier(
    verifier: OwnershipVerifier | None, routes: str
) -> OwnershipVerifier:
    """The service that owner-verifies ``routes``' uid — registration fails without one.

    A route that takes an entity uid verifies its owner before the service behind it
    runs (``verify_entity_ownership``); a factory registering such a route without the
    verifier would serve it unguarded, so it refuses at registration instead.
    """
    if verifier is None:
        raise ValueError(
            f"{routes} routes take a uid and cannot be registered without the "
            "service that verifies its owner"
        )
    return verifier


async def verify_entity_ownership(
    service: Any,
    uid: str,
    user_uid: UserUID,
    domain: str = "",
) -> Result[Any] | None:
    """
    Verify that a user owns an entity.

    Returns error Result if ownership check fails, None if it passes.
    Callers use truthiness check:

        ownership_error = await verify_entity_ownership(service, uid, user_uid, domain)
        if ownership_error:
            return ownership_error

    Security: Returns NotFound (404) not Forbidden (403), preventing UID enumeration.

    Args:
        service: Any service with a verify_ownership(uid, user_uid) -> Result method
        uid: Entity UID to check
        user_uid: Authenticated user UID
        domain: Domain name for debug logging

    See: /docs/patterns/OWNERSHIP_VERIFICATION.md
    """
    ownership_result: Result[Any] = cast(
        "Result[Any]", await service.verify_ownership(uid, user_uid)
    )
    if ownership_result.is_error:
        if domain:
            logger.debug(f"Ownership verification failed for {domain}: uid={uid}, user={user_uid}")
        return ownership_result
    return None


#: Response header on a rendered refusal. ``static/js/skuel.js`` swaps an error body into
#: its target only when this header is present — a plain-text 4xx/5xx stays unswapped.
REFUSAL_HEADER = "X-SKUEL-Refusal"
REFUSAL_RENDERED = "rendered"


def is_not_found(error: ErrorContext) -> bool:
    """Whether a failed owner-scoped read is the access decision (foreign or missing uid)."""
    return error.category is ErrorCategory.NOT_FOUND


async def require_owned_entity(
    service: Any | None,
    uid: str,
    user_uid: UserUID,
    entity_name: str = "Entity",
) -> tuple[Any | None, Response | None]:
    """
    Combined service availability + ownership verification for UI routes.

    Returns ``(entity, None)`` when the caller owns the entity, else
    ``(None, refusal)`` where the refusal is a bare ``Response``: 404 when the
    entity is not the caller's or does not exist (indistinguishable by design),
    the error's own status for anything else — a backend failure is not an
    access decision and must not read as "not found" (503 when the service is
    unavailable). Any object with ``verify_ownership(uid, user_uid)`` serves —
    every Activity facade inherits it.

    The bare response is the right answer where nothing is rendered on refusal:
    a mutation only a crafted request reaches, or a nested fragment whose parent
    already refused. Where the learner sees the refusal — a full page, or the
    top-level fragment a shell loads — render it through :func:`refuse`.

    Usage:
        task, refusal = await require_owned_entity(tasks_service, uid, user_uid, "Task")
        if refusal:
            return refusal

    Security: "not found" (404), never "forbidden" — a foreign uid and a missing
    one are indistinguishable, so UIDs cannot be enumerated.

    See: /docs/patterns/OWNERSHIP_VERIFICATION.md
    """
    if service is None:
        return None, Response("Service unavailable", status_code=503)
    result: Result[Any] = cast("Result[Any]", await service.verify_ownership(uid, user_uid))
    if result.is_error:
        error = result.expect_error()
        if is_not_found(error):
            return None, Response(f"{entity_name} not found", status_code=404)
        return None, Response(f"{entity_name} unavailable", status_code=status_for_error(error))
    return result.value, None


def refuse_not_found(body: FT) -> FtResponse:
    """The rendered 404 — the body the learner sees, with the status intact.

    ``body`` is a full page (sidebar chrome + banner) or a fragment (the banner in
    its slot); ``FtResponse`` renders either through FastHTML's own page/fragment
    path (``HX-Request``-aware). The status is the invariant: an ownership failure
    answers 404 to clients, caches and monitoring whatever the body says. The
    ``X-SKUEL-Refusal: rendered`` header is the fragment swap opt-in that
    ``skuel.js``'s ``htmx:beforeSwap`` listener reads; a page load ignores it.

    Reach for :func:`refuse` when the failure came from a ``Result`` — it keeps a
    backend failure from reading as "not found". Call this directly only when the
    refusal IS the not-found decision (a uid the caller never supplied, an
    audience check that has no error category to branch on).

    See: /docs/patterns/OWNERSHIP_VERIFICATION.md § UI Routes
    """
    return FtResponse(body, status_code=404, headers={REFUSAL_HEADER: REFUSAL_RENDERED})


def refuse_unavailable(body: FT, error: ErrorContext) -> FtResponse:
    """The rendered non-404 — an operational failure with the body the learner sees.

    The status is the error's own (503 for a database failure, 500 for a system
    one — ``status_for_error``), never 404: a backend outage must stay visible as
    a fault instead of reading as "no such entity". Same header, same swap opt-in.
    """
    return FtResponse(
        body, status_code=status_for_error(error), headers={REFUSAL_HEADER: REFUSAL_RENDERED}
    )


def refuse(error: ErrorContext, render: Callable[[str], FT], entity_name: str) -> FtResponse:
    """A rendered refusal from a failed owner-scoped read, at the status the failure earns.

    ``render`` builds the body from a message — the page (``partial(
    render_activity_sidebar_error, active="tasks", request=request)``) or the
    fragment slot. NOT_FOUND (foreign or missing uid) renders ``"<Entity> not
    found"`` at 404; anything else renders ``"Could not load <entity>. Please
    try again."`` at the error's own status, so a backend failure is reported as
    one. One decision, one door, for every page and fragment.

    Usage:
        owned = await tasks_service.verify_ownership(uid, user_uid)
        if owned.is_error:
            return refuse(
                owned.expect_error(),
                partial(render_activity_sidebar_error, active="tasks", request=request),
                "Task",
            )
        task = owned.value

    See: /docs/patterns/OWNERSHIP_VERIFICATION.md § UI Routes
    """
    if is_not_found(error):
        return refuse_not_found(render(f"{entity_name} not found"))
    return refuse_unavailable(
        render(f"Could not load {entity_name.lower()}. Please try again."), error
    )


# ============================================================================
# QUERY PARAM PARSING — one rule at every door
# ============================================================================
#
# Missing or blank is the default; present but malformed is a validation error
# (400 through ``boundary_handler``); a value outside its domain bounds
# (``min_val`` / ``max_val``) is a validation error too. Only a ``cap`` clamps:
# a limit, a window or a depth past what the server will do is server policy,
# not an input error. Omit ``default`` and the parameter is required.


class _Required(Enum):
    """The sentinel ``default`` of a required parameter."""

    TOKEN = auto()


_REQUIRED = _Required.TOKEN

_TRUE_WORDS = frozenset({"true", "1", "yes", "on"})
_FALSE_WORDS = frozenset({"false", "0", "no", "off"})


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _missing[D](value: object, field: str, default: D | _Required) -> Result[D] | None:
    """The answer for a missing or blank value — its default, or "required" —
    or ``None`` when a value is present."""
    if not _is_blank(value):
        return None
    if isinstance(default, _Required):
        return Result.fail(Errors.validation(f"{field} is required", field=field))
    return Result.ok(default)


def _out_of_range(field: str, value: object, low: object, high: object) -> ErrorContext:
    if low is not None and high is not None:
        message = f"{field} must be between {low} and {high}"
    elif low is not None:
        message = f"{field} must be at least {low}"
    else:
        message = f"{field} must be at most {high}"
    return Errors.validation(message, field=field, value=str(value))


@overload
def parse_int_param_strict(
    value: object,
    field: str,
    min_val: int | None = None,
    max_val: int | None = None,
    *,
    cap: int | None = None,
) -> Result[int]: ...
@overload
def parse_int_param_strict(
    value: object,
    field: str,
    min_val: int | None = None,
    max_val: int | None = None,
    *,
    default: int,
    cap: int | None = None,
) -> Result[int]: ...
@overload
def parse_int_param_strict(
    value: object,
    field: str,
    min_val: int | None = None,
    max_val: int | None = None,
    *,
    default: None,
    cap: int | None = None,
) -> Result[int | None]: ...
def parse_int_param_strict(
    value: object,
    field: str,
    min_val: int | None = None,
    max_val: int | None = None,
    *,
    default: int | _Required | None = _REQUIRED,
    cap: int | None = None,
) -> Result[int] | Result[int | None]:
    """Read an integer parameter: the text a query string or form carries, or a
    JSON body's number.

    Missing or blank is ``default`` (required when omitted). Text that is not an
    integer, a boolean, or a value outside ``[min_val, max_val]`` is a validation
    error. A value above ``cap`` is ``cap``.
    """
    missing = _missing(value, field, default)
    if missing is not None:
        return missing
    if isinstance(value, bool) or not isinstance(value, str | int):
        return Result.fail(Errors.validation(f"{field} must be an integer", field=field))
    try:
        number = int(value)
    except ValueError:
        return Result.fail(
            Errors.validation(f"{field} must be an integer", field=field, value=str(value))
        )
    if (min_val is not None and number < min_val) or (max_val is not None and number > max_val):
        return Result.fail(_out_of_range(field, number, min_val, max_val))
    if cap is not None:
        number = min(cap, number)
    return Result.ok(number)


def parse_float_param_strict(
    value: object,
    field: str,
    *,
    default: float,
    min_val: float | None = None,
    max_val: float | None = None,
) -> Result[float]:
    """Read a number parameter: the text a query string or form carries, or a
    JSON body's number.

    Missing or blank is ``default``. A boolean, a value that does not read as a
    number, a non-finite number, or one outside ``[min_val, max_val]`` is a
    validation error — a door never answers a default in place of a value it
    could not read.
    """
    missing = _missing(value, field, default)
    if missing is not None:
        return missing
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return Result.fail(Errors.validation(f"{field} must be a number", field=field))
    try:
        number = float(value)
    except ValueError:
        return Result.fail(
            Errors.validation(f"{field} must be a number", field=field, value=str(value))
        )
    if not math.isfinite(number):
        return Result.fail(
            Errors.validation(f"{field} must be a finite number", field=field, value=str(value))
        )
    if (min_val is not None and number < min_val) or (max_val is not None and number > max_val):
        return Result.fail(_out_of_range(field, value, min_val, max_val))
    return Result.ok(number)


def parse_bool_param_strict(value: object, field: str, *, default: bool) -> Result[bool]:
    """Read a boolean parameter: the text a query string or form carries, or a
    JSON body's ``true`` / ``false``.

    Missing or blank is ``default``. ``true`` / ``1`` / ``yes`` / ``on`` and
    ``false`` / ``0`` / ``no`` / ``off`` (any case) read; anything else is a
    validation error.
    """
    missing = _missing(value, field, default)
    if missing is not None:
        return missing
    if isinstance(value, bool):
        return Result.ok(value)
    word = str(value).strip().lower()
    if word in _TRUE_WORDS:
        return Result.ok(True)
    if word in _FALSE_WORDS:
        return Result.ok(False)
    return Result.fail(
        Errors.validation(f"{field} must be true or false", field=field, value=str(value))
    )


@overload
def parse_date_param_strict(value: object, field: str) -> Result[date]: ...
@overload
def parse_date_param_strict(value: object, field: str, *, default: date) -> Result[date]: ...
@overload
def parse_date_param_strict(value: object, field: str, *, default: None) -> Result[date | None]: ...
def parse_date_param_strict(
    value: object,
    field: str,
    *,
    default: date | _Required | None = _REQUIRED,
) -> Result[date] | Result[date | None]:
    """Read an ISO-format (``YYYY-MM-DD``) date parameter.

    Missing or blank is ``default`` (required when omitted); text that is not an
    ISO date is a validation error.
    """
    missing = _missing(value, field, default)
    if missing is not None:
        return missing
    try:
        return Result.ok(date.fromisoformat(str(value)))
    except ValueError:
        return Result.fail(
            Errors.validation(
                f"{field} must be ISO format (YYYY-MM-DD)", field=field, value=str(value)
            )
        )


def parse_csv_query_param(
    params: Mapping[str, Any],
    key: str,
) -> list[str]:
    """Parse a comma-separated query parameter into a list of stripped, non-empty strings.

    Any text reads as a list, so there is no malformed value: missing or blank is ``[]``.
    """
    raw = params.get(key)
    if raw is None or raw == "":
        return []
    return split_csv(str(raw))


def split_csv(value: str) -> list[str]:
    """Split a comma-separated string into a list of stripped, non-empty strings."""
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class PaginationParams:
    """Parsed limit / offset pair."""

    limit: int
    offset: int


def parse_pagination_params(
    params: Mapping[str, Any],
    *,
    default_limit: int = 50,
    default_offset: int = 0,
    max_limit: int = 500,
) -> Result[PaginationParams]:
    """Read ``limit`` + ``offset``: missing or blank is the default, a malformed or
    out-of-range value (``limit`` below 1, ``offset`` below 0) is a validation
    error, and a ``limit`` above ``max_limit`` is ``max_limit``."""
    limit = parse_int_param_strict(
        params.get("limit"), "limit", 1, default=default_limit, cap=max_limit
    )
    if limit.is_error:
        return Result.fail(limit)
    offset = parse_int_param_strict(params.get("offset"), "offset", 0, default=default_offset)
    if offset.is_error:
        return Result.fail(offset)
    return Result.ok(PaginationParams(limit=limit.value, offset=offset.value))


def refuse_malformed(error: ErrorContext) -> Response:
    """The bare 400 an HTML route answers for a malformed parameter.

    Plain text with no refusal header, so HTMX leaves the target as it was: the
    page minted the value, and only a crafted or stale request carries one that
    does not read.
    """
    return Response(error.message, status_code=status_for_error(error), media_type="text/plain")


__all__ = [
    "PaginationParams",
    "check_required_role",
    "parse_bool_param_strict",
    "parse_csv_query_param",
    "parse_date_param_strict",
    "parse_float_param_strict",
    "parse_int_param_strict",
    "parse_pagination_params",
    "refuse_malformed",
    "require_owned_entity",
    "require_ownership_verifier",
    "split_csv",
    "verify_entity_ownership",
]
