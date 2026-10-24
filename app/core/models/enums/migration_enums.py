"""
Migration Enums — where a whole-corpus data migration stands on the graph
=========================================================================

A whole-corpus data migration records its state on the graph itself, in a
``:MigrationRecord`` node, so the graph driver's guard can refuse a graph the
code would misread: the UTC instants migration (ADR-089), whose values cannot say
whether they have moved, and the uid grammar's close, stamped once the uid census
passes. The guard and the scripts that write a record read and write its state
through this vocabulary.

See: /docs/roadmap/utc-instants-arc.md § Migration contract (PR 4)
"""

from __future__ import annotations

from enum import StrEnum


class MigrationState(StrEnum):
    """The state a ``:MigrationRecord`` holds.

    - ``APPLIED`` — the migration's writes landed in full (for the uid grammar: the
      uid census passed), or the graph was empty when first opened and was
      stamped: the graph holds the migrated values.
    - ``REVERTED`` — applied and then undone: the graph holds the values from
      before the migration.
    """

    APPLIED = "applied"
    REVERTED = "reverted"

    @classmethod
    def from_stored(cls, value: object) -> MigrationState | None:
        """A stored state as this vocabulary names it; ``None`` for a value it does not."""
        try:
            return cls(str(value))
        except ValueError:
            return None
