"""
PathStep Intelligence Backend
=============================

Read Cypher for PathStep readiness / practice / guidance analytics, below the
hexagonal boundary. Parameterized queries run via an injected
``Neo4jQueryExecutor``; ``PsIntelligenceService`` keeps the scoring/shaping
(processor) logic above the boundary and delegates the queries here (ADR-044).

Returns per-query typed rows (``core/ports/query_types.py`` ``Ps*Row``) or bool
existence results; the service applies its readiness/score processors to the rows.
The row types are declared on ``PsIntelligenceBackendOperations`` too, so a change
to a RETURN clause's keys is a MyPy error rather than silent drift.

See: /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.ports.query_types import (
    PsGuidanceCountsRow,
    PsPracticeCountsRow,
    PsPrerequisiteStepUidsRow,
    PsTaughtKuUidRow,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


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

        Matches the canonical curriculum-composition triple
        ``USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU`` — the same set the substance
        write fan-out (``KuBackend.increment_substance``) and the UserContext
        MEGA-QUERY Ku-grain rollup traverse. Matching only ``USES_KU`` here
        would make per-user substance blind to TRAINS_KU/CONTAINS_KNOWLEDGE
        links that the fan-out already credits — a read/write asymmetry.
        """
        return await self._executor.execute(
            query="""
                MATCH (:Entity {uid: $ps_uid})-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity {entity_type: 'ku'})
                RETURN DISTINCT ku.uid AS ku_uid
            """,
            params={"ps_uid": ps_uid},
            operation="calculate_user_substance",
        )
