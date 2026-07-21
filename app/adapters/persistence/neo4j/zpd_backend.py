"""
ZPD Backend — Neo4j Graph Queries for Zone of Proximal Development
===================================================================

Pure persistence layer for ZPD graph traversals. Owns all Cypher queries
that compute the user's current zone, proximal zone, readiness scores,
blocking gaps, and submission scores from the curriculum graph.

Consumed by: core/services/zpd/zpd_service.py
See: core/ports/zpd_protocols.py — ZPDBackendOperations protocol
See: docs/roadmap/zpd-service-architecture.md — design rationale
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.ports.zpd_protocols import PrereqCount, SubmissionScore

if TYPE_CHECKING:
    from neo4j import AsyncDriver

from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


# ============================================================================
# ZPD EDGE SETS — deliberately different per step, direction-correct
# ============================================================================
#
# THREE distinct traversals, ONE source of truth each. These are NOT
# interchangeable, and they are deliberately NOT `SemanticRelationshipType.is_blocking`:
#
#   - Proximal expansion (Step 2) follows enablement FORWARD — "you engaged A,
#     A enables B → B is proximal". Two enabler vocabularies exist (Codex P2 #600):
#     standalone Edge YAML authors ENABLES (all live enabler edges); the
#     relationship registry maps frontmatter connections.enables →
#     ENABLES_KNOWLEDGE. The proximal expansion must read both, plus the forward
#     prerequisite edge.
#   - Readiness (Step 3) and blocking gaps (Step 5) follow ONLY the prerequisite
#     edge, INCOMING (`<-[:PREREQUISITE_FOR]-`) — an enabler is an invitation,
#     never a gate or a requirement (ruling 2026-07-10).
#
# Why NOT is_blocking (semantic-relationship-layer roadmap Phase 3, resolved
# 2026-07-21): `is_blocking` resolves — via SEMANTIC_TO_RELATIONSHIP_NAME — to the
# coarse edges {REQUIRES_KNOWLEDGE, BLOCKS, PRECEDES}. NONE of those is
# PREREQUISITE_FOR, so wiring ZPD's gate steps to `is_blocking` would silently
# read a disjoint edge set — a regression in "what should I learn next". The
# gate is PREREQUISITE_FOR, full stop. See docs/roadmap/semantic-relationship-layer.md.
#
# Guarded by tests/unit/adapters/test_zpd_backend_query_shape.py (asserts the
# emitted query matches these constants) + tests/integration/test_zpd_enables_proximal.py.

# Step 2 — proximal expansion (forward enablement, Ku- and PS-grain bridge).
_PROXIMAL_EXPANSION_EDGES: tuple[RelationshipName, ...] = (
    RelationshipName.PREREQUISITE_FOR,
    RelationshipName.LATERAL_ENABLES,  # value "ENABLES" — standalone Edge YAML enabler
    RelationshipName.ENABLES_KNOWLEDGE,
)
# Steps 3 & 5 — the prerequisite gate (incoming, prerequisite-only).
_PREREQUISITE_GATE_EDGE: RelationshipName = RelationshipName.PREREQUISITE_FOR

# Cypher edge-union pattern for the proximal expansion (`A|B|C`).
_PROXIMAL_EXPANSION_PATTERN: str = "|".join(e.value for e in _PROXIMAL_EXPANSION_EDGES)


# ============================================================================
# CYPHER QUERIES
# ============================================================================

# Steps 1-6: Current zone (engaged KUs, per-source), proximal zone, readiness,
# engaged paths, blocking gaps, and submission scores — all in a single round-trip.
#
# The proximal-expansion (`zpd_proximal_edges`) and prerequisite-gate
# (`zpd_prereq_gate`) edge sets are substituted from the constants above at
# module load — one source of truth, no buried literals. 17 Cypher map-literal
# brace pairs make f-string interpolation error-prone, so this uses a plain-string
# template + `.replace()` (byte-identical output; the shape test pins it).
_ZONE_QUERY_TEMPLATE = """
// ── Step 1: Current zone — KUs the user has meaningfully engaged ──────────
// Returns per-source lists for compound evidence tracking.
// Activity→knowledge edges target :Entity nodes (ADR-046) — both atomic :Ku and
// :PathStep. Roll up to atomic Ku grain: keep direct :Ku targets and bridge
// :PathStep targets to the Kus they compose via TRAINS_KU|USES_KU.
MATCH (u:User {uid: $user_uid})
OPTIONAL MATCH (u)-[:OWNS]->(t:Entity {entity_type: 'task'})-[:APPLIES_KNOWLEDGE]->(applied_t:Entity)
OPTIONAL MATCH (u)-[:OWNS]->(h:Entity {entity_type: 'habit'})-[:REINFORCES_KNOWLEDGE]->(applied_h:Entity)
OPTIONAL MATCH (u)-[:OWNS]->(ue:Entity:UserEntry)-[:APPLIES_KNOWLEDGE]->(applied_e:Entity)
WITH u,
     collect(DISTINCT applied_t) AS task_applied_nodes,
     collect(DISTINCT applied_h) AS habit_applied_nodes,
     collect(DISTINCT applied_e) AS entry_applied_nodes
// GRAIN CAVEAT: engaged_uids below is atomic Ku grain — correct for current-zone
// evidence (ZoneEvidence) and the Ku↔Ku PREREQUISITE_FOR readiness traversal.
// The LP traversal (Step 2 path-next, Step 4 engaged_paths) matches engaged_uids
// against (lp)-[:ORGANIZES]->(...), which is PathStep grain. That branch is DORMANT
// today (0 learning_path nodes, 0 ORGANIZES edges live), so the grain mismatch is
// inert. When LP/ORGANIZES data is added, carry the original activity→knowledge
// target uids (incl. :PathStep) separately for the LP steps. (Codex P2, PR #247.)
WITH u,
     [n IN task_applied_nodes WHERE n:Ku | n.uid] +
     reduce(acc = [], p IN task_applied_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) | k.uid]) AS task_engaged_raw,
     [n IN habit_applied_nodes WHERE n:Ku | n.uid] +
     reduce(acc = [], p IN habit_applied_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) | k.uid]) AS habit_engaged_raw,
     [n IN entry_applied_nodes WHERE n:Ku | n.uid] +
     reduce(acc = [], p IN entry_applied_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) | k.uid]) AS entry_engaged_raw,
     // RAW (pre-roll-down) engaged entity uids — :Ku AND :PathStep targets.
     // Kept alongside the Ku-grain lists so the PS-level enabler bridge in
     // Step 2 can expand from the entities the activity edges actually hit.
     [n IN task_applied_nodes + habit_applied_nodes + entry_applied_nodes
      WHERE n IS NOT NULL | n.uid] AS engaged_raw_entity_uids
WITH u, engaged_raw_entity_uids,
     [uid IN task_engaged_raw WHERE uid IS NOT NULL | uid] AS task_engaged_uids,
     [uid IN habit_engaged_raw WHERE uid IS NOT NULL | uid] AS habit_engaged_uids,
     [uid IN entry_engaged_raw WHERE uid IS NOT NULL | uid] AS entry_engaged_uids

// Combine all engaged UIDs (deduplicated via UNWIND + DISTINCT, no APOC)
CALL (task_engaged_uids, habit_engaged_uids, entry_engaged_uids) {
    UNWIND (task_engaged_uids + habit_engaged_uids + entry_engaged_uids) AS uid
    WITH DISTINCT uid WHERE uid IS NOT NULL
    RETURN collect(uid) AS engaged_uids
}
WITH u, task_engaged_uids, habit_engaged_uids, entry_engaged_uids, engaged_uids,
     engaged_raw_entity_uids

// PS-level enabler bridge (Codex P2 #600): activity edges target :PathStep as
// well as :Ku (ADR-046), and live PS-[:ENABLES_KNOWLEDGE]->PS edges exist. The
// Ku-grain roll-down above loses the PathStep identity, so enabler edges
// authored AT PathStep grain would never expand. Expand prereq/enabler edges
// from the RAW engaged entities here, then roll enabled PathSteps down to
// their composed Kus — the proximal zone stays Ku-grain (same invariant as
// Step 1's roll-down). Subquery isolates cardinality: one row in, one out.
CALL (engaged_raw_entity_uids) {
    UNWIND CASE WHEN size(engaged_raw_entity_uids) = 0 THEN [null]
           ELSE engaged_raw_entity_uids END AS raw_uid
    OPTIONAL MATCH (src:Entity {uid: raw_uid})
        -[:zpd_proximal_edges]->(target:Entity)
    WITH collect(DISTINCT target) AS targets
    RETURN [t IN targets WHERE t:Ku | t.uid] +
           reduce(acc = [], p IN [t IN targets WHERE t:PathStep] |
                  acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) | k.uid])
           AS bridged_candidate_uids
}
WITH u, task_engaged_uids, habit_engaged_uids, entry_engaged_uids, engaged_uids,
     bridged_candidate_uids

// ── Step 2: Proximal zone — structurally adjacent, not yet engaged ─────────
// Enabler edges join the forward expansion here ONLY (ruling 2026-07-10):
// "you engaged A, A enables B → B is proximal". Readiness (Step 3) and
// blocking gaps (Step 5) stay strictly PREREQUISITE_FOR — an enabler is an
// invitation, never a gate or a requirement.
// TWO enabler vocabularies exist (Codex P2 #600): standalone Edge YAML
// authors ENABLES (all 32 live edges), while the relationship registry maps
// frontmatter connections.enables → ENABLES_KNOWLEDGE — traverse both.
UNWIND CASE WHEN size(engaged_uids) = 0 THEN [null] ELSE engaged_uids END AS engaged_uid
OPTIONAL MATCH (engaged:Entity {uid: engaged_uid})-[:zpd_proximal_edges]->(next:Entity)
OPTIONAL MATCH (engaged:Entity {uid: engaged_uid})-[:COMPLEMENTARY_TO]->(adj:Entity)
// Next step in the same Learning Path: find siblings that come after engaged_uid
OPTIONAL MATCH (lp:Entity)-[:ORGANIZES]->(path_next:Entity)
WHERE (lp)-[:ORGANIZES]->(:Entity {uid: engaged_uid})

WITH task_engaged_uids, habit_engaged_uids, entry_engaged_uids, engaged_uids,
     bridged_candidate_uids,
     collect(DISTINCT next.uid) + collect(DISTINCT adj.uid) + collect(DISTINCT path_next.uid)
     AS expansion_uids
WITH task_engaged_uids, habit_engaged_uids, entry_engaged_uids, engaged_uids,
     expansion_uids + bridged_candidate_uids AS candidate_uids_raw

// Proximal = adjacent candidates NOT already in current zone, non-null,
// deduplicated (the Ku-grain expansion and the PS-enabler bridge can both
// surface the same Ku)
CALL (candidate_uids_raw, engaged_uids) {
    UNWIND CASE WHEN size(candidate_uids_raw) = 0 THEN [null]
           ELSE candidate_uids_raw END AS cuid
    WITH DISTINCT cuid WHERE cuid IS NOT NULL AND NOT cuid IN engaged_uids
    RETURN collect(cuid) AS proximal_uids
}
WITH task_engaged_uids, habit_engaged_uids, entry_engaged_uids, engaged_uids,
     proximal_uids

// ── Step 3: Prerequisite graph for readiness scoring ─────────────────────
// For each proximal KU, find how many prerequisites it has and how many
// are in the current zone
UNWIND CASE WHEN size(proximal_uids) = 0 THEN [null] ELSE proximal_uids END AS proximal_uid
OPTIONAL MATCH (prox:Entity {uid: proximal_uid})<-[:zpd_prereq_gate]-(prereq:Entity)
WITH task_engaged_uids, habit_engaged_uids, entry_engaged_uids,
     engaged_uids, proximal_uids,
     proximal_uid,
     count(prereq) AS total_prereqs,
     count(CASE WHEN prereq.uid IN engaged_uids THEN 1 END) AS met_prereqs

WITH task_engaged_uids, habit_engaged_uids, entry_engaged_uids,
     engaged_uids, proximal_uids,
     collect({
         ku_uid: proximal_uid,
         total: total_prereqs,
         met: met_prereqs
     }) AS prereq_data

// ── Step 4: Engaged Learning Paths ───────────────────────────────────────
// GRAIN CAVEAT (see Step 1): engaged_uids is Ku grain but LPs ORGANIZE PathSteps,
// so this matches only direct-Ku engagements. DORMANT (0 ORGANIZES edges live);
// when LP data lands, match against the original PathStep target uids instead.
OPTIONAL MATCH (lp:Entity {entity_type: 'learning_path'})-[:ORGANIZES]->(step:Entity)
WHERE step.uid IN engaged_uids
WITH task_engaged_uids, habit_engaged_uids, entry_engaged_uids,
     engaged_uids, proximal_uids, prereq_data,
     collect(DISTINCT lp.uid) AS engaged_path_uids

// ── Step 5: Blocking gaps — prerequisites NOT met ────────────────────────
// A blocking gap = a prerequisite KU that is not in current_zone and
// blocks at least one proximal KU
UNWIND CASE WHEN size(proximal_uids) = 0 THEN [null] ELSE proximal_uids END AS p_uid
OPTIONAL MATCH (p:Entity {uid: p_uid})<-[:zpd_prereq_gate]-(gap:Entity)
WHERE gap.uid IS NOT NULL AND NOT gap.uid IN engaged_uids

WITH task_engaged_uids, habit_engaged_uids, entry_engaged_uids,
     engaged_uids, proximal_uids, prereq_data, engaged_path_uids,
     collect(DISTINCT gap.uid) AS blocking_gap_uids

// ── Step 6: Submission scores per KU ────────────────────────────────────
// Exercise -> APPLIES_KNOWLEDGE -> Ku, Submission -> FULFILLS_EXERCISE -> Exercise
CALL () {
    MATCH (owner:User {uid: $user_uid})-[:OWNS]->(es:Entity:UserEntry)-[:FULFILLS_EXERCISE]->(ex:Entity)-[:APPLIES_KNOWLEDGE]->(ku_sub:Entity)
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
    habit_engaged_uids AS habit_engaged,
    entry_engaged_uids AS entry_engaged,
    submission_data    AS submission_data
LIMIT 1
"""

# Substitute the edge-set sentinels from the constants above — single source of
# truth, byte-identical to the historical literals (pinned by the shape test).
_ZONE_QUERY = _ZONE_QUERY_TEMPLATE.replace(
    "zpd_proximal_edges", _PROXIMAL_EXPANSION_PATTERN
).replace("zpd_prereq_gate", _PREREQUISITE_GATE_EDGE.value)


# Targeted KU engagement query — fetch evidence for specific KU UIDs only
# Used by assess_ku_readiness() for query-time ZPD (Socratic pipeline)
_TARGETED_KU_ENGAGEMENT_QUERY = """
// ── Targeted engagement data for specific KUs ──────────────────────────
MATCH (u:User {uid: $user_uid})

// Task engagement: which of the target KUs have tasks that APPLIES_KNOWLEDGE?
// Roll up to atomic Ku grain (ADR-046): direct :Ku targets + Kus composed by a
// :PathStep target via TRAINS_KU|USES_KU. The $ku_uids filter applies to the
// final atomic Ku uid, after the PathStep→Ku bridge.
OPTIONAL MATCH (u)-[:OWNS]->(t:Entity {entity_type: 'task'})-[:APPLIES_KNOWLEDGE]->(applied_t:Entity)
WITH u, collect(DISTINCT applied_t) AS task_applied_nodes
WITH u,
     [n IN task_applied_nodes WHERE n:Ku AND n.uid IN $ku_uids | n.uid] +
     reduce(acc = [], p IN task_applied_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) WHERE k.uid IN $ku_uids | k.uid])
     AS task_engaged_uids

// Habit engagement
OPTIONAL MATCH (u)-[:OWNS]->(h:Entity {entity_type: 'habit'})-[:REINFORCES_KNOWLEDGE]->(applied_h:Entity)
WITH u, task_engaged_uids, collect(DISTINCT applied_h) AS habit_applied_nodes
WITH u, task_engaged_uids,
     [n IN habit_applied_nodes WHERE n:Ku AND n.uid IN $ku_uids | n.uid] +
     reduce(acc = [], p IN habit_applied_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) WHERE k.uid IN $ku_uids | k.uid])
     AS habit_engaged_uids

// Entry engagement — (UserEntry)-[:APPLIES_KNOWLEDGE]->(Ku), ADR-069
OPTIONAL MATCH (u)-[:OWNS]->(ue:Entity:UserEntry)-[:APPLIES_KNOWLEDGE]->(applied_e:Entity)
WITH u, task_engaged_uids, habit_engaged_uids, collect(DISTINCT applied_e) AS entry_applied_nodes
WITH u, task_engaged_uids, habit_engaged_uids,
     [n IN entry_applied_nodes WHERE n:Ku AND n.uid IN $ku_uids | n.uid] +
     reduce(acc = [], p IN entry_applied_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) WHERE k.uid IN $ku_uids | k.uid])
     AS entry_engaged_uids

// Submission scores for target KUs
CALL (u) {
    MATCH (u)-[:OWNS]->(es:Entity:UserEntry)-[:FULFILLS_EXERCISE]->(ex:Entity)-[:APPLIES_KNOWLEDGE]->(ku_sub:Entity)
    WHERE ku_sub.uid IN $ku_uids AND es.status IN ['completed', 'approved']
    WITH ku_sub.uid AS sub_ku_uid, max(coalesce(es.score, 0.0)) AS best_score, count(es) AS sub_count
    RETURN collect({ku_uid: sub_ku_uid, best_score: best_score, count: sub_count}) AS submission_data
}

RETURN
    task_engaged_uids    AS task_engaged,
    habit_engaged_uids   AS habit_engaged,
    entry_engaged_uids   AS entry_engaged,
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
        except NEO4J_EXCEPTIONS as exc:
            self._logger.warning("ZPD: failed to count KUs — %s", exc)
            return 0

    async def get_targeted_ku_engagement(
        self, user_uid: UserUID, ku_uids: list[str]
    ) -> Result[tuple[list[str], list[str], list[str], list[SubmissionScore]]]:
        """Fetch engagement data for specific KU UIDs only.

        Lightweight alternative to get_zone_data() — queries only the target
        KUs instead of traversing the full curriculum graph. Used by
        ZPDService.assess_ku_readiness() for query-time ZPD in the Socratic pipeline.

        Returns:
            Result containing a tuple of:
                - task_engaged: KU UIDs engaged via tasks
                - habit_engaged: KU UIDs engaged via habits
                - entry_engaged: KU UIDs engaged via user entries (ADR-069)
                - submission_data: Submission scores per KU
        """
        if not ku_uids:
            return Result.ok(([], [], [], []))

        try:
            records, _, _ = await self._driver.execute_query(
                _TARGETED_KU_ENGAGEMENT_QUERY,
                {"user_uid": user_uid, "ku_uids": ku_uids},
            )
        except NEO4J_EXCEPTIONS as exc:
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
        habit_engaged: list[str] = list(row.get("habit_engaged") or [])
        entry_engaged: list[str] = list(row.get("entry_engaged") or [])
        # boundary: Neo4j Record row shape is fixed by the RETURN projection
        # in _TARGETED_KU_ENGAGEMENT_QUERY's submission_data collect{...}.
        submission_data: list[SubmissionScore] = [
            cast("SubmissionScore", item) for item in (row.get("submission_data") or [])
        ]

        return Result.ok((task_engaged, habit_engaged, entry_engaged, submission_data))

    async def get_zone_data(
        self, user_uid: UserUID
    ) -> Result[
        tuple[
            list[str],
            list[str],
            list[str],
            list[PrereqCount],
            list[str],
            list[str],
            list[str],
            list[str],
            list[SubmissionScore],
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
                - habit_engaged: KU UIDs engaged via habits
                - entry_engaged: KU UIDs engaged via user entries (ADR-069)
                - submission_data: Submission scores per KU
        """
        try:
            records, _, _ = await self._driver.execute_query(_ZONE_QUERY, {"user_uid": user_uid})
        except NEO4J_EXCEPTIONS as exc:
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
        # boundary: row shapes fixed by the RETURN projection in _ZONE_QUERY's
        # prereq_data and submission_data collect{...} steps.
        prereq_data: list[PrereqCount] = [
            cast("PrereqCount", item) for item in (row.get("prereq_data") or [])
        ]
        task_engaged: list[str] = list(row.get("task_engaged") or [])
        habit_engaged: list[str] = list(row.get("habit_engaged") or [])
        entry_engaged: list[str] = list(row.get("entry_engaged") or [])
        submission_data: list[SubmissionScore] = [
            cast("SubmissionScore", item) for item in (row.get("submission_data") or [])
        ]

        return Result.ok(
            (
                current_zone,
                proximal_zone,
                engaged_paths,
                prereq_data,
                blocking_gaps,
                task_engaged,
                habit_engaged,
                entry_engaged,
                submission_data,
            )
        )
