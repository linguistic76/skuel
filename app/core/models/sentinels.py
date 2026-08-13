"""
Shared UNSET sentinel (PEP 661 style)
=====================================

A single, type-checker-narrowable sentinel for "no value was provided" — distinct
from ``None``, which is a *meaningful* value (e.g. "clear this field").

Why a single-member ``Enum`` instead of ``object()``? A bare ``_UNSET = object()``
(as in ``core/services/exercises/``) has type ``object`` — MyPy cannot narrow
``x is not _UNSET`` to remove it from a union, so a field typed ``str | object`` stays
``object`` after the guard. A single-member enum gives every reference the literal type
``Literal[_Sentinel.UNSET]``, which MyPy *does* narrow: after ``if v is not UNSET`` the
value is just ``str``.

Usage::

    from core.models.sentinels import UNSET, Unset


    @dataclass(frozen=True)
    class TaskUpdateIntent:
        title: str | Unset | None = UNSET
        status: str | Unset | None = UNSET

        def to_changes(self) -> dict[str, Any]:
            return {
                f.name: v
                for f in fields(self)
                if (v := getattr(self, f.name)) is not UNSET
            }

See: ADR-066 (Typed Update Intents) — the ``*UpdateIntent`` dataclasses default every
field to ``UNSET`` so a partial update can distinguish "not in this update" from
"set to ``None``".
"""

from __future__ import annotations

from enum import Enum
from typing import Final, Literal


class _Sentinel(Enum):
    """Single-member enum backing the ``UNSET`` sentinel (PEP 661)."""

    UNSET = "UNSET"

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "UNSET"


UNSET: Final = _Sentinel.UNSET
"""The sentinel value. Compare with ``is`` / ``is not``, never ``==``."""

Unset = Literal[_Sentinel.UNSET]
"""Type alias for annotating an UNSET-able field: ``title: str | Unset = UNSET``."""


__all__ = ["UNSET", "Unset"]
