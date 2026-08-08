"""
Update contracts — the typed write-path primitives (ADR-066 Phase 7).
=====================================================================

Three small primitives parameterize the shared CRUD base over *what an update is
allowed to change*:

- ``SupportsToChanges`` — the structural contract every update value satisfies: it can
  materialize itself into a backend-ready ``dict`` patch via ``to_changes()``. The six
  Activity Domain ``*UpdateIntent`` dataclasses satisfy it; so does ``RawChanges``.
- ``SupportsToIntent`` — the edge-boundary contract a Pydantic ``*UpdateRequest`` satisfies:
  it can build the core ``*UpdateIntent`` via ``to_intent()``. The generic ``CRUDRouteFactory``
  types update schemas against this to build the intent without knowing the concrete type.
- ``RawChanges`` — the bounded **default** for the base's update type parameter ``U``. A
  ``dict`` subclass (so dict-shaped callers — curriculum, the base status/progress helpers —
  keep passing plain mappings, wrapped once) that *also* satisfies ``SupportsToChanges``. Only
  the six Activity Domains override ``U`` with their intent; the ~53 non-activity
  ``BaseService[Op, T]`` instantiations inherit ``U = RawChanges`` untouched.

See: ADR-066 (Typed Update Intents); ``docs/roadmap/done/update-intents.md`` (Phase 7a).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SupportsToChanges(Protocol):
    """An update value that can materialize itself into a backend-ready patch.

    The single materialization seam in ``CrudOperationsMixin`` calls ``to_changes()``
    exactly once, at the ``backend.update`` boundary.
    """

    def to_changes(self) -> dict[str, Any]:
        """Return the fields to write as a partial ``dict`` patch."""
        ...


@runtime_checkable
class SupportsToIntent(Protocol):
    """A Pydantic edge request that can build its core update intent.

    ``CRUDRouteFactory`` checks an update schema against this protocol to build the
    typed intent generically (``schema.to_intent()``); schemas without it (curriculum,
    forms, groups, templates) fall back to a ``RawChanges`` patch.
    """

    def to_intent(self) -> SupportsToChanges:
        """Build the core ``*UpdateIntent`` from this validated request."""
        ...


class RawChanges(dict[str, Any]):
    """A plain update patch — a ``dict`` that satisfies :class:`SupportsToChanges`.

    The bounded **default** for the base ``U`` type parameter, so non-activity services
    (curriculum, finance, the base ``update_progress`` / ``update_status`` helpers) keep
    expressing updates as dict-shaped patches without each declaring an intent type. It is
    a real ``dict`` at runtime, so the backend's ``SET n += $changes`` consumes it directly.
    """

    def to_changes(self) -> dict[str, Any]:
        """Return a plain ``dict`` copy of this patch (the materialized changes)."""
        return dict(self)


__all__ = ["RawChanges", "SupportsToChanges", "SupportsToIntent"]
