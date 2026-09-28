"""
Migration Enums — where a whole-corpus data migration stands on the graph
=========================================================================

A data migration that moves stored values (the UTC instants migration, ADR-089)
records its state on the graph itself, in a ``:MigrationRecord`` node, because
the values it moves cannot say whether they have moved. The graph driver's guard
and the migration script read and write that state through this vocabulary.

See: /docs/roadmap/utc-instants-arc.md § Migration contract (PR 4)
"""

from __future__ import annotations

from enum import StrEnum


class MigrationState(StrEnum):
    """The state a ``:MigrationRecord`` holds.

    - ``APPLIED`` — the manifest was written in full, or the graph was empty when
      first opened and was stamped: the graph holds the migrated values.
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
