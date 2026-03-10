"""
ZPD Snapshot Backend — Persists ZPD assessment snapshots to Neo4j
=================================================================

MVP persistence: Single :ZPDHistory node per user with latest snapshot fields.
Updated on significant events (submission approved, report submitted, etc.).

Full snapshot history (timeline arrays, trend analysis) is deferred post-MVP.

Consumed by: core/services/zpd/zpd_event_handler.py
See: docs/roadmap/zpd-service-deferred.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.zpd.zpd_assessment import ZPDAssessment

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)

_SAVE_SNAPSHOT_QUERY = """
MERGE (u:User {uid: $user_uid})
MERGE (u)-[:HAS_ZPD_HISTORY]->(h:ZPDHistory {user_uid: $user_uid})
SET h.latest_assessed_at = datetime(),
    h.latest_current_zone_count = $current_zone_count,
    h.latest_proximal_zone_count = $proximal_zone_count,
    h.latest_confirmed_count = $confirmed_count,
    h.latest_behavioral_readiness = $behavioral_readiness,
    h.latest_life_path_alignment = $life_path_alignment,
    h.latest_trigger_event = $trigger_event,
    h.snapshot_count = coalesce(h.snapshot_count, 0) + 1,
    h.updated_at = datetime()
"""

_GET_LATEST_SNAPSHOT_QUERY = """
MATCH (u:User {uid: $user_uid})-[:HAS_ZPD_HISTORY]->(h:ZPDHistory)
RETURN h {
    .latest_assessed_at,
    .latest_current_zone_count,
    .latest_proximal_zone_count,
    .latest_confirmed_count,
    .latest_behavioral_readiness,
    .latest_life_path_alignment,
    .latest_trigger_event,
    .snapshot_count,
    .updated_at
} AS snapshot
LIMIT 1
"""


class ZPDSnapshotBackend:
    """Neo4j persistence for ZPD assessment snapshots.

    MVP: Single :ZPDHistory node per user — stores only the latest
    snapshot's summary fields. No historical array yet.

    Args:
        driver: Neo4j async driver (injected at bootstrap).
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver
        self._logger = logger

    async def save_snapshot(
        self, user_uid: str, assessment: ZPDAssessment, trigger_event: str
    ) -> Result[None]:
        """MERGE ZPDHistory node, update latest fields + increment snapshot_count."""
        confirmed_count = len(assessment.confirmed_zone_uids())
        try:
            await self._driver.execute_query(
                _SAVE_SNAPSHOT_QUERY,
                {
                    "user_uid": user_uid,
                    "current_zone_count": len(assessment.current_zone),
                    "proximal_zone_count": len(assessment.proximal_zone),
                    "confirmed_count": confirmed_count,
                    "behavioral_readiness": assessment.behavioral_readiness,
                    "life_path_alignment": assessment.life_path_alignment,
                    "trigger_event": trigger_event,
                },
            )
            return Result.ok(None)
        except Exception as exc:
            self._logger.error("ZPD snapshot save failed for %s: %s", user_uid, exc)
            return Result.fail(
                Errors.database(
                    operation="ZPDSnapshotBackend.save_snapshot",
                    message=f"ZPD snapshot save failed: {exc}",
                )
            )

    async def get_latest_snapshot(self, user_uid: str) -> Result[dict[str, Any] | None]:
        """Read latest snapshot for a user."""
        try:
            records, _, _ = await self._driver.execute_query(
                _GET_LATEST_SNAPSHOT_QUERY, {"user_uid": user_uid}
            )
            if records and records[0].get("snapshot"):
                return Result.ok(dict(records[0]["snapshot"]))
            return Result.ok(None)
        except Exception as exc:
            self._logger.error("ZPD snapshot read failed for %s: %s", user_uid, exc)
            return Result.fail(
                Errors.database(
                    operation="ZPDSnapshotBackend.get_latest_snapshot",
                    message=f"ZPD snapshot read failed: {exc}",
                )
            )
