"""
PathStep Intelligence Backend
=============================

Read Cypher for PathStep readiness / practice / guidance analytics, below the
hexagonal boundary. Parameterized queries run via an injected
``Neo4jQueryExecutor``; ``PsIntelligenceService`` keeps the scoring/shaping
(processor) logic above the boundary and delegates the queries here (ADR-044).

Returns per-query typed rows (``core/ports/query_types.py`` ``Ps*Row``) or bool
existence results; the service applies its readiness/score processors to the rows.

**The row types are constructed here, not asserted.** ``Neo4jQueryExecutor.execute``
returns the driver's raw ``list[dict[str, Any]]`` untouched when given no processor,
and its generic ``T`` is inferred solely from the call site's return annotation — so a
bare annotation is an *unchecked claim*, and a renamed RETURN alias would type-check
while the service silently read the missing key as zero. Nothing statically links a
Cypher alias to a TypedDict key. The ``_to_*_rows`` processors below are therefore the
actual check: they index each row by its alias, so drift raises ``KeyError`` at this
boundary and surfaces as a failed ``Result`` through the service's
``@with_error_handling`` — loud instead of silent.

See: /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.query.cypher import CURRICULUM_COMPOSITION_EDGES
from core.models.enums import EntityType
from core.ports.query_types import (
    PsGuidanceCountsRow,
    PsPracticeCountsRow,
    PsPrerequisiteStepUidsRow,
    PsStepTaughtKuUidsRow,
    PsTaughtKuUidRow,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


# The four ``_to_*_rows`` processors take the neo4j driver's own row shape, straight
# off ``AsyncResult.data()``. That is a genuine external boundary and cannot be
# narrowed: ``Neo4jProperties`` (the house alias) does not type-check here, because
# ``int()`` rejects its value union and the ``collect()`` list is not iterable as a
# union member. Tier C of the `Any` policy — permanent boundary, marked per site.
# Narrowing happens *inside* each processor: it returns a typed ``Ps*Row``.


def _to_prerequisite_step_uid_rows(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> list[PsPrerequisiteStepUidsRow]:
    """Project raw rows onto PsPrerequisiteStepUidsRow (KeyError on alias drift)."""
    return [{"prereq_uids": [str(uid) for uid in (row["prereq_uids"] or [])]} for row in records]


def _to_practice_counts_rows(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> list[PsPracticeCountsRow]:
    """Project raw rows onto PsPracticeCountsRow (KeyError on alias drift)."""
    return [
        {
            "habits": int(row["habits"]),
            "tasks": int(row["tasks"]),
            "events": int(row["events"]),
            "goals": int(row["goals"]),
            "principles": int(row["principles"]),
            "choices": int(row["choices"]),
        }
        for row in records
    ]


def _to_guidance_counts_rows(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> list[PsGuidanceCountsRow]:
    """Project raw rows onto PsGuidanceCountsRow (KeyError on alias drift)."""
    return [
        {
            "principle_count": int(row["principle_count"]),
            "choice_count": int(row["choice_count"]),
        }
        for row in records
    ]


def _to_taught_ku_uid_rows(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> list[PsTaughtKuUidRow]:
    """Project raw rows onto PsTaughtKuUidRow (KeyError on alias drift).

    Rows with a null ``ku.uid`` are dropped so the declared ``str`` is truthful
    rather than a stringified ``None``.
    """
    return [{"ku_uid": str(row["ku_uid"])} for row in records if row["ku_uid"]]


def _to_step_taught_ku_rows(
    records: list[dict[str, Any]],  # boundary: raw neo4j-driver rows (AsyncResult.data())
) -> list[PsStepTaughtKuUidsRow]:
    """Project raw rows onto PsStepTaughtKuUidsRow (KeyError on alias drift)."""
    return [
        {
            "ps_uid": str(row["ps_uid"]),
            "ku_uids": [str(uid) for uid in (row["ku_uids"] or []) if uid],
        }
        for row in records
        if row["ps_uid"]
    ]


class PsIntelligenceBackend:
    """Cypher backend for PathStep intelligence reads."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    async def fetch_prerequisite_step_uids(
        self, ps_uid: str
    ) -> Result[list[PsPrerequisiteStepUidsRow]]:
        """Return a single row with ``prereq_uids`` (collected REQUIRES_STEP targets)."""
        return await self._executor.execute(
            query="""
                MATCH (ps:Entity {uid: $ps_uid})-[:REQUIRES_STEP]->(prereq:Entity {entity_type: 'path_step'})
                RETURN collect(prereq.uid) as prereq_uids
            """,
            params={"ps_uid": ps_uid},
            processor=_to_prerequisite_step_uid_rows,
            operation="is_ready",
        )

    async def fetch_practice_counts(self, ps_uid: str) -> Result[list[PsPracticeCountsRow]]:
        """Return per-domain practice-opportunity counts for a PathStep."""
        return await self._executor.execute(
            query="""
                MATCH (ps:Entity {uid: $ps_uid})
                OPTIONAL MATCH (ps)-[:BUILDS_HABIT]->(h)
                OPTIONAL MATCH (ps)-[:ASSIGNS_TASK]->(t)
                OPTIONAL MATCH (ps)-[:SCHEDULES_EVENT]->(e)
                OPTIONAL MATCH (ps)-[:SUPPORTS_GOAL]->(g)
                OPTIONAL MATCH (ps)-[:GUIDED_BY_PRINCIPLE]->(p)
                OPTIONAL MATCH (ps)-[:INFORMS_CHOICE]->(c)
                RETURN count(DISTINCT h) as habits,
                       count(DISTINCT t) as tasks,
                       count(DISTINCT e) as events,
                       count(DISTINCT g) as goals,
                       count(DISTINCT p) as principles,
                       count(DISTINCT c) as choices
            """,
            params={"ps_uid": ps_uid},
            processor=_to_practice_counts_rows,
            operation="get_practice_summary",
        )

    async def fetch_guidance_counts(self, ps_uid: str) -> Result[list[PsGuidanceCountsRow]]:
        """Return principle/choice guidance counts for a PathStep."""
        return await self._executor.execute(
            query="""
                MATCH (ps:Entity {uid: $ps_uid})
                OPTIONAL MATCH (ps)-[:GUIDED_BY_PRINCIPLE]->(p)
                OPTIONAL MATCH (ps)-[:INFORMS_CHOICE]->(c)
                RETURN count(DISTINCT p) as principle_count,
                       count(DISTINCT c) as choice_count
            """,
            params={"ps_uid": ps_uid},
            processor=_to_guidance_counts_rows,
            operation="calculate_guidance_strength",
        )

    async def has_prerequisites(self, ps_uid: str) -> Result[bool]:
        """True if the PathStep has REQUIRES_STEP or REQUIRES_KNOWLEDGE edges."""
        return await self._executor.execute_exists(
            query="""
                MATCH (ps:Entity {uid: $ps_uid})
                WHERE exists((ps)-[:REQUIRES_STEP]->()) OR exists((ps)-[:REQUIRES_KNOWLEDGE]->())
                RETURN ps
            """,
            params={"ps_uid": ps_uid},
            operation="has_prerequisites",
        )

    async def has_guidance(self, ps_uid: str) -> Result[bool]:
        """True if the PathStep has principle or choice guidance edges."""
        return await self._executor.execute_exists(
            query="""
                MATCH (ps:Entity {uid: $ps_uid})
                WHERE exists((ps)-[:GUIDED_BY_PRINCIPLE]->())
                   OR exists((ps)-[:INFORMS_CHOICE]->())
                RETURN ps
            """,
            params={"ps_uid": ps_uid},
            operation="has_guidance",
        )

    async def has_practice_opportunities(self, ps_uid: str) -> Result[bool]:
        """True if the PathStep has any of the 6 activity-domain practice edges."""
        return await self._executor.execute_exists(
            query="""
                MATCH (ps:Entity {uid: $ps_uid})
                WHERE exists((ps)-[:BUILDS_HABIT]->())
                   OR exists((ps)-[:ASSIGNS_TASK]->())
                   OR exists((ps)-[:SCHEDULES_EVENT]->())
                   OR exists((ps)-[:SUPPORTS_GOAL]->())
                   OR exists((ps)-[:GUIDED_BY_PRINCIPLE]->())
                   OR exists((ps)-[:INFORMS_CHOICE]->())
                RETURN ps
            """,
            params={"ps_uid": ps_uid},
            operation="has_practice_opportunities",
        )

    async def fetch_taught_ku_uids(self, ps_uid: str) -> Result[list[PsTaughtKuUidRow]]:
        """Return ``ku_uid`` rows for the KUs taught by a PathStep.

        Matches ``CURRICULUM_COMPOSITION_EDGES`` — the same set the substance
        write fan-out (``KuBackend.increment_substance``) and the UserContext
        MEGA-QUERY Ku-grain rollup traverse. Interpolated from that one constant
        rather than spelled out: matching a narrower set here would make
        per-user substance blind to links the fan-out already credits, and a
        hand-copied literal per query is how that asymmetry keeps recurring.
        """
        return await self._executor.execute(
            query=f"""
                MATCH (:Entity {{uid: $ps_uid}})-[:{CURRICULUM_COMPOSITION_EDGES}]->(ku:Entity {{entity_type: $ku_entity_type}})
                RETURN DISTINCT ku.uid AS ku_uid
            """,
            params={"ps_uid": ps_uid, "ku_entity_type": EntityType.KU.value},
            processor=_to_taught_ku_uid_rows,
            operation="calculate_user_substance",
        )

    async def fetch_taught_ku_uids_for_steps(
        self, ps_uids: list[str]
    ) -> Result[list[PsStepTaughtKuUidsRow]]:
        """Return one ``(ps_uid, ku_uids)`` row per requested PathStep.

        The batched form of :meth:`fetch_taught_ku_uids`, for callers scoring a
        whole set of steps at once — the Layer-0 analytics metric holds a
        learner's entire engagement window, and one round trip per step there is
        an N+1 over a set with no upper bound.

        ``UNWIND`` over the input list rather than a single ``IN`` match so a
        step that teaches nothing still comes back, with an empty ``ku_uids``.
        A caller must be able to tell "this step has no Kus" from "this step was
        not in the result", because the first scores 0.0 and belongs in the
        report while the second is a step silently dropped from the denominator.

        Traverses ``CURRICULUM_COMPOSITION_EDGES``, the same constant the
        single-step form and the substance write fan-out agree on. The
        publication gate stays off for the same
        reason it is off on the engagement reads that feed this: the caller
        already holds steps the learner worked, and withholding their
        composition would rewrite past numbers rather than hide new curriculum.
        """
        return await self._executor.execute(
            query=f"""
                UNWIND $ps_uids AS ps_uid
                OPTIONAL MATCH (:Entity {{uid: ps_uid}})-[:{CURRICULUM_COMPOSITION_EDGES}]->(ku:Entity {{entity_type: $ku_entity_type}})
                RETURN ps_uid AS ps_uid, collect(DISTINCT ku.uid) AS ku_uids
            """,
            params={"ps_uids": ps_uids, "ku_entity_type": EntityType.KU.value},
            processor=_to_step_taught_ku_rows,
            operation="calculate_user_substance_for_steps",
        )
