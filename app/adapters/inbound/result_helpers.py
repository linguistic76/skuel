"""
Result Helpers for Route Handlers
=================================

Shared helpers that eliminate recurring Result[T] handling boilerplate
in route functions. These complement the boundary_handler decorator
(which converts Result→HTTP at the edge) by simplifying the *inner*
result manipulation that routes do before returning.

See: /docs/patterns/ERROR_HANDLING.md
"""

from typing import overload

from core.utils.result_simplified import Errors, Result


@overload
def require_found[T](result: Result[T | None], resource: str, identifier: str) -> Result[T]: ...


@overload
def require_found[T](result: Result[T], resource: str, identifier: str) -> Result[T]: ...


def require_found[T](
    result: Result[T | None] | Result[T],
    resource: str,
    identifier: str,
) -> Result[T]:
    """Unwrap a Result that may contain None, returning NOT_FOUND if absent.

    Combines two common checks into one call:
    1. If the result is an error, propagate it.
    2. If the value is None, return a NOT_FOUND error.

    Before::

        result = await service.get_entity(uid)
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(Errors.not_found("Entity", uid))
        entity = result.value

    After::

        found = require_found(result, "Entity", uid)
        if found.is_error:
            return found
        entity = found.value

    Two overloads, one body. The nullable arm is the original: a backend-shaped
    getter that reports "no match" as ``Result.ok(None)``. The non-nullable arm
    exists because ``BaseService.get()`` returns ``Result[T]`` — it converts
    not-found into an error itself — and ``Result`` is invariant, so a
    ``Result[T]`` will not flow into a ``Result[T | None]`` parameter. Without
    the second overload a route fetching through a *typed* service could not use
    this helper at all, and the pressure would be to drop the guard rather than
    keep the convention (AGENTS.md: route handlers use ``require_found`` for the
    fetch + not-found guard). Keeping it is defense in depth at the boundary: the
    declared type says the value cannot be None, and if some implementation ever
    disagrees the route still answers 404 rather than dereferencing None into a
    500. Both arms narrow to ``Result[T]`` — verified by ``reveal_type``.

    Args:
        result: A Result whose value may be None (service returned no match), or
            one already typed non-None — see the overloads above.
        resource: Human-readable resource name for the error message (e.g. "Task").
        identifier: The UID or key that was looked up.

    Returns:
        Result[T] — guaranteed non-None value on success.
    """
    if result.is_error:
        return Result.fail(result)
    if result.value is None:
        return Result.fail(Errors.not_found(resource=resource, identifier=identifier))
    return Result.ok(result.value)


__all__ = ["require_found"]
