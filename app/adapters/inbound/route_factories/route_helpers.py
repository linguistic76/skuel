"""
Route Helpers - Shared Utilities for Route Factories
=====================================================

Extracted common patterns to eliminate duplication across factories.
Each helper follows SKUEL's Result[T] pattern: returns Result internally;
boundary_handler converts to HTTP at the route level.

Helpers:
    check_required_role       - Role-based access control (used by CRUD, Analytics)
    verify_entity_ownership   - Ownership verification returning 404 on failure
    parse_int_query_param     - Integer param with bounds clamping
    parse_bool_query_param    - Boolean param ("true"/"1"/"yes"/"on" → True)
    parse_date_query_param    - ISO date param with safe fallback
    parse_csv_query_param     - Comma-separated list from query params
    split_csv                 - Comma-separated list from a string value
    parse_date_range_params   - Start/end date pair → DateRangeParams
    parse_pagination_params   - Limit/offset pair → PaginationParams
    parse_date_param_strict   - ISO date with Result[T] validation error
    parse_int_param_strict    - Integer in range with Result[T] validation error

See: /docs/patterns/AUTH_PATTERNS.md, /docs/patterns/OWNERSHIP_VERIFICATION.md,
     /docs/patterns/API_VALIDATION_PATTERNS.md
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, cast, overload

from starlette.responses import Response

from adapters.inbound.auth.session import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.models.enums import UserRole
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

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


def parse_int_query_param(
    params: Mapping[str, Any],
    key: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Parse an integer query param with safe fallback and optional bounds.

    Invalid, missing, or blank values return ``default``.
    Values are clamped when ``minimum`` and/or ``maximum`` are provided.
    """
    raw_value = params.get(key)
    if raw_value is None or raw_value == "":
        return default
    try:
        value = int(str(raw_value))
    except (TypeError, ValueError):  # fmt: skip
        return default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def parse_float_query_param(
    params: Mapping[str, Any],
    key: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Parse a float query param with safe fallback and optional bounds.

    Invalid, missing, or blank values return ``default``.
    Values are clamped when ``minimum`` and/or ``maximum`` are provided.
    """
    raw_value = params.get(key)
    if raw_value is None or raw_value == "":
        return default
    try:
        value = float(str(raw_value))
    except (TypeError, ValueError):  # fmt: skip
        return default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


async def require_owned_entity(
    service_core: Any | None,
    uid: str,
    user_uid: UserUID,
    entity_name: str = "Entity",
) -> tuple[Any | None, Response | None]:
    """
    Combined service availability + ownership verification for UI routes.

    Eliminates the repeated 5-line pattern:
        if not service: return Response("Service unavailable", 503)
        result = await service.core.verify_ownership(uid, user_uid)
        if result.is_error: return Response("X not found", 404)

    Returns (entity, None) on success, (None, error_response) on failure.

    Usage:
        entity, error = await require_owned_entity(
            service and service.core, uid, user_uid, "Choice"
        )
        if error:
            return error

    Security: Returns generic "not found" (404), never includes UID in response.

    See: /docs/patterns/OWNERSHIP_VERIFICATION.md
    """
    if service_core is None:
        return None, Response("Service unavailable", status_code=503)
    result: Result[Any] = cast("Result[Any]", await service_core.verify_ownership(uid, user_uid))
    if result.is_error:
        return None, Response(f"{entity_name} not found", status_code=404)
    return result.value, None


# ============================================================================
# QUERY PARAM PARSING HELPERS
# ============================================================================


def parse_bool_query_param(
    params: Mapping[str, Any],
    key: str,
    default: bool = False,
) -> bool:
    """Parse a boolean query parameter with safe fallback.

    Truthy values: ``"true"``, ``"1"``, ``"yes"``, ``"on"`` (case-insensitive).
    Missing or blank values return *default*.
    """
    raw = params.get(key)
    if raw is None or raw == "":
        return default
    return str(raw).lower() in ("true", "1", "yes", "on")


@overload
def parse_date_query_param(params: Mapping[str, Any], key: str, default: date) -> date: ...
@overload
def parse_date_query_param(
    params: Mapping[str, Any], key: str, default: None = None
) -> date | None: ...
def parse_date_query_param(
    params: Mapping[str, Any],
    key: str,
    default: date | None = None,
) -> date | None:
    """Parse an ISO-format date query parameter with safe fallback.

    Invalid or missing values return *default*. Overloaded on *default*
    because every return path is either a parsed date or *default* itself:
    a caller that supplies a real date can never receive None, and saying so
    is what lets it feed a ``date``-typed parameter without a cast.
    """
    raw = params.get(key)
    if raw is None or raw == "":
        return default
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError):  # fmt: skip
        return default


def parse_csv_query_param(
    params: Mapping[str, Any],
    key: str,
) -> list[str]:
    """Parse a comma-separated query parameter into a list of stripped, non-empty strings."""
    raw = params.get(key)
    if raw is None or raw == "":
        return []
    return split_csv(str(raw))


def split_csv(value: str) -> list[str]:
    """Split a comma-separated string into a list of stripped, non-empty strings."""
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class DateRangeParams:
    """Parsed start_date / end_date pair."""

    start_date: date | None
    end_date: date | None


def parse_date_range_params(
    params: Mapping[str, Any],
    start_key: str = "start_date",
    end_key: str = "end_date",
    *,
    default_start: date | None = None,
    default_end: date | None = None,
) -> DateRangeParams:
    """Parse a start/end date pair from query params with safe fallbacks."""
    return DateRangeParams(
        start_date=parse_date_query_param(params, start_key, default_start),
        end_date=parse_date_query_param(params, end_key, default_end),
    )


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
) -> PaginationParams:
    """Parse limit + offset query params with safe defaults and bounds."""
    return PaginationParams(
        limit=parse_int_query_param(params, "limit", default_limit, minimum=1, maximum=max_limit),
        offset=parse_int_query_param(params, "offset", default_offset, minimum=0),
    )


# ============================================================================
# STRICT (Result-wrapped) QUERY PARAM HELPERS
# ============================================================================


def parse_date_param_strict(value: str | None, field: str) -> Result[date]:
    """Parse an ISO-format date string, returning a validation error on failure.

    Use when invalid input should surface as a 400/422 to the caller rather
    than silently falling back to a default.
    """
    if not value:
        return Result.fail(Errors.validation(f"{field} is required", field=field))
    try:
        return Result.ok(date.fromisoformat(value))
    except ValueError:
        return Result.fail(
            Errors.validation(f"{field} must be ISO format (YYYY-MM-DD)", field=field, value=value)
        )


def parse_int_param_strict(
    value: str | None, field: str, min_val: int, max_val: int
) -> Result[int]:
    """Parse an integer string and validate it falls within [min_val, max_val].

    Use when invalid input should surface as a validation error rather than
    silently clamping or falling back.
    """
    if not value:
        return Result.fail(Errors.validation(f"{field} is required", field=field))
    try:
        n = int(value)
    except ValueError:
        return Result.fail(
            Errors.validation(f"{field} must be an integer", field=field, value=value)
        )
    if n < min_val or n > max_val:
        return Result.fail(
            Errors.validation(
                f"{field} must be between {min_val} and {max_val}",
                field=field,
                value=n,
            )
        )
    return Result.ok(n)


__all__ = [
    "DateRangeParams",
    "PaginationParams",
    "check_required_role",
    "parse_bool_query_param",
    "parse_csv_query_param",
    "parse_date_param_strict",
    "parse_date_query_param",
    "parse_date_range_params",
    "parse_int_param_strict",
    "parse_int_query_param",
    "parse_pagination_params",
    "require_owned_entity",
    "split_csv",
    "verify_entity_ownership",
]
