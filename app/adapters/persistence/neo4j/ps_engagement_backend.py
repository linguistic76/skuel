"""
PS Engagement Backend
=====================

All Cypher for the PathStep engagement lifecycle (ADR-059), below the hexagonal
boundary. Parameterized queries run via an injected ``Neo4jQueryExecutor``;
relationship types come from the closed ``RelationshipName`` enum and the
``timestamp_field`` / ``rel_value`` interpolations are constrained, caller-only
values — never user input.

Implements ``PsEngagementOperations`` (``core/ports/ps_engagement_protocols.py``).
Returns raw property-dict rows; ``PsEngagementService`` and its helpers
reconstruct the ``Engagement`` / ``TemplateBundle`` / ``ReviewItem`` domain
objects above the boundary.

See: /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.activity_enums import EngagementState
from core.models.relationship_names import RelationshipName
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

_ENGAGED_WITH = RelationshipName.ENGAGED_WITH.value
_OWNS = RelationshipName.OWNS.value
# An instance's engagement_state — the spawn orchestrator writes it through
# EngagementState, so every read and write here binds it from the enum too.
_INSTANCE_STATE_PARAMS = {
    "engaged_state": EngagementState.ENGAGED.value,
    "owned_state": EngagementState.OWNED.value,
}

# The instances the (student, PS) pair's ACTIVE engagement spawned, bound as
# ``n`` with their template as ``t``. Owned is kept in the state list for a
# completion that failed part-way, leaving the engagement active with some of
# its instances already owned; an earlier engagement's owned instances carry
# that engagement's uid and are out of reach.
_ACTIVE_ENGAGEMENT_INSTANCES = f"""
        MATCH (u:User {{uid: $student_uid}})-[e:{_ENGAGED_WITH}]->(:Entity {{uid: $ps_uid}})
        WHERE e.state = 'engaged'
        MATCH (u)-[:{_OWNS}]->(n)-[sf:SPAWNED_FROM]->(t)
        WHERE sf.engagement_uid = e.uid
          AND n.engagement_state IN [$engaged_state, $owned_state]"""


class PsEngagementBackend:
    """Cypher backend for the 4-transition PathStep engagement lifecycle."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    # ------------------------------------------------------------------
    # ENGAGED_WITH edge
    # ------------------------------------------------------------------

    async def find_active_engagement(
        self, student_uid: str, ps_uid: str
    ) -> Result[list[dict[str, Any]]]:
        query = f"""
        MATCH (u:User {{uid: $student_uid}})-[r:{_ENGAGED_WITH}]->(ps {{uid: $ps_uid}})
        WHERE r.state = 'engaged'
        RETURN r.uid AS uid,
               r.since AS since,
               r.state AS state,
               r.completed_at AS completed_at,
               r.abandoned_at AS abandoned_at
        LIMIT 1
        """
        return await self._executor.execute(
            query=query,
            params={"student_uid": student_uid, "ps_uid": ps_uid},
            operation="find_active_engagement",
        )

    async def list_engaged_edges(self, student_uid: str) -> Result[list[dict[str, Any]]]:
        query = f"""
        MATCH (u:User {{uid: $student_uid}})-[r:{_ENGAGED_WITH}]->(ps)
        WHERE r.state = 'engaged'
        RETURN ps.uid AS ps_uid,
               r.uid AS uid,
               r.since AS since,
               r.state AS state,
               r.completed_at AS completed_at,
               r.abandoned_at AS abandoned_at
        """
        return await self._executor.execute(
            query=query,
            params={"student_uid": student_uid},
            operation="list_engaged",
        )

    async def create_engagement_edge(
        self, student_uid: str, ps_uid: str, engagement_uid: str, since: str
    ) -> Result[list[dict[str, Any]]]:
        query = f"""
        MATCH (u:User {{uid: $student_uid}}), (ps {{uid: $ps_uid}})
        CREATE (u)-[r:{_ENGAGED_WITH} {{
            uid: $engagement_uid,
            since: $since,
            state: 'engaged',
            completed_at: null,
            abandoned_at: null
        }}]->(ps)
        RETURN r.uid AS uid,
               r.since AS since,
               r.state AS state,
               r.completed_at AS completed_at,
               r.abandoned_at AS abandoned_at
        """
        return await self._executor.execute_write(
            query=query,
            params={
                "student_uid": student_uid,
                "ps_uid": ps_uid,
                "engagement_uid": engagement_uid,
                "since": since,
            },
            operation="open_engagement",
        )

    async def mark_engagement_terminal(
        self, student_uid: str, ps_uid: str, new_state: str, timestamp_field: str, ts: str
    ) -> Result[list[dict[str, Any]]]:
        # timestamp_field is validated against a whitelist by the caller
        # (_EngagementGateway) — never user input.
        query = f"""
        MATCH (u:User {{uid: $student_uid}})-[r:{_ENGAGED_WITH}]->(ps {{uid: $ps_uid}})
        WHERE r.state = 'engaged'
        SET r.state = $new_state,
            r.{timestamp_field} = $ts
        RETURN r.uid AS uid,
               r.since AS since,
               r.state AS state,
               r.completed_at AS completed_at,
               r.abandoned_at AS abandoned_at
        """
        return await self._executor.execute_write(
            query=query,
            params={
                "student_uid": student_uid,
                "ps_uid": ps_uid,
                "new_state": new_state,
                "ts": ts,
            },
            operation=f"mark_engagement_{new_state}",
        )

    # ------------------------------------------------------------------
    # Template attachment reads
    # ------------------------------------------------------------------

    async def fetch_template_uids(
        self, ps_uid: str, rel_value: str
    ) -> Result[list[dict[str, Any]]]:
        # rel_value is a RelationshipName enum value, not user input.
        query = f"""
        MATCH (ps {{uid: $ps_uid}})-[:{rel_value}]->(t)
        RETURN t.uid AS uid
        ORDER BY t.uid
        """
        return await self._executor.execute(
            query=query,
            params={"ps_uid": ps_uid},
            operation=f"fetch_{rel_value.lower()}_uids",
        )

    # ------------------------------------------------------------------
    # PathStep status (T1 publish)
    # ------------------------------------------------------------------

    async def set_pathstep_published(
        self, ps_uid: str, status: str, updated_at: str
    ) -> Result[list[dict[str, Any]]]:
        # :Entity — the PathStep's :Content shadow shares its uid; unlabeled,
        # this SET would stamp status onto the shadow node too (G13).
        return await self._executor.execute_write(
            query="""
            MATCH (ps:Entity {uid: $uid})
            SET ps.status = $status,
                ps.updated_at = $updated_at
            RETURN ps
            """,
            params={"uid": ps_uid, "status": status, "updated_at": updated_at},
            operation="publish_pathstep",
        )

    # ------------------------------------------------------------------
    # Spawned-instance lifecycle (T3 complete / T4 abandon)
    # ------------------------------------------------------------------

    async def delete_instance(
        self, instance_uid: str, operation: str
    ) -> Result[list[dict[str, Any]]]:
        # :Entity — an unlabeled uid DETACH DELETE could take a :Content
        # shadow node with it (G13); spawned instances are always entities.
        return await self._executor.execute_write(
            query="MATCH (n:Entity {uid: $uid}) DETACH DELETE n",
            params={"uid": instance_uid},
            operation=operation,
        )

    async def mark_instance_owned(
        self, instance_uid: str, updated_at: str
    ) -> Result[list[dict[str, Any]]]:
        return await self._executor.execute_write(
            query="""
            MATCH (n:Entity {uid: $uid})
            SET n.engagement_state = $owned_state,
                n.updated_at = $updated_at
            RETURN n.uid AS uid
            """,
            params={
                "uid": instance_uid,
                "updated_at": updated_at,
                "owned_state": EngagementState.OWNED.value,
            },
            operation="own_instance",
        )

    # ------------------------------------------------------------------
    # Reads over spawned instances
    # ------------------------------------------------------------------

    # An engagement's instances are the ones whose SPAWNED_FROM edge carries
    # its uid — never "instances of a template attached to this step": a
    # template can sit on several steps, and one step can be engaged many
    # times over, so the template names neither the step nor the engagement.

    async def fetch_auto_complete_siblings(
        self, student_uid: str, instance_uid: str
    ) -> Result[list[dict[str, Any]]]:
        query = f"""
        MATCH (n {{uid: $instance_uid, user_uid: $student_uid}})-[sf:SPAWNED_FROM]->()
        WHERE n.engagement_state = $engaged_state
        MATCH (u:User {{uid: $student_uid}})-[e:{_ENGAGED_WITH}]->(ps)
        WHERE e.state = 'engaged' AND e.uid = sf.engagement_uid
        MATCH (u)-[:{_OWNS}]->(other_n)-[other_sf:SPAWNED_FROM]->()
        WHERE other_sf.engagement_uid = e.uid
          AND other_n.engagement_state = $engaged_state
        RETURN ps.uid AS ps_uid,
               collect({{
                 entity_type: other_n.entity_type,
                 status: other_n.status
               }}) AS siblings
        """
        return await self._executor.execute(
            query=query,
            params={
                "student_uid": student_uid,
                "instance_uid": instance_uid,
                "engaged_state": EngagementState.ENGAGED.value,
            },
            operation="check_auto_complete",
        )

    async def list_review_items(
        self, student_uid: str, ps_uid: str
    ) -> Result[list[dict[str, Any]]]:
        query = f"""
        {_ACTIVE_ENGAGEMENT_INSTANCES}
        RETURN t.uid          AS template_uid,
               n.uid           AS instance_uid,
               labels(n)       AS labels,
               coalesce(n.title, n.uid) AS title
        """
        return await self._executor.execute(
            query=query,
            params={"student_uid": student_uid, "ps_uid": ps_uid, **_INSTANCE_STATE_PARAMS},
            operation="list_review_items",
        )

    async def fetch_engaged_instances(
        self, student_uid: str, ps_uid: str
    ) -> Result[list[dict[str, Any]]]:
        query = f"""
        {_ACTIVE_ENGAGEMENT_INSTANCES}
        RETURN t.uid AS template_uid, n.uid AS instance_uid, labels(n) AS labels
        """
        return await self._executor.execute(
            query=query,
            params={"student_uid": student_uid, "ps_uid": ps_uid, **_INSTANCE_STATE_PARAMS},
            operation="fetch_engaged_instances",
        )
