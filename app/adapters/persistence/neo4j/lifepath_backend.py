"""
LifePath Backend
================

Backend for life path designation, alignment, and related graph operations.
Does NOT extend UniversalNeo4jBackend — takes a Neo4jQueryExecutor directly.

Migrates 12 execute_query calls:
- LifePathAlignmentService (7 calls)
- LifePathCoreService (5 calls)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.query.cypher import CURRICULUM_COMPOSITION_EDGES
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.relationship_names import RelationshipName
from core.ports.query_types import (
    LifePathActivityCounts,
    LifePathComposition,
    LifePathKuMasteryRow,
    LifePathMomentumCounts,
    LifePathServingCounts,
    LifePathStepRow,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

# Habits reach knowledge over REINFORCES_KNOWLEDGE; tasks over
# APPLIES_KNOWLEDGE. Matching BOTH and telling the channels apart by the
# activity's entity_type is the same rule _USER_KNOWLEDGE_CHANNELS_QUERY
# follows, and it is the drift-proof one: reading habits over
# APPLIES_KNOWLEDGE matched zero rows silently for as long as it existed,
# because Neo4j does not object to an edge type nothing writes.
_ACTIVITY_KNOWLEDGE_EDGES = (
    f"{RelationshipName.APPLIES_KNOWLEDGE.value}|{RelationshipName.REINFORCES_KNOWLEDGE.value}"
)


# The designated path and the steps it composes, in one pass. OPTIONAL so a
# designated path that composes nothing still returns its title — that is a real
# state ("add steps to your Life Path"), and an inner MATCH would report it as
# "no such path".
#
# The min() collapses to ONE row per step. HAS_STEP is not constrained unique,
# and a step held by two edges would otherwise be counted twice in the alignment
# denominator — an over-return, which reads as a longer path rather than as a
# bug. Same rule the engaged-step read applies over its engagement edges.
_LIFE_PATH_COMPOSITION_QUERY = """
MATCH (lp:Entity {uid: $life_path_uid, entity_type: $life_path_type})
OPTIONAL MATCH (lp)-[r:HAS_STEP]->(ps:Entity {entity_type: $path_step_type})
WITH lp, ps, min(r.sequence) AS sequence
ORDER BY sequence, ps.uid
RETURN lp.uid AS life_path_uid, lp.title AS life_path_title,
       ps.uid AS ps_uid, ps.title AS ps_title, sequence
"""


def _to_life_path_composition(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> LifePathComposition | None:
    """Project raw rows onto LifePathComposition (KeyError on alias drift).

    Indexes every alias rather than ``.get``-ing it: the annotation alone is an
    unchecked claim, and a renamed RETURN would type-check while the caller read
    the missing title as "Unknown" and the missing steps as "this path composes
    nothing" — a confident zero rather than a failure.

    No rows means no such life path. A single row whose ``ps_uid`` is NULL is the
    OPTIONAL MATCH reporting a path with no steps, which is a composition with an
    empty ``steps`` list, not a missing one.
    """
    if not records:
        return None
    steps: list[LifePathStepRow] = [
        {
            "ps_uid": str(row["ps_uid"]),
            "title": str(row["ps_title"] or ""),
            "sequence": None if row["sequence"] is None else int(row["sequence"]),
        }
        for row in records
        if row["ps_uid"]
    ]
    return {
        "life_path_uid": str(records[0]["life_path_uid"]),
        "life_path_title": str(records[0]["life_path_title"] or ""),
        "steps": steps,
    }


# A goal counts toward the goal dimension while it is being pursued. The
# retired second entry, 'in_progress', is not an EntityStatus member and no
# writer sets it — a literal that widened the filter by exactly nothing.
_ACTIVE_GOAL_STATUSES: list[str] = [EntityStatus.ACTIVE.value]

# Momentum counts the creation of new path-aligned COMMITMENTS. Tasks and
# habits both qualify; goals and principles have dimensions of their own, and
# counting them here would score the same fact twice.
_MOMENTUM_ACTIVITY_TYPES: list[str] = [EntityType.TASK.value, EntityType.HABIT.value]


# Mastery per Ku, LEFT-joined so an untouched Ku scores 0.0 and STAYS in the
# denominator. `mastery_level` is NOT a number: _AdaptiveMixin is its only
# writer and sets the strings 'introduced'/'proficient'. `mastery_score` is the
# continuous 0-1 signal the other four MASTERED writers set — and an
# _AdaptiveMixin edge, which carries no score, still means mastered, so its
# existence scores 1.0.
#
# The max() collapses to ONE row per Ku: a Ku taught by two of the path's steps
# is one piece of knowledge to master, and two rows would weight it twice in the
# mean the service takes.
_LIFE_PATH_KU_MASTERY_QUERY = f"""
MATCH (lp:Entity {{uid: $life_path_uid, entity_type: $life_path_type}})
      -[:{RelationshipName.HAS_STEP.value}]->(ps:Entity {{entity_type: $path_step_type}})
      -[:{CURRICULUM_COMPOSITION_EDGES}]->(ku:Entity {{entity_type: $ku_type}})
OPTIONAL MATCH (u:User {{uid: $user_uid}})-[m:{RelationshipName.MASTERED.value}]->(ku)
WITH ku.uid AS ku_uid,
     max(CASE WHEN m IS NULL THEN 0.0
              ELSE coalesce(m.mastery_score, 1.0) END) AS mastery
RETURN ku_uid, mastery
"""

# The path's Ku set is gathered under an OPTIONAL MATCH so a designated path
# that teaches nothing yields an EMPTY set and one row, not zero rows. The
# difference matters: zero rows reads back as "no data", while the truth is
# "you own N activities and none of them can align" — a real, scoreable state.
_LIFE_PATH_ACTIVITY_COUNTS_QUERY = f"""
MATCH (lp:Entity {{uid: $life_path_uid, entity_type: $life_path_type}})
OPTIONAL MATCH (lp)-[:{RelationshipName.HAS_STEP.value}]->(ps:Entity {{entity_type: $path_step_type}})
      -[:{CURRICULUM_COMPOSITION_EDGES}]->(ku:Entity {{entity_type: $ku_type}})
WITH collect(DISTINCT ku.uid) AS lp_knowledge

MATCH (u:User {{uid: $user_uid}})
OPTIONAL MATCH (u)-[:{RelationshipName.OWNS.value}]->(t:Entity {{entity_type: $task_type}})
WITH u, lp_knowledge, count(DISTINCT t) AS total_tasks

OPTIONAL MATCH (u)-[:{RelationshipName.OWNS.value}]->(at:Entity {{entity_type: $task_type}})
      -[:{_ACTIVITY_KNOWLEDGE_EDGES}]->(tk:Entity)
WHERE tk.uid IN lp_knowledge
WITH u, lp_knowledge, total_tasks, count(DISTINCT at) AS aligned_tasks

OPTIONAL MATCH (u)-[:{RelationshipName.OWNS.value}]->(h:Entity {{entity_type: $habit_type}})
WITH u, lp_knowledge, total_tasks, aligned_tasks, count(DISTINCT h) AS total_habits

OPTIONAL MATCH (u)-[:{RelationshipName.OWNS.value}]->(ah:Entity {{entity_type: $habit_type}})
      -[:{_ACTIVITY_KNOWLEDGE_EDGES}]->(hk:Entity)
WHERE hk.uid IN lp_knowledge
WITH total_tasks, aligned_tasks, total_habits, count(DISTINCT ah) AS aligned_habits

RETURN total_tasks, aligned_tasks, total_habits, aligned_habits
"""

_LIFE_PATH_GOAL_COUNTS_QUERY = f"""
MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(g:Entity {{entity_type: $goal_type}})
WHERE g.status IN $active_statuses
OPTIONAL MATCH (g)-[:{RelationshipName.SERVES_LIFE_PATH.value}]->
      (lp:Entity {{uid: $life_path_uid, entity_type: $life_path_type}})
RETURN count(g) AS total, count(lp) AS serving
"""

_LIFE_PATH_PRINCIPLE_COUNTS_QUERY = f"""
MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(p:Entity {{entity_type: $principle_type}})
WHERE p.status = $active_status
OPTIONAL MATCH (p)-[:{RelationshipName.SERVES_LIFE_PATH.value}]->
      (lp:Entity {{uid: $life_path_uid, entity_type: $life_path_type}})
RETURN count(p) AS total, count(lp) AS serving
"""

# Both week legs OPTIONAL — see get_life_path_momentum_counts. Activities are
# selected by entity_type over the shared edge alternation, the same rule
# _USER_KNOWLEDGE_CHANNELS_QUERY uses, so a habit is counted through the edge it
# is actually written with.
_LIFE_PATH_MOMENTUM_COUNTS_QUERY = f"""
MATCH (lp:Entity {{uid: $life_path_uid, entity_type: $life_path_type}})
OPTIONAL MATCH (lp)-[:{RelationshipName.HAS_STEP.value}]->(ps:Entity {{entity_type: $path_step_type}})
      -[:{CURRICULUM_COMPOSITION_EDGES}]->(ku:Entity {{entity_type: $ku_type}})
WITH collect(DISTINCT ku.uid) AS lp_knowledge

OPTIONAL MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(recent:Entity)
      -[:{_ACTIVITY_KNOWLEDGE_EDGES}]->(rk:Entity)
WHERE recent.entity_type IN $momentum_types
  AND rk.uid IN lp_knowledge
  AND datetime(recent.created_at) >= datetime($seven_days_ago)
WITH lp_knowledge, count(DISTINCT recent) AS recent_count

OPTIONAL MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(prior:Entity)
      -[:{_ACTIVITY_KNOWLEDGE_EDGES}]->(pk:Entity)
WHERE prior.entity_type IN $momentum_types
  AND pk.uid IN lp_knowledge
  AND datetime(prior.created_at) >= datetime($fourteen_days_ago)
  AND datetime(prior.created_at) < datetime($seven_days_ago)
WITH recent_count, count(DISTINCT prior) AS previous_count

RETURN recent_count AS recent, previous_count AS previous
"""


def _to_ku_mastery_rows(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> list[LifePathKuMasteryRow]:
    """Project raw rows onto LifePathKuMasteryRow (KeyError on alias drift).

    Indexes every alias rather than ``.get``-ing it. A renamed RETURN would
    type-check while the caller read every mastery as 0.0 and reported a learner
    who has mastered their whole path as having mastered none of it — a
    confident zero, which is the failure mode this area keeps producing.
    """
    return [
        {"ku_uid": str(row["ku_uid"]), "mastery": float(row["mastery"] or 0.0)}
        for row in records
        if row["ku_uid"]
    ]


def _to_activity_counts(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> LifePathActivityCounts:
    """Project the single counts row onto LifePathActivityCounts.

    No rows means no such user or no such life path; both are "nothing owned
    here", which scores identically to a learner who owns nothing.
    """
    if not records:
        return {"total_tasks": 0, "aligned_tasks": 0, "total_habits": 0, "aligned_habits": 0}
    row = records[0]
    return {
        "total_tasks": int(row["total_tasks"] or 0),
        "aligned_tasks": int(row["aligned_tasks"] or 0),
        "total_habits": int(row["total_habits"] or 0),
        "aligned_habits": int(row["aligned_habits"] or 0),
    }


def _to_serving_counts(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> LifePathServingCounts:
    """Project the single counts row onto LifePathServingCounts."""
    if not records:
        return {"total": 0, "serving": 0}
    row = records[0]
    return {"total": int(row["total"] or 0), "serving": int(row["serving"] or 0)}


def _to_momentum_counts(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> LifePathMomentumCounts:
    """Project the single counts row onto LifePathMomentumCounts."""
    if not records:
        return {"recent": 0, "previous": 0}
    row = records[0]
    return {"recent": int(row["recent"] or 0), "previous": int(row["previous"] or 0)}


class LifePathBackend:
    """Backend for life path designation and alignment operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    async def get_life_path_composition(
        self, life_path_uid: str
    ) -> Result[LifePathComposition | None]:
        """The designated path's title and the PathSteps it composes, in order.

        Composition travels over ``HAS_STEP`` — the edge the designation writes
        against — never over a node property. ``PathStep.knowledge_uids``, which
        the alignment metric used to read, is populated on no node in the live
        graph; the composition has always lived on edges.

        Returns None when no such life path exists. Note the ``entity_type``
        discriminators are parameters: a designated path is an ordinary
        LearningPath node whose ``entity_type`` was flipped in place, so this
        read is keyed on the property, and a re-normalised vocabulary must break
        loudly here rather than match zero rows.
        """
        return await self._executor.execute(
            query=_LIFE_PATH_COMPOSITION_QUERY,
            params={
                "life_path_uid": life_path_uid,
                "life_path_type": EntityType.LIFE_PATH.value,
                "path_step_type": EntityType.PATH_STEP.value,
            },
            processor=_to_life_path_composition,
            operation="get_life_path_composition",
        )

    # ========================================================================
    # Core Service — Designation CRUD
    # ========================================================================

    async def get_designation(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get user's life path designation and vision data."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            OPTIONAL MATCH (u)-[r:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
            RETURN u.vision_statement AS vision_statement,
                   u.vision_themes AS vision_themes,
                   u.vision_captured_at AS vision_captured_at,
                   lp.uid AS life_path_uid,
                   r.designated_at AS designated_at,
                   r.alignment_score AS alignment_score
            """,
            {"user_uid": user_uid},
        )

    async def save_vision(
        self,
        user_uid: str,
        vision_statement: str,
        vision_themes: list[str],
        captured_at: str,
    ) -> Result[list[dict[str, Any]]]:
        """Save vision statement and themes on User node."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            SET u.vision_statement = $vision_statement,
                u.vision_themes = $vision_themes,
                u.vision_captured_at = $captured_at
            RETURN u.uid AS user_uid
            """,
            {
                "user_uid": user_uid,
                "vision_statement": vision_statement,
                "vision_themes": vision_themes,
                "captured_at": captured_at,
            },
        )

    async def designate_life_path(
        self,
        user_uid: str,
        life_path_uid: str,
        designated_at: str,
    ) -> Result[list[dict[str, Any]]]:
        """Designate LP as life path: remove old designation, create new ULTIMATE_PATH."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})
            MATCH (lp:Entity {uid: $life_path_uid, entity_type: 'learning_path'})

            // Revert previous designation's entity_type back to learning_path
            OPTIONAL MATCH (u)-[old:ULTIMATE_PATH]->(old_lp:Entity {entity_type: 'life_path'})
            SET old_lp.entity_type = 'learning_path'
            DELETE old

            // Create new designation and promote entity_type
            WITH u, lp
            CREATE (u)-[r:ULTIMATE_PATH {designated_at: $designated_at}]->(lp)
            SET lp.entity_type = 'life_path'

            RETURN u.vision_statement AS vision_statement,
                   u.vision_themes AS vision_themes,
                   u.vision_captured_at AS vision_captured_at,
                   lp.uid AS life_path_uid,
                   r.designated_at AS designated_at
            """,
            {
                "user_uid": user_uid,
                "life_path_uid": life_path_uid,
                "designated_at": designated_at,
            },
        )

    async def remove_designation(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Remove ULTIMATE_PATH and revert entity_type to learning_path."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[r:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
            SET lp.entity_type = 'learning_path'
            DELETE r
            RETURN count(r) > 0 AS removed
            """,
            {"user_uid": user_uid},
        )

    async def update_alignment_score(self, params: dict[str, Any]) -> Result[list[dict[str, Any]]]:
        """Update alignment scores on the ULTIMATE_PATH relationship."""
        # Build query dynamically based on whether dimension scores are provided
        has_dimensions = "knowledge_alignment" in params

        query = """
        MATCH (u:User {uid: $user_uid})-[r:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
        SET r.alignment_score = $alignment_score,
            r.alignment_level = $alignment_level,
            r.alignment_updated_at = datetime()
        """

        if has_dimensions:
            query += """,
            r.knowledge_alignment = $knowledge_alignment,
            r.activity_alignment = $activity_alignment,
            r.goal_alignment = $goal_alignment,
            r.principle_alignment = $principle_alignment,
            r.momentum = $momentum
            """

        query += "\nRETURN r.alignment_score AS score"

        return await self._executor.execute_query(query, params)

    async def record_alignment_snapshot(
        self, user_uid: str, score: float
    ) -> Result[list[dict[str, Any]]]:
        """Record today's alignment score as a daily snapshot (idempotent per day)."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
            MERGE (u)-[r:ALIGNMENT_SNAPSHOT {date: date()}]->(lp)
            ON CREATE SET r.score = $score, r.recorded_at = datetime()
            ON MATCH SET r.score = $score, r.recorded_at = datetime()
            RETURN r.score AS score, toString(r.date) AS date_str
            """,
            {"user_uid": user_uid, "score": score},
        )

    async def get_alignment_snapshots(
        self, user_uid: str, days: int = 31
    ) -> Result[list[dict[str, Any]]]:
        """Get daily alignment snapshots for trend analysis, newest first."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
            MATCH (u)-[r:ALIGNMENT_SNAPSHOT]->(lp)
            WHERE r.recorded_at >= datetime() - duration({days: $days})
            RETURN r.score AS score, toString(r.date) AS date_str
            ORDER BY r.recorded_at DESC
            """,
            {"user_uid": user_uid, "days": days},
        )

    # ========================================================================
    # Alignment Service — Graph Queries
    # ========================================================================

    async def get_user_life_path(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get user's designated life path UID."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:ULTIMATE_PATH]->(lp:Entity {entity_type: 'life_path'})
            RETURN lp.uid AS life_path_uid
            """,
            {"user_uid": user_uid},
        )

    async def get_life_path_ku_mastery(
        self, user_uid: str, life_path_uid: str
    ) -> Result[list[LifePathKuMasteryRow]]:
        """The learner's MASTERED level for every Ku the designated path teaches.

        One row per Ku, mastery 0.0 where the learner has no MASTERED edge — a
        LEFT join over the whole path, so a Ku they have never touched stays in
        the denominator rather than vanishing from it.

        Returns mastery ALONE. The substance half of the knowledge dimension is
        deliberately not computed here: it belongs to the one weight table in
        ``core/services/knowledge/user_substance.py``, and summing it inside this
        query with hand-copied per-instance weights is precisely how the habit
        channel came to be read over ``APPLIES_KNOWLEDGE`` — an edge no habit
        writer emits — and to be worth exactly zero.

        Backend: HAS_STEP → composition-edge traversal, LEFT join on MASTERED.
        """
        return await self._executor.execute(
            query=_LIFE_PATH_KU_MASTERY_QUERY,
            params={
                "user_uid": user_uid,
                "life_path_uid": life_path_uid,
                "life_path_type": EntityType.LIFE_PATH.value,
                "path_step_type": EntityType.PATH_STEP.value,
                "ku_type": EntityType.KU.value,
            },
            processor=_to_ku_mastery_rows,
            operation="get_life_path_ku_mastery",
        )

    async def get_life_path_activity_counts(
        self, user_uid: str, life_path_uid: str
    ) -> Result[LifePathActivityCounts]:
        """How many of the learner's tasks and habits point at the life path.

        Raw counts — the ratio, the task/habit blend and the no-data rule are
        scoring policy and live in ``LifePathAlignmentService``, so they have one
        home instead of one copy per dimension query.

        Habits are matched over the SAME edge alternation as tasks and told apart
        by ``entity_type``; habits reach knowledge over REINFORCES_KNOWLEDGE, and
        a query naming only APPLIES_KNOWLEDGE counted every habit as unaligned
        while still counting it in the denominator — which made building a habit
        toward your life path LOWER your alignment.

        Backend: OWNS → activity-knowledge traversal against the path's Ku set.
        """
        return await self._executor.execute(
            query=_LIFE_PATH_ACTIVITY_COUNTS_QUERY,
            params={
                "user_uid": user_uid,
                "life_path_uid": life_path_uid,
                "life_path_type": EntityType.LIFE_PATH.value,
                "path_step_type": EntityType.PATH_STEP.value,
                "ku_type": EntityType.KU.value,
                "task_type": EntityType.TASK.value,
                "habit_type": EntityType.HABIT.value,
            },
            processor=_to_activity_counts,
            operation="get_life_path_activity_counts",
        )

    async def get_life_path_goal_counts(
        self, user_uid: str, life_path_uid: str
    ) -> Result[LifePathServingCounts]:
        """Active goals owned by the learner, and how many SERVE the life path.

        Backend: OWNS → SERVES_LIFE_PATH, counted not scored.
        """
        return await self._executor.execute(
            query=_LIFE_PATH_GOAL_COUNTS_QUERY,
            params={
                "user_uid": user_uid,
                "life_path_uid": life_path_uid,
                "life_path_type": EntityType.LIFE_PATH.value,
                "goal_type": EntityType.GOAL.value,
                "active_statuses": _ACTIVE_GOAL_STATUSES,
            },
            processor=_to_serving_counts,
            operation="get_life_path_goal_counts",
        )

    async def get_life_path_principle_counts(
        self, user_uid: str, life_path_uid: str
    ) -> Result[LifePathServingCounts]:
        """Active principles owned by the learner, and how many SERVE the path.

        Backend: OWNS → SERVES_LIFE_PATH, counted not scored.
        """
        return await self._executor.execute(
            query=_LIFE_PATH_PRINCIPLE_COUNTS_QUERY,
            params={
                "user_uid": user_uid,
                "life_path_uid": life_path_uid,
                "life_path_type": EntityType.LIFE_PATH.value,
                "principle_type": EntityType.PRINCIPLE.value,
                "active_status": EntityStatus.ACTIVE.value,
            },
            processor=_to_serving_counts,
            operation="get_life_path_principle_counts",
        )

    async def get_life_path_momentum_counts(
        self,
        user_uid: str,
        life_path_uid: str,
        seven_days_ago: str,
        fourteen_days_ago: str,
    ) -> Result[LifePathMomentumCounts]:
        """Path-aligned commitments CREATED in the recent vs the previous week.

        Counts tasks and habits alike: committing to a habit that reinforces the
        path is momentum in the week you commit to it, and the arm that counted
        only tasks left the heaviest substance channel unable to move the
        dimension at all.

        Both week legs are OPTIONAL by design — a learner whose aligned activity
        dropped to zero must score as DECLINING, and an inner MATCH would collapse
        the query to no rows, which the service reads back as the neutral "no
        data" default: the opposite signal.

        Backend: OWNS → activity-knowledge traversal, windowed on created_at.
        """
        return await self._executor.execute(
            query=_LIFE_PATH_MOMENTUM_COUNTS_QUERY,
            params={
                "user_uid": user_uid,
                "life_path_uid": life_path_uid,
                "life_path_type": EntityType.LIFE_PATH.value,
                "path_step_type": EntityType.PATH_STEP.value,
                "ku_type": EntityType.KU.value,
                "momentum_types": _MOMENTUM_ACTIVITY_TYPES,
                "seven_days_ago": seven_days_ago,
                "fourteen_days_ago": fourteen_days_ago,
            },
            processor=_to_momentum_counts,
            operation="get_life_path_momentum_counts",
        )
