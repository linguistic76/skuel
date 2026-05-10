"""Engagement value object — frozen state of a (User, PathStep) engagement edge.

The engagement itself is a Neo4j edge ``(User)-[:ENGAGED_WITH {since, state,
completed_at?, abandoned_at?}]->(PathStep)``, NOT a standalone Entity. This
dataclass is the in-memory projection returned by the facade's lifecycle
methods so callers don't have to decode raw Cypher records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime

EngagementState = Literal["engaged", "completed", "abandoned"]


@dataclass(frozen=True, kw_only=True)
class Engagement:
    """Snapshot of one (student, PS) engagement edge.

    ``spawned_instance_uids`` is populated only on engage_pathstep results —
    other transitions return an empty tuple. Tuple, not list, for hash/freeze.
    """

    student_uid: str
    ps_uid: str
    state: EngagementState
    since: datetime
    completed_at: datetime | None = None
    abandoned_at: datetime | None = None
    spawned_instance_uids: tuple[str, ...] = field(default_factory=tuple)
