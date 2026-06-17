"""
Entity Timestamp Mixin
======================

Provides ``update_properties()`` and ``timestamp_properties()`` — the only two
Neo4j property-dict helpers still used after the MOC service cleanup.

Services Using This Mixin:
- TranscriptionService — ``update_properties()`` for transcript status updates

See Also:
    - docs/patterns/entity_timestamp_mixin.md
"""

from core.utils.timestamp_helpers import now_local, now_utc


class EntityTimestampMixin:
    """Mixin providing timestamp property-dict helpers for Neo4j write operations."""

    @staticmethod
    def update_properties(use_utc: bool = False) -> dict[str, str]:
        """
        Create update timestamp properties dict for Neo4j updates.

        Returns:
            Dict with ``updated_at`` ISO string.

        Example::

            updates = {"title": new_title, **self.update_properties()}
        """
        current_time = now_utc() if use_utc else now_local()
        return {"updated_at": current_time.isoformat()}
