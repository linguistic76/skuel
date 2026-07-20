"""
LP Intelligence Mixin
=====================

Intelligence and adaptive learning operations for LpBackend.

Provides prerequisite validation, blocker identification, path recommendations,
learning sequence discovery, adaptive step selection, and contextual path queries.

Requires on concrete class:
    execute_query, logger  (provided by UniversalNeo4jBackend)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins
    import logging


class _LpIntelligenceMixin:
    """Intelligence and adaptive learning operations.

    Domain backends that need LP intelligence queries should add
    ``_LpIntelligenceMixin`` to their class bases.

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
    # INTELLIGENCE QUERIES (moved from LpIntelligenceService)
    # ========================================================================

    @staticmethod
    def _build_prerequisite_subquery(knowledge_var: str = "k", depth: int = 3) -> str:
        """
        Build pure Cypher prerequisite subquery using semantic relationships.

        Args:
            knowledge_var: Variable name for knowledge node in query
            depth: Maximum prerequisite depth

        Returns:
            Cypher subquery fragment for prerequisite discovery
        """
        prerequisite_types = [
            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            SemanticRelationshipType.REQUIRES_PRACTICAL_APPLICATION,
            SemanticRelationshipType.REQUIRES_CONCEPTUAL_FOUNDATION,
            SemanticRelationshipType.BUILDS_ON_FOUNDATION,
        ]
        rel_pattern = "|".join([st.to_neo4j_name() for st in prerequisite_types])
        return f"""
        OPTIONAL MATCH ({knowledge_var})<-[:{rel_pattern}*1..{depth}]-(prereq:Entity)
        WITH {knowledge_var}, collect(DISTINCT prereq) as prereqs
        """

    async def validate_path_prerequisites(self, path_uid: str) -> Result[list[dict[str, Any]]]:
        """Run prerequisite validation query for a learning path."""
        query = f"""
        MATCH (path:Entity {{uid: $path_uid}})
        MATCH (path)-[r:HAS_STEP]->(step:Entity {{entity_type: 'path_step'}})
        MATCH (k:Entity {{uid: step.knowledge_uid}})

        // Get all prerequisites using pure Cypher
        {self._build_prerequisite_subquery("k", 3)}

        // Check if prerequisites are in earlier steps
        WITH path, step, k, r.sequence as step_seq, prereqs
        MATCH (path)-[r2:HAS_STEP]->(earlier:Entity {{entity_type: 'path_step'}})
        WHERE r2.sequence < step_seq

        WITH step, k, step_seq, prereqs,
             collect(earlier.knowledge_uid) as earlier_knowledge

        // Find unmet prerequisites
        WITH step, k, step_seq,
             [p IN prereqs WHERE NOT p.uid IN earlier_knowledge | p.uid] as unmet_prereqs

        RETURN {{
            step_uid: step.uid,
            knowledge_uid: k.uid,
            sequence: step_seq,
            unmet_prerequisites: unmet_prereqs,
            has_issues: size(unmet_prereqs) > 0
        }} as validation
        ORDER BY step_seq
        """
        return await self.execute_query(query, {"path_uid": path_uid})

    async def identify_path_blockers(
        self, path_uid: str, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:
        """Run blocker identification query for a user on a learning path."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        MATCH (path:Entity {{uid: $path_uid}})

        // Get user's mastered knowledge
        OPTIONAL MATCH (u)-[m:MASTERED]->(mastered:Entity)
        WITH u, path, collect(mastered.uid) as mastered_uids

        // Get path steps
        MATCH (path)-[r:HAS_STEP]->(step:Entity {{entity_type: 'path_step'}})
        MATCH (k:Entity {{uid: step.knowledge_uid}})

        // Check prerequisites
        {self._build_prerequisite_subquery("k", 2)}

        WITH step, k, r.sequence as seq, mastered_uids, prereqs,
             [p IN prereqs WHERE NOT p.uid IN mastered_uids] as blocking_prereqs

        // Identify blockers
        WITH step, k, seq,
             blocking_prereqs,
             size(blocking_prereqs) > 0 as is_blocked

        ORDER BY seq

        // Find first blocker
        WITH collect({{
            step: step,
            knowledge: k,
            sequence: seq,
            is_blocked: is_blocked,
            blocking_prerequisites: blocking_prereqs
        }}) as all_steps

        WITH all_steps,
             [s IN all_steps WHERE s.is_blocked][0] as first_blocker

        RETURN {{
            total_steps: size(all_steps),
            blocked_steps: [s IN all_steps WHERE s.is_blocked],
            first_blocker: first_blocker,
            can_progress: first_blocker IS NULL
        }} as blocker_analysis
        """
        return await self.execute_query(query, {"path_uid": path_uid, "user_uid": user_uid})

    async def get_optimal_path_recommendations(
        self, user_uid: UserUID, goal_domain: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        """Find optimal learning path recommendations for a user."""
        domain_filter = "AND path.domain = $domain" if goal_domain else ""

        query = f"""
        MATCH (u:User {{uid: $user_uid}})

        // Get user's mastered knowledge
        OPTIONAL MATCH (u)-[m:MASTERED]->(mastered:Entity)
        WITH u, collect(mastered.uid) as mastered_uids

        // Get available paths — completion lives on ENROLLED_IN r.status
        // (written by UserBackend.complete_learning_path); a :COMPLETED edge
        // never had a writer.
        MATCH (path:Entity {{entity_type: 'learning_path'}})
        WHERE NOT (u)-[:ENROLLED_IN {{status: 'completed'}}]->(path) {domain_filter}

        // Calculate path readiness
        MATCH (path)-[:HAS_STEP]->(step:Entity {{entity_type: 'path_step'}})
        MATCH (k:Entity {{uid: step.knowledge_uid}})

        // Get prerequisites
        {self._build_prerequisite_subquery("k", 2)}

        WITH path, mastered_uids,
             size([p IN prereqs WHERE p.uid IN mastered_uids]) as met,
             size(prereqs) as total

        WITH path,
             CASE WHEN total = 0 THEN 1.0
                  ELSE toFloat(met) / total
             END as readiness_score

        // Get path with best readiness
        WITH path, readiness_score
        ORDER BY readiness_score DESC, path.estimated_hours ASC
        LIMIT 5

        RETURN {{
            recommended_paths: collect({{
                path: path,
                readiness_score: readiness_score,
                estimated_hours: path.estimated_hours,
                reason: CASE
                    WHEN readiness_score > 0.8 THEN "High readiness - prerequisites mostly met"
                    WHEN readiness_score > 0.5 THEN "Moderate readiness - some prerequisites needed"
                    ELSE "Low readiness - build foundations first"
                END
            }})
        }} as recommendations
        """
        params: dict[str, Any] = {"user_uid": user_uid}
        if goal_domain:
            params["domain"] = goal_domain
        return await self.execute_query(query, params)

    async def find_learning_sequence(
        self, start_uid: str, goal_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Find optimal learning path from start to goal using graph traversal."""
        query = """
        MATCH path = shortestPath(
            (start:Entity {uid: $start_uid})-[:ENABLES_KNOWLEDGE|REQUIRES_KNOWLEDGE*]-(goal:Entity {uid: $goal_uid})
        )
        WITH path, relationships(path) as rels

        // Sort by typical_learning_order if available
        UNWIND rels as r
        WITH path, r
        ORDER BY coalesce(r.typical_learning_order, 999)

        RETURN [node IN nodes(path) | node.uid] as sequence
        """
        return await self.execute_query(query, {"start_uid": start_uid, "goal_uid": goal_uid})

    async def get_next_adaptive_step(
        self, current_step_uid: str, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:
        """Get next path step based on adaptive intelligence."""
        query = """
        MATCH (current:Entity {uid: $current_uid})-[r:ENABLES_KNOWLEDGE]->(next:Entity)

        // Get user progress for prerequisites
        OPTIONAL MATCH (next)-[:REQUIRES_KNOWLEDGE]->(prereq)
        OPTIONAL MATCH (prereq)<-[:HAS_PROGRESS]-(up:UserProgress {user_uid: $user_uid})

        WITH next, r,
             count(prereq) as total_prereqs,
             count(CASE WHEN up.mastery_level >= 0.7 THEN 1 END) as completed_prereqs,
             avg(coalesce(r.confidence, 1.0)) as avg_confidence,
             avg(coalesce(r.strength, 1.0)) as avg_strength,
             avg(coalesce(r.difficulty_gap, 0.3)) as avg_difficulty

        // Calculate prerequisite readiness
        WITH next,
             CASE
                 WHEN total_prereqs = 0 THEN 1.0
                 ELSE toFloat(completed_prereqs) / total_prereqs
             END as prerequisite_readiness,
             avg_confidence,
             avg_strength,
             avg_difficulty

        // Filter to ready steps (80% of prerequisites complete)
        WHERE prerequisite_readiness >= 0.8

        // Score by confidence (60%) and strength (40%)
        WITH next,
             (avg_confidence * 0.6 + avg_strength * 0.4) as readiness_score,
             avg_difficulty,
             prerequisite_readiness
        ORDER BY readiness_score DESC, avg_difficulty ASC

        RETURN next.uid as next_uid,
               readiness_score,
               avg_difficulty,
               prerequisite_readiness
        LIMIT 1
        """
        return await self.execute_query(
            query, {"current_uid": current_step_uid, "user_uid": user_uid}
        )

    async def get_recommended_path_steps(
        self, user_uid: UserUID, max_difficulty: float = 0.5, limit: int = 5
    ) -> Result[list[dict[str, Any]]]:
        """Get recommended path steps for a user based on their progress."""
        query = """
        // Find knowledge units user has mastered
        MATCH (mastered:Entity)<-[:HAS_PROGRESS]-(up:UserProgress {user_uid: $user_uid})
        WHERE up.mastery_level >= 0.7

        // Find next steps enabled by mastered knowledge
        MATCH (mastered)-[r:ENABLES_KNOWLEDGE]->(next:Entity)

        // Check if user hasn't started this yet
        WHERE NOT exists((next)<-[:HAS_PROGRESS]-(:UserProgress {user_uid: $user_uid}))

        // Check prerequisite readiness
        OPTIONAL MATCH (next)-[:REQUIRES_KNOWLEDGE]->(prereq)
        OPTIONAL MATCH (prereq)<-[:HAS_PROGRESS]-(prereq_progress:UserProgress {user_uid: $user_uid})

        WITH next, r,
             count(prereq) as total_prereqs,
             count(CASE WHEN prereq_progress.mastery_level >= 0.7 THEN 1 END) as completed_prereqs

        // Calculate readiness
        WITH next, r,
             CASE
                 WHEN total_prereqs = 0 THEN 1.0
                 ELSE toFloat(completed_prereqs) / total_prereqs
             END as prerequisite_readiness

        // Filter by readiness and difficulty
        WHERE prerequisite_readiness >= 0.8
          AND coalesce(r.difficulty_gap, 0.3) <= $max_difficulty

        // Return recommendations with metadata
        RETURN DISTINCT next.uid as uid,
               next.title as title,
               next.domain as domain,
               coalesce(r.confidence, 1.0) as confidence,
               coalesce(r.strength, 1.0) as strength,
               coalesce(r.difficulty_gap, 0.3) as difficulty_gap,
               coalesce(r.semantic_distance, 0.5) as semantic_distance,
               prerequisite_readiness

        ORDER BY (confidence * 0.4 + strength * 0.3 + prerequisite_readiness * 0.3) DESC,
                 difficulty_gap ASC

        LIMIT $limit
        """
        return await self.execute_query(
            query,
            {"user_uid": user_uid, "max_difficulty": max_difficulty, "limit": limit},
        )
