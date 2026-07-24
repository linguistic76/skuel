"""
Knowledge Context Mixin
=======================

Context, discovery, and readiness operations for domain backends.

Provides graph context queries (full neighborhood, USES_KU linking),
application discovery (connected activities, PS/LP containing KU), and
learning readiness (ready to learn, gaps, reinforcement, recommendations,
prerequisite linking).

Requires on concrete class:
    execute_query, logger  (provided by UniversalNeo4jBackend)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j._backend_helpers import _ALLOWED_ORDER_BY, _validate_rel_name
from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    import logging

    from core.models.enums.neo_labels import NeoLabel
    from core.models.relationship_names import RelationshipName
    from core.models.type_hints import Neo4jProperties


class _KnowledgeContextMixin:
    """Context, discovery, and readiness operations.

    Domain backends that need knowledge graph context queries should add
    ``_KnowledgeContextMixin`` to their class bases.

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
    # GRAPH CONTEXT QUERIES
    # ========================================================================

    async def get_with_context_raw(
        self, uid: str, min_confidence: float
    ) -> Result[list[Neo4jProperties]]:
        """Fetch entity with full graph neighborhood in one query."""
        query = """
        MATCH (ku:Entity {uid: $uid})

        OPTIONAL MATCH (ku)-[r1:REQUIRES_KNOWLEDGE]->(prereq:Entity)
        WHERE coalesce(r1.confidence, 1.0) >= $min_confidence
        WITH ku, collect(DISTINCT {
            uid: prereq.uid,
            title: prereq.title,
            confidence: coalesce(r1.confidence, 1.0)
        }) as prerequisites

        OPTIONAL MATCH (dependent:Entity)-[r2:REQUIRES_KNOWLEDGE]->(ku)
        WHERE coalesce(r2.confidence, 1.0) >= $min_confidence
        WITH ku, prerequisites, collect(DISTINCT {
            uid: dependent.uid,
            title: dependent.title,
            confidence: coalesce(r2.confidence, 1.0)
        }) as dependents

        OPTIONAL MATCH (ku)-[r3:RELATED_TO]-(related:Entity)
        WHERE coalesce(r3.confidence, 1.0) >= $min_confidence * 0.85
        WITH ku, prerequisites, dependents, collect(DISTINCT {
            uid: related.uid,
            title: related.title,
            confidence: coalesce(r3.confidence, 1.0),
            relationship_type: type(r3)
        }) as related

        OPTIONAL MATCH (ku)<-[:MASTERED]-(user:User)
        WITH ku, prerequisites, dependents, related, count(DISTINCT user) as mastery_count

        OPTIONAL MATCH (ku)-[]-(shared)-[]-(similar:Entity)
        WHERE similar <> ku
        WITH ku, prerequisites, dependents, related, mastery_count,
             similar, count(DISTINCT shared) as shared_count

        WITH ku, prerequisites, dependents, related, mastery_count,
             collect(DISTINCT {
                 uid: similar.uid,
                 title: similar.title,
                 shared_neighbors: shared_count
             }) as all_similar

        WITH ku, prerequisites, dependents, related, mastery_count,
             [s IN all_similar WHERE s.shared_neighbors >= 2][0..5] as similar_knowledge

        RETURN ku, prerequisites, dependents, related, mastery_count, similar_knowledge
        """
        return await self.execute_query(query, {"uid": uid, "min_confidence": min_confidence})

    # ========================================================================
    # PATHSTEP-KU LINKING
    # ========================================================================

    async def link_to_ku(self, ps_uid: str, ku_uid: str) -> Result[bool]:
        """Create USES_KU relationship from PathStep to atomic Ku."""
        query = """
        MATCH (ps:Entity {uid: $ps_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (ps)-[r:USES_KU]->(ku)
        RETURN true AS success
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid, "ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(
                Errors.not_found(resource="PathStep or Ku", identifier=f"{ps_uid} / {ku_uid}")
            )
        return Result.ok(True)

    async def get_used_kus(self, ps_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all atomic Kus used by a PathStep via USES_KU."""
        query = """
        MATCH (ps:Entity {uid: $ps_uid})-[:USES_KU]->(ku:Entity)
        RETURN ku.uid AS uid, ku.title AS title
        ORDER BY ku.title
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    # ========================================================================
    # APPLICATION DISCOVERY
    # ========================================================================

    async def find_connected_activities(
        self,
        ku_uid: str,
        user_uid: UserUID,
        node_label: NeoLabel,
        rel_types: list[RelationshipName | str],
        filters: dict[str, Any] | None = None,
        order_by: str = "created_at",
        limit: int = 10,
        reverse_direction: bool = False,
    ) -> Result[list[Neo4jProperties]]:
        """Find activity entities connected to a KU via graph relationships."""
        from core.models.enums.neo_labels import NeoLabel as NeoLabelEnum
        from core.models.relationship_names import RelationshipName as RelNameEnum

        # Validate order_by against whitelist (prevents Cypher injection)
        if order_by not in _ALLOWED_ORDER_BY:
            return Result.fail(Errors.validation(f"Invalid order_by field: {order_by!r}"))

        # Validate relationship types (enum .value or pre-validated strings)
        rel_values = [r.value if isinstance(r, RelNameEnum) else r for r in rel_types]
        for rv in rel_values:
            _validate_rel_name(rv)

        # NeoLabel is a StrEnum — .value is safe for interpolation
        label = node_label.value if isinstance(node_label, NeoLabelEnum) else str(node_label)

        rel_pattern = "|".join(rel_values)
        if reverse_direction:
            match_clause = f"MATCH (n:{label})-[:{rel_pattern}]<-(ku:Entity)"
        else:
            match_clause = f"MATCH (n:{label})-[:{rel_pattern}]->(ku:Entity)"

        conditions = ["ku.uid = $ku_uid", "n.user_uid = $user_uid"]
        params: dict[str, Any] = {"ku_uid": ku_uid, "user_uid": user_uid, "limit": limit}

        if filters:
            for condition_fragment, filter_params in filters.items():
                conditions.append(condition_fragment)
                params.update(filter_params)

        where_clause = " AND ".join(conditions)

        query = f"""
        {match_clause}
        WHERE {where_clause}
        RETURN n.uid as entity_uid
        ORDER BY n.{order_by} DESC
        LIMIT $limit
        """
        return await self.execute_query(query, params)

    async def find_path_steps_containing_ku(
        self, ku_uid: str, limit: int = 10
    ) -> Result[list[Neo4jProperties]]:
        """Find path steps that contain/teach a KU via CONTAINS_KNOWLEDGE."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})<-[:CONTAINS_KNOWLEDGE]-(ps:PathStep)
        RETURN ps.uid as step_uid
        ORDER BY ps.sequence_number ASC
        LIMIT $limit
        """
        return await self.execute_query(query, {"ku_uid": ku_uid, "limit": limit})

    async def find_learning_paths_teaching_ku(
        self, ku_uid: str, limit: int = 10
    ) -> Result[list[Neo4jProperties]]:
        """Find learning paths that teach a KU via PathStep chain."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})<-[:CONTAINS_KNOWLEDGE]-(ps:PathStep)<-[:HAS_STEP]-(lp:LearningPath)
        RETURN DISTINCT lp.uid as path_uid
        ORDER BY lp.created_at DESC
        LIMIT $limit
        """
        return await self.execute_query(query, {"ku_uid": ku_uid, "limit": limit})

    # ========================================================================
    # LEARNING READINESS
    # ========================================================================

    async def find_ready_to_learn(
        self, mastered_uids: list[str], domain: str | None, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Find KUs the user is ready to learn (prerequisites >= 70% met)."""
        query = """
        MATCH (ku:Entity)
        WHERE NOT ku.uid IN $mastered_uids
          AND ($domain IS NULL OR ku.domain = $domain)

        // Count prerequisites and how many user has mastered
        OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
        WITH ku,
             collect(prereq.uid) as prereq_uids,
             count(prereq) as total_prereqs

        // Calculate readiness based on prerequisites
        WITH ku, prereq_uids, total_prereqs,
             size([p IN prereq_uids WHERE p IN $mastered_uids]) as satisfied_prereqs

        WITH ku, prereq_uids, total_prereqs, satisfied_prereqs,
             CASE
               WHEN total_prereqs = 0 THEN 1.0
               ELSE toFloat(satisfied_prereqs) / total_prereqs
             END as readiness

        // Filter for ready-to-learn (>= 70% prerequisites met)
        WHERE readiness >= 0.7

        // Get what this enables (dependents)
        OPTIONAL MATCH (ku)<-[:REQUIRES_KNOWLEDGE]-(dependent:Entity)

        RETURN ku.uid as uid,
               ku.title as title,
               ku.domain as domain,
               ku.summary as summary,
               readiness,
               total_prereqs,
               satisfied_prereqs,
               prereq_uids,
               count(dependent) as dependent_count
        ORDER BY readiness DESC, dependent_count DESC
        LIMIT $limit
        """
        return await self.execute_query(
            query, {"mastered_uids": mastered_uids, "domain": domain, "limit": limit}
        )

    async def find_learning_gaps(
        self, goal_uids: list[str], mastered_uids: list[str], limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Find KUs required by goals but not mastered."""
        query = """
        MATCH (goal:Goal)-[:REQUIRES_KNOWLEDGE]->(ku:Entity)
        WHERE goal.uid IN $goal_uids
          AND NOT ku.uid IN $mastered_uids

        // Count how many goals need this knowledge
        WITH ku, count(DISTINCT goal) as goals_blocked,
             collect(DISTINCT goal.uid) as blocking_goal_uids

        // Get prerequisite info
        OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
        WITH ku, goals_blocked, blocking_goal_uids,
             count(prereq) as prereq_count,
             collect(prereq.uid) as prereq_uids

        // Calculate how many prereqs are satisfied
        WITH ku, goals_blocked, blocking_goal_uids, prereq_count, prereq_uids,
             size([p IN prereq_uids WHERE p IN $mastered_uids]) as satisfied_prereqs

        RETURN ku.uid as uid,
               ku.title as title,
               ku.domain as domain,
               goals_blocked,
               blocking_goal_uids,
               prereq_count,
               satisfied_prereqs,
               CASE
                 WHEN prereq_count = 0 THEN 1.0
                 ELSE toFloat(satisfied_prereqs) / prereq_count
               END as readiness
        ORDER BY goals_blocked DESC, readiness DESC
        LIMIT $limit
        """
        return await self.execute_query(
            query, {"goal_uids": goal_uids, "mastered_uids": mastered_uids, "limit": limit}
        )

    async def find_reinforcement_candidates(
        self, uids: list[str], active_goal_uids: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Get KU details + goal relevance for reinforcement candidates."""
        query = """
        UNWIND $uids as uid
        MATCH (ku:Entity {uid: uid})

        // Check if this knowledge is used by active goals
        OPTIONAL MATCH (goal:Goal)-[:REQUIRES_KNOWLEDGE]->(ku)
        WHERE goal.uid IN $active_goal_uids

        WITH ku, count(goal) as goal_relevance

        // Check what depends on this knowledge
        OPTIONAL MATCH (ku)<-[:REQUIRES_KNOWLEDGE]-(dependent:Entity)

        RETURN ku.uid as uid,
               ku.title as title,
               ku.domain as domain,
               goal_relevance,
               count(dependent) as dependent_count
        """
        return await self.execute_query(query, {"uids": uids, "active_goal_uids": active_goal_uids})

    async def link_prerequisite(
        self, unit_uid: str, prereq_uid: str, is_mandatory: bool
    ) -> Result[list[Neo4jProperties]]:
        """Create REQUIRES_KNOWLEDGE relationship between two entities."""
        query = """
        MATCH (unit:Entity {uid: $unit_uid})
        MATCH (prereq:Entity {uid: $prereq_uid})
        MERGE (unit)-[r:REQUIRES_KNOWLEDGE]->(prereq)
        SET r.is_mandatory = $is_mandatory
        SET r.created_at = datetime()
        RETURN r
        """
        return await self.execute_query(
            query, {"unit_uid": unit_uid, "prereq_uid": prereq_uid, "is_mandatory": is_mandatory}
        )

    async def link_parent_child(
        self, parent_uid: str, child_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create HAS_NARROWER hierarchy relationship."""
        query = """
        MATCH (parent:Entity {uid: $parent_uid})
        MATCH (child:Entity {uid: $child_uid})
        MERGE (parent)-[r:HAS_NARROWER]->(child)
        SET r.created_at = datetime()
        RETURN r
        """
        return await self.execute_query(query, {"parent_uid": parent_uid, "child_uid": child_uid})

    async def query_user_mastery_for_prereqs(
        self, user_uid: UserUID, prereq_uids: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Query user MASTERED + IN_PROGRESS state for prerequisite KUs."""
        query = """
        MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[m:MASTERED]->(k:Entity)
        WHERE k.uid IN $prereq_uids
        RETURN k.uid as ku_uid,
               m.mastery_score as score,
               m.confidence_level as confidence,
               m.last_practiced as last_practiced
        UNION
        MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[ip:IN_PROGRESS]->(k:Entity)
        WHERE k.uid IN $prereq_uids
        RETURN k.uid as ku_uid,
               ip.progress as score,
               coalesce(ip.difficulty_rating, 0.5) as confidence,
               ip.last_accessed as last_practiced
        """
        return await self.execute_query(query, {"user_uid": user_uid, "prereq_uids": prereq_uids})

    async def find_learning_recommendations(
        self, user_uid: UserUID, domain: str | None, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Find KUs user is ready to learn based on mastery and prerequisites."""
        query = """
        // Get user's mastered knowledge
        MATCH (u:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
        WITH u, collect(mastered.uid) as mastered_uids

        // Find knowledge units not yet mastered
        MATCH (candidate:Entity)
        WHERE NOT candidate.uid IN mastered_uids
          AND ($domain IS NULL OR candidate.domain = $domain)

        // Count prerequisites and how many are satisfied
        OPTIONAL MATCH (candidate)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
        WITH candidate, mastered_uids,
             count(prereq) as total_prereqs,
             sum(CASE WHEN prereq.uid IN mastered_uids THEN 1 ELSE 0 END) as satisfied_prereqs

        // Calculate readiness score
        WITH candidate,
             total_prereqs,
             satisfied_prereqs,
             CASE
               WHEN total_prereqs = 0 THEN 1.0
               ELSE toFloat(satisfied_prereqs) / total_prereqs
             END as readiness

        // Only recommend if readiness >= 0.7 (most prereqs done)
        WHERE readiness >= 0.7

        // Get next steps info (what this enables)
        OPTIONAL MATCH (candidate)<-[:REQUIRES_KNOWLEDGE]-(enables:Entity)
        WITH candidate, readiness, total_prereqs, satisfied_prereqs,
             count(enables) as enables_count

        RETURN candidate.uid as uid,
               candidate.title as title,
               candidate.summary as summary,
               candidate.domain as domain,
               readiness,
               total_prereqs,
               satisfied_prereqs,
               enables_count
        ORDER BY readiness DESC, enables_count DESC
        LIMIT $limit
        """
        return await self.execute_query(
            query, {"user_uid": user_uid, "domain": domain, "limit": limit}
        )

    # ========================================================================
    # RESOURCE CITATION QUERIES (migrated from ContextRetriever)
    # ========================================================================

    async def get_exercises_for_path_step(self, ps_uid: str) -> Result[list[Neo4jProperties]]:
        """Get exercises linked to a PathStep via HAS_EXERCISE.

        Returns basic exercise details (uid, title, scope, estimated_time_minutes)
        so the PathStep detail page can render an exercises section with submit links.

        Args:
            ps_uid: PathStep UID.

        Returns:
            List of records with exercise uid, title, scope, estimated_time_minutes.
        """
        query = """
        MATCH (ps:Entity {uid: $ps_uid, entity_type: 'path_step'})-[:HAS_EXERCISE]->(e:Entity {entity_type: 'exercise'})
        RETURN e.uid AS uid, e.title AS title, e.scope AS scope,
               e.estimated_time_minutes AS estimated_time_minutes
        ORDER BY e.title
        """
        return await self.execute_query(query, {"ps_uid": ps_uid})

    async def get_cited_resources(
        self, source_uids: list[str], limit: int = 20
    ) -> Result[list[Neo4jProperties]]:
        """Get Resources cited by PathSteps/KUs via CITES_RESOURCE.

        Rows are ranked by the citing source's position in ``source_uids``
        before the limit applies, so callers can express priority through list
        order (the Askesis bundle leads with the anchor PathStep — without the
        ranking, ``LIMIT`` without ``ORDER BY`` could drop the anchor's own
        citations on large bundles).

        Args:
            source_uids: UIDs of PathSteps/KUs to traverse from, highest
                priority first.
            limit: Maximum number of resources to return.

        Returns:
            List of records with a 'resource' key (resource properties) and a
            'locator' key (the CITES_RESOURCE edge's free-string anchor, or null
            for a whole-work citation).
        """
        query = """
        MATCH (source:Entity)-[cite:CITES_RESOURCE]->(r:Resource)
        WHERE source.uid IN $source_uids
        WITH r, cite.locator AS locator,
             min([i IN range(0, size($source_uids) - 1)
                  WHERE $source_uids[i] = source.uid][0]) AS source_rank
        ORDER BY source_rank
        RETURN r {.*} AS resource, locator
        LIMIT $limit
        """
        return await self.execute_query(query, {"source_uids": source_uids, "limit": limit})

    async def get_ku_lateral_edges(
        self, ku_uids: list[str], limit: int = 20
    ) -> Result[list[Neo4jProperties]]:
        """Get Ku↔Ku lateral edges touching any of the given KUs.

        Matches the six lateral relationship families (RELATED_TO,
        PREREQUISITE_FOR/DEPENDS_ON, ALTERNATIVE_TO, COMPLEMENTARY_TO,
        SIBLING, BLOCKS/BLOCKED_BY — see RELATIONSHIPS_ARCHITECTURE.md) where
        EITHER endpoint is in ``ku_uids`` — a bundle KU can be the source or
        the target of an authored connection. Both endpoints must be KUs,
        matched by ``entity_type``, never by UID prefix (ADR-013 never-sniff
        rule).

        Edge-file ingestion copies ``evidence`` (plus confidence/source) onto
        any relationship type, so it rides along here (null for edges authored
        without evidence) — SURFACE_CONNECTION prompts ground the connection
        in that authored text.

        Args:
            ku_uids: KU UIDs to anchor the search (typically the bundle's KUs).
            limit: Maximum number of edges to return.

        Returns:
            Records with source_uid, source_title, target_uid, target_title,
            relationship_type, evidence.
        """
        query = """
        MATCH (a:Entity {entity_type: 'ku'})
              -[r:RELATED_TO|PREREQUISITE_FOR|DEPENDS_ON|ALTERNATIVE_TO|COMPLEMENTARY_TO|SIBLING|BLOCKS|BLOCKED_BY]->
              (b:Entity {entity_type: 'ku'})
        WHERE a.uid IN $ku_uids OR b.uid IN $ku_uids
        RETURN a.uid AS source_uid, a.title AS source_title,
               b.uid AS target_uid, b.title AS target_title,
               type(r) AS relationship_type, r.evidence AS evidence
        ORDER BY relationship_type, source_uid, target_uid
        LIMIT $limit
        """
        return await self.execute_query(query, {"ku_uids": ku_uids, "limit": limit})
