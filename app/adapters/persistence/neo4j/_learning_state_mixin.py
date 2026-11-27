"""
Learning State Mixin
====================

User progress tracking operations for domain backends.

Manages learning-state relationships between User and Entity nodes:
VIEWED, IN_PROGRESS, MASTERED, MARKED_AS_READ, BOOKMARKED.

The learner-door writes land on a published PathStep only — the far end is
admitted by the statement that writes the edge. ``mark_mastered`` takes a Ku or a
PathStep, and the reads take any :Entity.

Requires on concrete class:
    execute_query, logger  (provided by UniversalNeo4jBackend)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.query.cypher import (
    CURRICULUM_COMPOSITION_EDGES,
    build_publication_clause,
)
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins
    import logging

    from core.models.type_hints import Neo4jProperties
    from core.ports.query_types import (
        MasteredWriteRow,
        StepHoldRow,
        StepMasteryGapRow,
        StepStartRow,
    )


# The far end of every learner-door write here (VIEWED, IN_PROGRESS, MARKED_AS_READ,
# BOOKMARKED): a PathStep a learner can read. The write's own MATCH admits it, so a
# uid naming another kind of node, another user's entity, a draft or nothing at all
# matches no row and writes nothing — one answer for all of them, which the service
# reports as the step not being found.
_PUBLISHED_STEP, _PUBLISHED_STEP_PARAMS = build_publication_clause("ps")
_MATCH_PUBLISHED_STEP = (
    f"MATCH (ps:{NeoLabel.ENTITY}:{NeoLabel.PATH_STEP} {{uid: $step_uid}}) WHERE {_PUBLISHED_STEP}"
)


# The lock every learner-state write takes first, after binding the learner as ``u``
# (here and on the Ku and User backends: VIEWED, IN_PROGRESS, MASTERED, MARKED_AS_READ,
# BOOKMARKED onto a step or a Ku): a no-op SET takes the learner's exclusive lock, so
# the writes for one learner run one at a time and in one order — the User node, then
# the step or Ku and its edges. Sign-in writes the User node first too
# (``SessionBackend.create_session``). Creating an edge takes a shared lock on each end
# and then upgrades; two writes upgrading on the one User node, or taking the User and
# the step in opposite orders, deadlock, and an auto-commit statement answers a
# deadlock as an error.
LOCK_LEARNER = "SET u.uid = u.uid WITH u"


def _step_params(user_uid: UserUID, step_uid: str, **extra: str | int) -> dict[str, str | int]:
    return {"user_uid": user_uid, "step_uid": step_uid, **_PUBLISHED_STEP_PARAMS, **extra}


def _to_step_start_rows(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> list[StepStartRow]:
    """Project ``mark_in_progress``'s rows onto StepStartRow (KeyError on alias drift)."""
    return [
        {
            "mastered": bool(row["mastered"]),
            "held": bool(row["held"]),
            "started": bool(row["started"]),
            "capped": bool(row["capped"]),
        }
        for row in records
    ]


def _to_step_hold_rows(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> list[StepHoldRow]:
    """Project a held-step write's rows onto StepHoldRow (KeyError on alias drift)."""
    return [{"held": bool(row["held"]), "mastered": bool(row["mastered"])} for row in records]


def to_mastered_write_rows(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> list[MasteredWriteRow]:
    """Project a MASTERED writer's rows onto MasteredWriteRow (KeyError on alias drift).

    Shared by every writer of the edge — ``_LearningStateMixin.mark_mastered``,
    ``KuBackend.mark_mastered`` and ``UserBackend.record_knowledge_mastery`` —
    so the transition flag has one spelling.
    """
    return [
        {"mastery_score": float(row["mastery_score"]), "was_mastered": bool(row["was_mastered"])}
        for row in records
    ]


class _LearningStateMixin:
    """User progress tracking operations (VIEWED, IN_PROGRESS, MASTERED, etc.).

    Hosted by ``PsBackend``. The learner-door writes (``record_view``,
    ``mark_in_progress``, ``mark_as_learning``, ``mark_as_read``,
    ``create_bookmark``) land on a published PathStep only and return no row for
    any other uid. ``mark_mastered`` serves a Ku or a PathStep — its callers name a
    Ku a report or self-report mastered, or a step derived from its Kus — and the
    reads take any :Entity.

    Requires on concrete class:
        execute_query: async (query, params) -> Result[list[dict]]
        logger: logging.Logger
    """

    if TYPE_CHECKING:
        logger: logging.Logger

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[builtins.list[dict[str, Any]]]: ...

    # ========================================================================
    # STATE TRANSITION METHODS
    # ========================================================================

    async def record_view(
        self, user_uid: UserUID, ku_uid: str, now: str, time_spent: int
    ) -> Result[list[Neo4jProperties]]:
        """MERGE VIEWED onto a published PathStep, tracking timestamps and count."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        {LOCK_LEARNER}
        {_MATCH_PUBLISHED_STEP}
        MERGE (u)-[r:VIEWED]->(ps)
        ON CREATE SET
            r.first_viewed_at = datetime($now),
            r.last_viewed_at = datetime($now),
            r.view_count = 1,
            r.time_spent_seconds = $time_spent
        ON MATCH SET
            r.last_viewed_at = datetime($now),
            r.view_count = COALESCE(r.view_count, 0) + 1,
            r.time_spent_seconds = COALESCE(r.time_spent_seconds, 0) + $time_spent
        RETURN r.view_count as view_count
        """
        return await self.execute_query(
            query, _step_params(user_uid, ku_uid, now=now, time_spent=time_spent)
        )

    async def mark_in_progress(
        self, user_uid: UserUID, ku_uid: str, now: str, cap: int
    ) -> Result[list[StepStartRow]]:
        """Start a published PathStep for the user, under the enrollment cap; one statement.

        The verdict is decided BY the write (ADR-087): the statement locks the learner's
        ``User`` node before it reads anything, so every start for one learner runs one at
        a time and the tally it reads is the tally it writes against. Under that lock it
        reads whether the learner mastered the step (mastery is terminal: nothing is
        written), whether they already hold it (no new slot: only ``last_activity_at``
        moves), and how many steps they hold; a new start is written only while they
        hold fewer than ``cap``.

        The tally is every PathStep the learner holds IN_PROGRESS, a draft included —
        the set ``get_in_progress_path_step_uids`` lists.

        Lock order: the ``User`` node (``SET u.uid = u.uid``, a no-op that takes its
        exclusive lock), then the step and the edge — the order every learner-state
        write takes (``LOCK_LEARNER``).

        One row for a published step — ``mastered``, ``held`` (before this write),
        ``started`` (the edge was created) and ``capped`` (refused for the cap); no row
        for any other uid.
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        {LOCK_LEARNER}
        {_MATCH_PUBLISHED_STEP}
        WITH u, ps,
             EXISTS {{ (u)-[:MASTERED]->(ps) }} AS mastered,
             EXISTS {{ (u)-[:IN_PROGRESS]->(ps) }} AS held,
             COUNT {{ (u)-[:IN_PROGRESS]->(:{NeoLabel.ENTITY}:{NeoLabel.PATH_STEP}) }} AS holding
        WITH u, ps, mastered, held, NOT mastered AND NOT held AND holding >= $cap AS capped
        FOREACH (_ IN CASE WHEN mastered OR capped THEN [] ELSE [1] END |
            MERGE (u)-[r:IN_PROGRESS]->(ps)
            ON CREATE SET
                r.started_at = datetime($now),
                r.last_activity_at = datetime($now),
                r.progress_score = 0.0
            ON MATCH SET
                r.last_activity_at = datetime($now)
        )
        RETURN mastered, held, capped, NOT (mastered OR held OR capped) AS started
        """
        result = await self.execute_query(query, _step_params(user_uid, ku_uid, now=now, cap=cap))
        if result.is_error:
            return Result.fail(result)
        return Result.ok(_to_step_start_rows(result.value or []))

    async def mark_as_learning(self, user_uid: UserUID, ku_uid: str) -> Result[list[StepHoldRow]]:
        """Delete MARKED_AS_READ from a published PathStep the user holds IN_PROGRESS (Review again).

        Writes only when the user holds the step's IN_PROGRESS edge, so it undertakes
        nothing new: a step never started, and a mastered one (whose IN_PROGRESS its
        mastery retired), are left alone. One row for a published step, reporting
        ``held`` and ``mastered``; no row for any other uid.
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        {LOCK_LEARNER}
        {_MATCH_PUBLISHED_STEP}
        OPTIONAL MATCH (u)-[ip:IN_PROGRESS]->(ps)
        OPTIONAL MATCH (u)-[r:MARKED_AS_READ]->(ps)
        FOREACH (_ IN CASE WHEN ip IS NULL THEN [] ELSE [1] END |
            DELETE r
            SET ip.last_activity_at = datetime()
        )
        RETURN ip IS NOT NULL AS held, EXISTS {{ (u)-[:MASTERED]->(ps) }} AS mastered
        """
        result = await self.execute_query(query, _step_params(user_uid, ku_uid))
        if result.is_error:
            return Result.fail(result)
        return Result.ok(_to_step_hold_rows(result.value or []))

    async def mark_as_read(self, user_uid: UserUID, ku_uid: str) -> Result[list[StepHoldRow]]:
        """MERGE MARKED_AS_READ onto a published PathStep the user holds IN_PROGRESS.

        A step the user never started is left alone. One row for a published step,
        reporting ``held`` and ``mastered``; no row for any other uid.
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        {LOCK_LEARNER}
        {_MATCH_PUBLISHED_STEP}
        OPTIONAL MATCH (u)-[ip:IN_PROGRESS]->(ps)
        FOREACH (_ IN CASE WHEN ip IS NULL THEN [] ELSE [1] END |
            MERGE (u)-[r:MARKED_AS_READ]->(ps)
            ON CREATE SET r.marked_at = datetime()
        )
        RETURN ip IS NOT NULL AS held, EXISTS {{ (u)-[:MASTERED]->(ps) }} AS mastered
        """
        result = await self.execute_query(query, _step_params(user_uid, ku_uid))
        if result.is_error:
            return Result.fail(result)
        return Result.ok(_to_step_hold_rows(result.value or []))

    async def mark_mastered(
        self, user_uid: UserUID, entity_uid: str, now: str, mastery_score: float, method: str
    ) -> Result[list[MasteredWriteRow]]:
        """MERGE the MASTERED edge onto a Ku or a PathStep; the higher score wins.

        One writer, one edge shape for both targets: ``mastered_at`` (the
        caller's ISO instant), ``mastery_score``, ``confidence``, ``method``.
        Mastery is the terminal learning state, so the entity's IN_PROGRESS
        edge is retired in the same statement — a mastered step holds no
        enrollment-cap slot (``mark_in_progress``).

        Reports ``was_mastered`` — whether the edge existed before this write —
        so the caller publishes on the transition only, never on a repeat. The
        verdict is decided BY the write (ADR-087): ``MERGE`` sets a marker in
        its ``ON CREATE`` / ``ON MATCH`` branch, under the lock it holds on the
        pair, and the marker is removed before the row is returned. A read
        taken before the ``MERGE`` would let two concurrent first writes both
        report a transition.
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        {LOCK_LEARNER}
        MATCH (entity:Entity {{uid: $entity_uid}})
        MERGE (u)-[r:MASTERED]->(entity)
        ON CREATE SET
            r.mastered_at = datetime($now),
            r.mastery_score = $mastery_score,
            r.confidence = $mastery_score,
            r.method = $method,
            r.transition = true
        ON MATCH SET
            r.mastery_score = CASE
                WHEN $mastery_score > r.mastery_score THEN $mastery_score
                ELSE r.mastery_score
            END,
            r.confidence = CASE
                WHEN $mastery_score > coalesce(r.confidence, 0) THEN $mastery_score
                ELSE r.confidence
            END,
            r.method = $method,
            r.transition = false
        WITH u, entity, r, NOT r.transition AS was_mastered
        REMOVE r.transition
        WITH u, entity, r, was_mastered
        OPTIONAL MATCH (u)-[ip:IN_PROGRESS]->(entity)
        DELETE ip
        RETURN r.mastery_score AS mastery_score, was_mastered
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "entity_uid": entity_uid,
                "now": now,
                "mastery_score": mastery_score,
                "method": method,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(to_mastered_write_rows(result.value or []))

    async def get_in_progress_path_step_uids(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """The uids of the PathSteps the user holds IN_PROGRESS, a draft included: the set
        the enrollment cap counts (``mark_in_progress``)."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:IN_PROGRESS]->(ps:Entity:PathStep)
        RETURN ps.uid AS uid
        ORDER BY ps.title
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    # ========================================================================
    # BOOKMARK OPERATIONS
    # ========================================================================

    async def check_bookmark(self, user_uid: UserUID, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Check if BOOKMARKED relationship exists."""
        query = """
        MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Entity {uid: $ku_uid})
        RETURN r IS NOT NULL as is_bookmarked
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def delete_bookmark(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Delete BOOKMARKED relationship."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        {LOCK_LEARNER}
        MATCH (u)-[r:BOOKMARKED]->(:Entity {{uid: $ku_uid}})
        DELETE r
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def create_bookmark(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """MERGE BOOKMARKED onto a published PathStep; one row when it lands."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        {LOCK_LEARNER}
        {_MATCH_PUBLISHED_STEP}
        MERGE (u)-[r:BOOKMARKED]->(ps)
        ON CREATE SET r.bookmarked_at = datetime()
        RETURN true AS success
        """
        return await self.execute_query(query, _step_params(user_uid, ku_uid))

    # ========================================================================
    # QUERY OPERATIONS
    # ========================================================================

    async def get_learning_state_raw(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Fetch all user-entity learning relationships in one query.

        The user is bound ONCE, optionally, before the edge probes. Binding
        ``u`` inside the first OPTIONAL MATCH would null it for a learner with
        no VIEWED edge, and every later probe on ``u`` would then read null
        too — a step mastered without ever being viewed would report NONE.
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})
        OPTIONAL MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[v:VIEWED]->(ku)
        OPTIONAL MATCH (u)-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u)-[m:MASTERED]->(ku)
        OPTIONAL MATCH (u)-[mr:MARKED_AS_READ]->(ku)
        OPTIONAL MATCH (u)-[bk:BOOKMARKED]->(ku)
        RETURN
            v IS NOT NULL as has_viewed,
            p IS NOT NULL as has_in_progress,
            m IS NOT NULL as has_mastered,
            mr IS NOT NULL as has_marked_as_read,
            bk IS NOT NULL as has_bookmarked,
            v.first_viewed_at as first_viewed_at,
            v.last_viewed_at as last_viewed_at,
            v.view_count as view_count,
            v.time_spent_seconds as time_spent_seconds,
            p.started_at as started_at,
            m.mastered_at as mastered_at
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def get_learning_states_batch_raw(
        self, user_uid: UserUID, ku_uids: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Batch query learning states for multiple KUs (user bound once, as above)."""
        query = """
        UNWIND $ku_uids as ku_uid
        MATCH (ku:Entity {uid: ku_uid})
        OPTIONAL MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[v:VIEWED]->(ku)
        OPTIONAL MATCH (u)-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u)-[m:MASTERED]->(ku)
        RETURN
            ku.uid as ku_uid,
            v IS NOT NULL as has_viewed,
            p IS NOT NULL as has_in_progress,
            m IS NOT NULL as has_mastered
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uids": ku_uids})

    async def detect_path_step_completion(
        self, ku_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Find PathSteps where all KUs are mastered after a KU mastery event.

        Uses the canonical PathStep→Ku triple. ``TRAINS_KU`` (a step's declared
        objectives, from ``trains_ku_uids``) counts toward completion exactly as
        ``USES_KU``/``CONTAINS_KNOWLEDGE`` (its content) does — a step whose
        objectives are unmastered is not complete.

        The composition targets counted are ``:Ku`` only: the edge writer (the
        content-vault sync's) matches its target by uid alone, so a step can
        point one of these edges at another step, and a step's mastery is
        announced as ``PathStepCompleted`` — never ``KnowledgeMastered`` — so
        a non-Ku target in the tally would leave the parent underivable. The
        trigger is ``:Ku`` for the same reason from the other side: a mastery
        announced for a non-Ku uid must not enter the derivation, or a step
        whose only target is another step would tally 0 of 0 and be mastered.

        Publication-gated: a draft step is never derived. Its mastery would be
        a learner-state reference to curriculum the learner never saw, and the
        learner-state reads (``MASTERED_PATH_STEPS_QUERY``) carry no gate of
        their own. A step published later is a gap ``find_step_mastery_gaps``
        reports and the reconciler closes.
        """
        published, published_params = build_publication_clause("ps")
        query = f"""
        MATCH (ps:Entity:PathStep)-[:{CURRICULUM_COMPOSITION_EDGES}]->(ku:Entity:Ku {{uid: $ku_uid}})
        WHERE {published}
        WITH ps
        MATCH (ps)-[:{CURRICULUM_COMPOSITION_EDGES}]->(all_ku:Entity:Ku)
        WITH ps, collect(DISTINCT all_ku.uid) as all_ku_uids, count(DISTINCT all_ku) as total
        OPTIONAL MATCH (user:User {{uid: $user_uid}})-[:MASTERED]->(mastered_ku:Entity)
        WHERE mastered_ku.uid IN all_ku_uids
        WITH ps, total, count(DISTINCT mastered_ku) as mastered_count, all_ku_uids
        WHERE mastered_count = total
        RETURN ps.uid as ps_uid, ps.title as ps_title, all_ku_uids
        """
        return await self.execute_query(
            query, {"ku_uid": ku_uid, "user_uid": user_uid, **published_params}
        )

    async def find_step_mastery_gaps(self) -> Result[list[StepMasteryGapRow]]:
        """Every (user, step) pair where the user has mastered all of the step's
        Kus and the step's own MASTERED edge is absent — across all users.

        The derived writer runs best-effort behind ``KnowledgeMastered``; a
        detection or write that failed after the Ku edge committed leaves this
        gap, and the transition event is not replayed. The reconciler reads the
        gaps from the graph's own state and closes them. The tally is ``:Ku``
        only and the step must be published, as in ``detect_path_step_completion``
        — which is also how a step published after its Kus were mastered gets
        its edge.
        """
        published, published_params = build_publication_clause("ps")
        query = f"""
        MATCH (ps:Entity:PathStep)-[:{CURRICULUM_COMPOSITION_EDGES}]->(ku:Entity:Ku)
        WHERE {published}
        WITH ps, collect(DISTINCT ku) AS kus
        MATCH (user:User)-[:MASTERED]->(mastered:Entity)
        WHERE mastered IN kus
        WITH ps, kus, user, count(DISTINCT mastered) AS mastered_count
        WHERE mastered_count = size(kus) AND NOT EXISTS {{ (user)-[:MASTERED]->(ps) }}
        RETURN user.uid AS user_uid, ps.uid AS ps_uid
        ORDER BY user.uid, ps.uid
        """
        result = await self.execute_query(query, published_params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                {"user_uid": str(r["user_uid"]), "ps_uid": str(r["ps_uid"])}
                for r in (result.value or [])
            ]
        )

    async def get_bookmarked_kus(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all bookmarked KU UIDs for a user."""
        query = """
        MATCH (user:User {uid: $user_uid})-[r:BOOKMARKED]->(ku:Entity)
        RETURN ku.uid as ku_uid
        ORDER BY datetime(r.bookmarked_at) DESC
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def get_all_user_knowledge_status(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get all Ku entities with per-user interaction status."""
        query = """
        MATCH (ku:Entity:Ku)
        OPTIONAL MATCH (u:User {uid: $user_uid})-[v:VIEWED]->(ku)
        OPTIONAL MATCH (u2:User {uid: $user_uid})-[b:BOOKMARKED]->(ku)
        OPTIONAL MATCH (u3:User {uid: $user_uid})-[m:MASTERED]->(ku)
        OPTIONAL MATCH (u4:User {uid: $user_uid})-[ip:IN_PROGRESS]->(ku)
        RETURN ku.uid AS uid, ku.title AS title, ku.domain AS domain,
               v IS NOT NULL AS viewed,
               b IS NOT NULL AS bookmarked,
               m IS NOT NULL AS mastered,
               ip IS NOT NULL AS studying
        ORDER BY ku.title ASC, ku.uid ASC
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def get_user_mastery(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get mastery level for a specific user-KU pair."""
        query = """
        MATCH (user:User {uid: $user_uid})-[r:MASTERED]->(ku:Entity {uid: $ku_uid})
        RETURN r.level as mastery
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})
