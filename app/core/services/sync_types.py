"""
Sync Operation Statistics Types
================================

Frozen dataclasses for sync operation results.
Follows Pattern 3C: dict[str, Any] → frozen dataclasses

Pattern:
- Frozen (immutable after construction)
- Type-safe field access
- Self-documenting structure
- Follows user_stats_types.py pattern
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SyncStats:
    """
    Statistics from Obsidian sync operation.

    Tracks the results of syncing KnowledgeUnits to Obsidian vault.

    Attributes:
        total: Total number of items processed
        synced: Number successfully synced
        conflicts: Number with conflicts
        errors: List of error details (uid + error message)
    """

    total: int
    synced: int
    conflicts: int
    errors: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class SyncError:
    """
    Individual sync error details.

    Attributes:
        uid: Entity UID that failed to sync
        error: Error message
    """

    uid: str
    error: str
