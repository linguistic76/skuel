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

from core.models.relationship_names import RelationshipName
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

_ENGAGED_WITH = RelationshipName.ENGAGED_WITH.value

# The 6 HAS_*_TEMPLATE edges, pre-joined for the spawned-instance traversals.
_HAS_TEMPLATE_EDGES = (
    "HAS_TASK_TEMPLATE"
    "|HAS_GOAL_TEMPLATE"
    "|HAS_HABIT_TEMPLATE"
    "|HAS_EVENT_TEMPLATE"
    "|HAS_CHOICE_TEMPLATE"
    "|HAS_PRINCIPLE_TEMPLATE"
)


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
        RETURN r.since AS since,
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
        self, student_uid: str, ps_uid: str, since: str
    ) -> Result[list[dict[str, Any]]]:
        query = f"""
        MATCH (u:User {{uid: $student_uid}}), (ps {{uid: $ps_uid}})
        CREATE (u)-[r:{_ENGAGED_WITH} {{
            since: $since,
            state: 'engaged',
            completed_at: null,
            abandoned_at: null
        }}]->(ps)
        RETURN r.since AS since,
               r.state AS state,
               r.completed_at AS completed_at,
               r.abandoned_at AS abandoned_at
        """
        return await self._executor.execute_write(
            query=query,
            params={"student_uid": student_uid, "ps_uid": ps_uid, "since": since},
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
        RETURN r.since AS since,
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
            SET n.engagement_state = 'owned',
                n.updated_at = $updated_at
            RETURN n.uid AS uid
            """,
            params={"uid": instance_uid, "updated_at": updated_at},
            operation="own_instance",
        )

    # ------------------------------------------------------------------
    # Reads over spawned instances
    # ------------------------------------------------------------------

    async def fetch_auto_complete_siblings(
        self, student_uid: str, instance_uid: str
    ) -> Result[list[dict[str, Any]]]:
        query = f"""
        MATCH (n {{uid: $instance_uid, user_uid: $student_uid}})-[:SPAWNED_FROM]->(t)
        WHERE n.engagement_state = 'engaged'
        MATCH (ps)-[:{_HAS_TEMPLATE_EDGES}]->(t)
        MATCH (u:User {{uid: $student_uid}})-[e:{_ENGAGED_WITH}]->(ps)
        WHERE e.state = 'engaged'
        WITH ps
        MATCH (other_n {{user_uid: $student_uid}})-[:SPAWNED_FROM]->(other_t)
        MATCH (ps)-[:{_HAS_TEMPLATE_EDGES}]->(other_t)
        WHERE other_n.engagement_state = 'engaged'
        RETURN ps.uid AS ps_uid,
               collect({{
                 entity_type: other_n.entity_type,
                 status: other_n.status
               }}) AS siblings
        LIMIT 1
        """
        return await self._executor.execute(
            query=query,
            params={"student_uid": student_uid, "instance_uid": instance_uid},
            operation="check_auto_complete",
        )

    async def list_review_items(
        self, student_uid: str, ps_uid: str
    ) -> Result[list[dict[str, Any]]]:
        query = f"""
        MATCH (ps {{uid: $ps_uid}})-[:{_HAS_TEMPLATE_EDGES}]->(t)
        MATCH (n {{user_uid: $student_uid}})-[:SPAWNED_FROM]->(t)
        WHERE n.engagement_state IN ['engaged', 'owned']
        RETURN t.uid          AS template_uid,
               n.uid           AS instance_uid,
               labels(n)       AS labels,
               coalesce(n.title, n.uid) AS title
        """
        return await self._executor.execute(
            query=query,
            params={"student_uid": student_uid, "ps_uid": ps_uid},
            operation="list_review_items",
        )

    async def fetch_engaged_instances(
        self, student_uid: str, ps_uid: str
    ) -> Result[list[dict[str, Any]]]:
        query = f"""
        MATCH (ps {{uid: $ps_uid}})-[:{_HAS_TEMPLATE_EDGES}]->(t)
        MATCH (n {{user_uid: $student_uid}})-[:SPAWNED_FROM]->(t)
        WHERE n.engagement_state IN ['engaged', 'owned']
        RETURN t.uid AS template_uid, n.uid AS instance_uid, labels(n) AS labels
        """
        return await self._executor.execute(
            query=query,
            params={"student_uid": student_uid, "ps_uid": ps_uid},
            operation="fetch_engaged_instances",
        )
