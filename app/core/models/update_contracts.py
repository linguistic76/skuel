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
  ``dict`` subclass (so dict-shaped callers — curriculum, the base progress helper — keep
  passing plain mappings, wrapped once) that *also* satisfies ``SupportsToChanges``. Only
  the six Activity Domains override ``U`` with their intent; the ~53 non-activity
  ``BaseService[Op, T]`` instantiations inherit ``U = RawChanges`` untouched.

Two further value types parameterize *how a status-bearing update is written* (ADR-087):

- ``StatusWriteGuard`` — declarative conditions the **write statement itself** evaluates
  against the status the node holds at write time, under its write-lock.
- ``StatusGuardedOutcome`` — what that write returns: whether it applied, the prior status
  read under the lock, and the resulting entity.

See: ADR-066 (Typed Update Intents); ``docs/roadmap/done/update-intents.md`` (Phase 7a);
ADR-087 (Status-Guarded Conditional Writes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.models.type_hints import Neo4jProperties


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
    (curriculum, finance, the base ``update_progress`` helper) keep expressing updates as
    dict-shaped patches without each declaring an intent type. It is a real ``dict`` at
    runtime, so the backend's ``SET n += $changes`` consumes it directly.
    """

    def to_changes(self) -> dict[str, Any]:
        """Return a plain ``dict`` copy of this patch (the materialized changes)."""
        return dict(self)


@dataclass(frozen=True)
class StatusWriteGuard:
    """Conditions a status-bearing write evaluates against the node's *prior* status.

    The caller always knows the TARGET status before the write; only the PRIOR is
    unknown, so every condition here reduces to set-membership of the prior status —
    the backend never needs to know what ``completed`` means. Each set holds canonical
    ``EntityStatus`` **values** (strings), matching how status is stored.

    Evaluated inside the write statement, after the node's write-lock is taken, so two
    concurrent writers cannot both observe the same prior (ADR-087). The default is an
    unconditional write: no refusal, no patches.

    Attributes:
        refuse_if_prior_in: Whole-write gate. When the prior status is in this set the
            node is left byte-identical and the outcome reports ``applied=False`` —
            an outcome, not an error.
        patch_if_prior_in: ``(statuses, patch)`` — merge ``patch`` only when the prior
            status IS in ``statuses`` (the reopen clear: ``{stamp_field: None}``, which
            REMOVES the property).
        patch_if_prior_not_in: ``(statuses, patch)`` — merge ``patch`` only when the
            prior status is NOT in ``statuses`` (the completion stamp, so re-posting
            ``completed`` never re-dates).
    """

    refuse_if_prior_in: frozenset[str] = frozenset()
    patch_if_prior_in: tuple[frozenset[str], Neo4jProperties] | None = None
    patch_if_prior_not_in: tuple[frozenset[str], Neo4jProperties] | None = None

    def has_patches(self) -> bool:
        """True when the guard carries at least one conditional patch."""
        return self.patch_if_prior_in is not None or self.patch_if_prior_not_in is not None


@dataclass(frozen=True)
class StatusGuardedOutcome[T]:
    """What a status-guarded write returns — the prior status IS the contract.

    Services derive every transition verdict (completion, reopen, ``is_repeat``) from
    :attr:`prior_status` using the same pure helpers in ``core.services.completion_stamp``
    that a pre-read once fed, so the verdict is exact under concurrency instead of
    reflecting a status some other writer has already moved.

    Attributes:
        applied: ``False`` when the guard refused the write (prior in
            ``refuse_if_prior_in``); the node is untouched. Not an error — a
            not-found entity is the error.
        prior_status: The status the node held at write time, read under its
            write-lock. ``None`` when the property was absent.
        entity: The post-write node when applied; the unchanged node when refused.
    """

    applied: bool
    prior_status: str | None
    entity: T


__all__ = [
    "RawChanges",
    "StatusGuardedOutcome",
    "StatusWriteGuard",
    "SupportsToChanges",
    "SupportsToIntent",
]
