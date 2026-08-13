"""_EngagementGateway — manages the (User)-[:ENGAGED_WITH]->(PS) edge.

Edge schema:

    (User)-[:ENGAGED_WITH {
        since:        datetime,           # set on engage
        state:        "engaged" | "completed" | "abandoned",
        completed_at: datetime | null,    # set on complete
        abandoned_at: datetime | null,    # set on abandon
    }]->(PathStep)

Invariants enforced here:
- At most one edge with state="engaged" per (student, PS).
  ``find_active`` returns it; ``open_engagement`` refuses to create a second.
- Completed and abandoned edges are preserved as audit trail; they are not
  deleted on subsequent re-engagement.

The gateway returns the raw datetime/state shape, not the ``Engagement`` value
object — the facade composes the ``spawned_instance_uids`` field on top.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from .engagement import Engagement, EngagementEdgeState

if TYPE_CHECKING:
    from core.ports.ps_engagement_protocols import PsEngagementOperations

logger = get_logger(__name__)


class _EngagementGateway:
    """Thin orchestrator over the ENGAGED_WITH edge.

    Owns the at-most-one-active invariant and the record→``Engagement``
    reconstruction; the Cypher itself lives in ``PsEngagementBackend`` below
    the hexagonal boundary (ADR-044).
    """

    def __init__(self, backend: PsEngagementOperations) -> None:
        self._backend = backend
        self.logger = logger

    async def find_active(self, student_uid: str, ps_uid: str) -> Result[Engagement | None]:
        """Return the active engagement edge, or None if there isn't one.

        "Active" = ``state = "engaged"``. Completed/abandoned edges are
        ignored here — callers wanting audit history use ``find_history``.
        """
        result = await self._backend.find_active_engagement(student_uid, ps_uid)
        if result.is_error:
            return Result.fail(result)
        records: list[dict[str, Any]] = result.value
        if not records:
            return Result.ok(None)
        return Result.ok(_record_to_engagement(records[0], student_uid, ps_uid))

    async def list_engaged(self, student_uid: str) -> Result[list[Engagement]]:
        """Return all active (state='engaged') engagement edges for a student.

        Completed and abandoned edges are filtered out — callers wanting the
        full audit trail need a different read path. Each returned Engagement
        carries an empty ``spawned_instance_uids`` tuple; the facade enriches
        it from the activity instance store.
        """
        result = await self._backend.list_engaged_edges(student_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [_record_to_engagement(rec, student_uid, rec["ps_uid"]) for rec in result.value]
        )

    async def open_engagement(self, student_uid: str, ps_uid: str) -> Result[Engagement]:
        """Create a new ENGAGED_WITH edge with state='engaged'.

        Refuses if an active engagement already exists for this (student, PS) —
        enforces the at-most-one-active invariant. The actual instance spawn
        is the orchestrator's job; this method only owns the edge.
        """
        active = await self.find_active(student_uid, ps_uid)
        if active.is_error:
            return Result.fail(active)
        if active.value is not None:
            return Result.fail(
                Errors.business(
                    rule="engagement_already_active",
                    message=(
                        f"User {student_uid} already has an active engagement "
                        f"with PathStep {ps_uid}; complete or abandon it first."
                    ),
                    student_uid=student_uid,
                    ps_uid=ps_uid,
                )
            )

        now = datetime.now(UTC)
        # NOTE: this CREATE is not atomic with find_active above. Two concurrent
        # engage calls could both see "no active" and both create an edge. The
        # facade test for this case is the concurrency test in Phase 4
        # verification — in practice we accept the race for V1; a Neo4j unique
        # constraint on (User, PS, state="engaged") would harden it later.
        result = await self._backend.create_engagement_edge(student_uid, ps_uid, now.isoformat())
        if result.is_error:
            return Result.fail(result)
        records: list[dict[str, Any]] = result.value
        if not records:
            return Result.fail(
                Errors.database(
                    operation="open_engagement",
                    message=(
                        f"Failed to create ENGAGED_WITH edge — "
                        f"User '{student_uid}' or PathStep '{ps_uid}' may not exist"
                    ),
                )
            )
        return Result.ok(_record_to_engagement(records[0], student_uid, ps_uid))

    async def mark_completed(self, student_uid: str, ps_uid: str) -> Result[Engagement]:
        """Transition the active engagement edge to state='completed'."""
        return await self._mark_terminal(
            student_uid=student_uid,
            ps_uid=ps_uid,
            new_state="completed",
            timestamp_field="completed_at",
        )

    async def mark_abandoned(self, student_uid: str, ps_uid: str) -> Result[Engagement]:
        """Transition the active engagement edge to state='abandoned'."""
        return await self._mark_terminal(
            student_uid=student_uid,
            ps_uid=ps_uid,
            new_state="abandoned",
            timestamp_field="abandoned_at",
        )

    async def _mark_terminal(
        self,
        student_uid: str,
        ps_uid: str,
        new_state: EngagementEdgeState,
        timestamp_field: str,
    ) -> Result[Engagement]:
        """Common path for both terminal transitions (complete / abandon)."""
        now = datetime.now(UTC)
        # Inline timestamp_field is from a constrained whitelist (caller-only),
        # not user input — safe to interpolate.
        if timestamp_field not in {"completed_at", "abandoned_at"}:
            return Result.fail(Errors.system(message=f"Invalid timestamp_field: {timestamp_field}"))

        result = await self._backend.mark_engagement_terminal(
            student_uid, ps_uid, new_state, timestamp_field, now.isoformat()
        )
        if result.is_error:
            return Result.fail(result)
        records: list[dict[str, Any]] = result.value
        if not records:
            return Result.fail(
                Errors.not_found(
                    "active engagement",
                    f"student={student_uid} ps={ps_uid}",
                )
            )
        return Result.ok(_record_to_engagement(records[0], student_uid, ps_uid))


def _record_to_engagement(record: dict[str, Any], student_uid: str, ps_uid: str) -> Engagement:
    """Reconstruct an Engagement from a Neo4j record's edge properties."""
    return Engagement(
        student_uid=student_uid,
        ps_uid=ps_uid,
        state=record["state"],
        since=_parse_dt(record["since"]),
        completed_at=_parse_dt_optional(record.get("completed_at")),
        abandoned_at=_parse_dt_optional(record.get("abandoned_at")),
    )


def _parse_dt(value: Any) -> datetime:
    """Coerce a Neo4j datetime-or-iso-string to a python datetime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    # Neo4j Python driver returns its own DateTime type; .to_native() is the
    # documented way to get a stdlib datetime back.
    return value.to_native()


def _parse_dt_optional(value: Any) -> datetime | None:
    if value is None:
        return None
    return _parse_dt(value)
