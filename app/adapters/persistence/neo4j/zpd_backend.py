"""
ZPD Backend — Neo4j Graph Queries for Zone of Proximal Development
===================================================================

Pure persistence layer for ZPD graph traversals. Owns all Cypher queries
that compute the user's current zone, proximal zone, readiness scores,
blocking gaps, and submission scores from the curriculum graph.

Consumed by: core/services/zpd/zpd_service.py
See: core/ports/zpd_protocols.py — ZPDBackendOperations protocol
See: docs/roadmap/zpd-service-deferred.md — design rationale
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


# ============================================================================
# CYPHER QUERIES
# ============================================================================

# Steps 1-6: Current zone (engaged KUs, per-source), proximal zone, readiness,
# engaged paths, blocking gaps, and submission scores — all in a single round-trip.
_ZONE_QUERY = """
// ── Step 1: Current zone — KUs the user has meaningfully engaged ──────────
// Returns per-source lists for compound evidence tracking.
MATCH (u:User {uid: $user_uid})
OPTIONAL MATCH (u)-[:OWNS]->(t:Entity {entity_type: 'task'})-[:APPLIES_KNOWLEDGE]->(ku_t:Entity)
OPTIONAL MATCH (u)-[:OWNS]->(j:Entity {entity_type: 'journal_submission'})-[:APPLIES_KNOWLEDGE]->(ku_j:Entity)
OPTIONAL MATCH (u)-[:OWNS]->(h:Entity {entity_type: 'habit'})-[:REINFORCES_KNOWLEDGE]->(ku_h:Entity)
WITH u,
     [uid IN collect(DISTINCT ku_t.uid) WHERE uid IS NOT NULL] AS task_engaged_uids,
     [uid IN collect(DISTINCT ku_j.uid) WHERE uid IS NOT NULL] AS journal_engaged_uids,
     [uid IN collect(DISTINCT ku_h.uid) WHERE uid IS NOT NULL] AS habit_engaged_uids

// Combine all engaged UIDs (deduplicated via UNWIND + DISTINCT, no APOC)
CALL {
    WITH task_engaged_uids, journal_engaged_uids, habit_engaged_uids
    UNWIND (task_engaged_uids + journal_engaged_uids + habit_engaged_uids) AS uid
    WITH DISTINCT uid WHERE uid IS NOT NULL
    RETURN collect(uid) AS engaged_uids
}
WITH u, task_engaged_uids, journal_engaged_uids, habit_engaged_uids, engaged_uids

// ── Step 2: Proximal zone — structurally adjacent, not yet engaged ─────────
UNWIND CASE WHEN size(engaged_uids) = 0 THEN [null] ELSE engaged_uids END AS engaged_uid
OPTIONAL MATCH (engaged:Entity {uid: engaged_uid})-[:PREREQUISITE_FOR]->(next:Entity)
OPTIONAL MATCH (engaged:Entity {uid: engaged_uid})-[:COMPLEMENTARY_TO]->(adj:Entity)
// Next step in the same Learning Path: find siblings that come after engaged_uid
OPTIONAL MATCH (lp:Entity)-[:ORGANIZES]->(path_next:Entity)
WHERE (lp)-[:ORGANIZES]->(:Entity {uid: engaged_uid})

WITH task_engaged_uids, journal_engaged_uids, habit_engaged_uids, engaged_uids,
     collect(DISTINCT next.uid) + collect(DISTINCT adj.uid) + collect(DISTINCT path_next.uid)
     AS candidate_uids_raw

// Proximal = adjacent candidates NOT already in current zone, and non-null
WITH task_engaged_uids, journal_engaged_uids, habit_engaged_uids, engaged_uids,
     [uid IN candidate_uids_raw
      WHERE uid IS NOT NULL AND NOT uid IN engaged_uids] AS proximal_uids

// ── Step 3: Prerequisite graph for readiness scoring ─────────────────────
// For each proximal KU, find how many prerequisites it has and how many
// are in the current zone
UNWIND CASE WHEN size(proximal_uids) = 0 THEN [null] ELSE proximal_uids END AS proximal_uid
OPTIONAL MATCH (prox:Entity {uid: proximal_uid})<-[:PREREQUISITE_FOR]-(prereq:Entity)
WITH task_engaged_uids, journal_engaged_uids, habit_engaged_uids,
     engaged_uids, proximal_uids,
     proximal_uid,
     count(prereq) AS total_prereqs,
     count(CASE WHEN prereq.uid IN engaged_uids THEN 1 END) AS met_prereqs

WITH task_engaged_uids, journal_engaged_uids, habit_engaged_uids,
     engaged_uids, proximal_uids,
     collect({
         ku_uid: proximal_uid,
         total: total_prereqs,
         met: met_prereqs
     }) AS prereq_data

// ── Step 4: Engaged Learning Paths ───────────────────────────────────────
OPTIONAL MATCH (lp:Entity {entity_type: 'learning_path'})-[:ORGANIZES]->(step:Entity)
WHERE step.uid IN engaged_uids
WITH task_engaged_uids, journal_engaged_uids, habit_engaged_uids,
     engaged_uids, proximal_uids, prereq_data,
     collect(DISTINCT lp.uid) AS engaged_path_uids

// ── Step 5: Blocking gaps — prerequisites NOT met ────────────────────────
// A blocking gap = a prerequisite KU that is not in current_zone and
// blocks at least one proximal KU
UNWIND CASE WHEN size(proximal_uids) = 0 THEN [null] ELSE proximal_uids END AS p_uid
OPTIONAL MATCH (p:Entity {uid: p_uid})<-[:PREREQUISITE_FOR]-(gap:Entity)
WHERE gap.uid IS NOT NULL AND NOT gap.uid IN engaged_uids

WITH task_engaged_uids, journal_engaged_uids, habit_engaged_uids,
     engaged_uids, proximal_uids, prereq_data, engaged_path_uids,
     collect(DISTINCT gap.uid) AS blocking_gap_uids

// ── Step 6: Submission scores per KU ────────────────────────────────────
// Exercise -> APPLIES_KNOWLEDGE -> Ku, Submission -> FULFILLS_EXERCISE -> Exercise
CALL {
    WITH engaged_uids
    MATCH (es:Entity {entity_type: 'exercise_submission'})-[:FULFILLS_EXERCISE]->(ex:Entity)-[:APPLIES_KNOWLEDGE]->(ku_sub:Entity)
    WHERE es.status IN ['completed', 'approved']
    WITH ku_sub.uid AS sub_ku_uid, max(coalesce(es.score, 0.0)) AS best_score, count(es) AS sub_count
    RETURN collect({ku_uid: sub_ku_uid, best_score: best_score, count: sub_count}) AS submission_data
}

RETURN
    engaged_uids       AS current_zone,
    proximal_uids      AS proximal_zone,
    engaged_path_uids  AS engaged_paths,
    prereq_data        AS prereq_data,
    blocking_gap_uids  AS blocking_gaps,
    task_engaged_uids  AS task_engaged,
    journal_engaged_uids AS journal_engaged,
    habit_engaged_uids AS habit_engaged,
    submission_data    AS submission_data
LIMIT 1
"""

# Targeted KU engagement query — fetch evidence for specific KU UIDs only
# Used by assess_ku_readiness() for query-time ZPD (Socratic pipeline)
_TARGETED_KU_ENGAGEMENT_QUERY = """
// ── Targeted engagement data for specific KUs ──────────────────────────
MATCH (u:User {uid: $user_uid})

// Task engagement: which of the target KUs have tasks that APPLIES_KNOWLEDGE?
OPTIONAL MATCH (u)-[:OWNS]->(t:Entity {entity_type: 'task'})-[:APPLIES_KNOWLEDGE]->(ku_t:Entity)
WHERE ku_t.uid IN $ku_uids
WITH u, collect(DISTINCT ku_t.uid) AS task_engaged_uids

// Journal engagement
OPTIONAL MATCH (u)-[:OWNS]->(j:Entity {entity_type: 'journal_submission'})-[:APPLIES_KNOWLEDGE]->(ku_j:Entity)
WHERE ku_j.uid IN $ku_uids
WITH u, task_engaged_uids, collect(DISTINCT ku_j.uid) AS journal_engaged_uids

// Habit engagement
OPTIONAL MATCH (u)-[:OWNS]->(h:Entity {entity_type: 'habit'})-[:REINFORCES_KNOWLEDGE]->(ku_h:Entity)
WHERE ku_h.uid IN $ku_uids
WITH u, task_engaged_uids, journal_engaged_uids, collect(DISTINCT ku_h.uid) AS habit_engaged_uids

// Submission scores for target KUs
CALL {
    WITH u
    MATCH (es:Entity {entity_type: 'exercise_submission'})-[:FULFILLS_EXERCISE]->(ex:Entity)-[:APPLIES_KNOWLEDGE]->(ku_sub:Entity)
    WHERE ku_sub.uid IN $ku_uids AND es.status IN ['completed', 'approved']
    WITH ku_sub.uid AS sub_ku_uid, max(coalesce(es.score, 0.0)) AS best_score, count(es) AS sub_count
    RETURN collect({ku_uid: sub_ku_uid, best_score: best_score, count: sub_count}) AS submission_data
}

RETURN
    task_engaged_uids    AS task_engaged,
    journal_engaged_uids AS journal_engaged,
    habit_engaged_uids   AS habit_engaged,
    submission_data      AS submission_data
LIMIT 1
"""

# Minimum KU count to consider the curriculum graph "ready"
_MIN_KU_COUNT_QUERY = """
MATCH (ku:Entity {entity_type: 'ku'})
RETURN count(ku) AS ku_count
"""


class ZPDBackend:
    """Neo4j persistence backend for ZPD graph traversals.

    Pure data access — no business logic. Executes Cypher queries and returns
    raw parsed results. Business logic (readiness scoring, behavioral
    enrichment) stays in ZPDService.

    Args:
        driver: Neo4j async driver (injected at bootstrap).
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver
        self._logger = logger

    async def get_ku_count(self) -> int:
        """Count total KUs in the curriculum graph."""
        try:
            records, _, _ = await self._driver.execute_query(_MIN_KU_COUNT_QUERY)
            if records:
                return records[0].get("ku_count", 0) or 0
            return 0
        except Exception as exc:
            self._logger.warning("ZPD: failed to count KUs — %s", exc)
            return 0

    async def get_targeted_ku_engagement(
        self, user_uid: str, ku_uids: list[str]
    ) -> Result[tuple[list[str], list[str], list[str], list[dict[str, Any]]]]:
        """Fetch engagement data for specific KU UIDs only.

        Lightweight alternative to get_zone_data() — queries only the target
        KUs instead of traversing the full curriculum graph. Used by
        ZPDService.assess_ku_readiness() for query-time ZPD in the Socratic pipeline.

        Returns:
            Result containing a tuple of:
                - task_engaged: KU UIDs engaged via tasks
                - journal_engaged: KU UIDs engaged via journals
                - habit_engaged: KU UIDs engaged via habits
                - submission_data: Submission scores per KU
        """
        if not ku_uids:
            return Result.ok(([], [], [], []))

        try:
            records, _, _ = await self._driver.execute_query(
                _TARGETED_KU_ENGAGEMENT_QUERY,
                {"user_uid": user_uid, "ku_uids": ku_uids},
            )
        except Exception as exc:
            self._logger.error("ZPD targeted KU query failed for %s: %s", user_uid, exc)
            return Result.fail(
                Errors.database(
                    operation="ZPDBackend.get_targeted_ku_engagement",
                    message=f"Targeted KU engagement query failed: {exc}",
                )
            )

        if not records:
            return Result.ok(([], [], [], []))

        row = records[0]
        task_engaged: list[str] = list(row.get("task_engaged") or [])
        journal_engaged: list[str] = list(row.get("journal_engaged") or [])
        habit_engaged: list[str] = list(row.get("habit_engaged") or [])
        submission_data: list[dict[str, Any]] = list(row.get("submission_data") or [])

        return Result.ok((task_engaged, journal_engaged, habit_engaged, submission_data))

    async def get_zone_data(
        self, user_uid: str
    ) -> Result[
        tuple[
            list[str],
            list[str],
            list[str],
            list[dict[str, Any]],
            list[str],
            list[str],
            list[str],
            list[str],
            list[dict[str, Any]],
        ]
    ]:
        """Execute the zone traversal query and parse results.

        Returns:
            Result containing a tuple of:
                - current_zone: KU UIDs the user has engaged
                - proximal_zone: Adjacent KU UIDs not yet engaged
                - engaged_paths: Learning Path UIDs the user is on
                - prereq_data: Raw prerequisite counts per proximal KU
                - blocking_gaps: Prerequisite KU UIDs not yet met
                - task_engaged: KU UIDs engaged via tasks
                - journal_engaged: KU UIDs engaged via journals
                - habit_engaged: KU UIDs engaged via habits
                - submission_data: Submission scores per KU
        """
        try:
            records, _, _ = await self._driver.execute_query(_ZONE_QUERY, {"user_uid": user_uid})
        except Exception as exc:
            self._logger.error("ZPD zone query failed for %s: %s", user_uid, exc)
            return Result.fail(
                Errors.database(
                    operation="ZPDBackend.get_zone_data",
                    message=f"ZPD zone query failed: {exc}",
                )
            )

        if not records:
            return Result.ok(([], [], [], [], [], [], [], [], []))

        row = records[0]
        current_zone: list[str] = list(row.get("current_zone") or [])
        proximal_zone: list[str] = list(row.get("proximal_zone") or [])
        engaged_paths: list[str] = list(row.get("engaged_paths") or [])
        blocking_gaps: list[str] = list(row.get("blocking_gaps") or [])
        prereq_data: list[dict[str, Any]] = list(row.get("prereq_data") or [])
        task_engaged: list[str] = list(row.get("task_engaged") or [])
        journal_engaged: list[str] = list(row.get("journal_engaged") or [])
        habit_engaged: list[str] = list(row.get("habit_engaged") or [])
        submission_data: list[dict[str, Any]] = list(row.get("submission_data") or [])

        return Result.ok(
            (
                current_zone,
                proximal_zone,
                engaged_paths,
                prereq_data,
                blocking_gaps,
                task_engaged,
                journal_engaged,
                habit_engaged,
                submission_data,
            )
        )
