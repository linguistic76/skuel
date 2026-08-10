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

from adapters.persistence.neo4j.query.cypher import build_publication_clause
from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.type_hints import UserUID
from core.ports.query_types import LpKnowledgeScopeSummary
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins
    import logging

# Safety bound on how deep a REQUIRES_KNOWLEDGE prerequisite chain is walked when
# measuring a path's depth. Prerequisite graphs are shallow DAGs (chains of 1-3
# are typical); this caps pathological cases and bounds the traversal. Reported
# ``max_prerequisite_depth`` is therefore honest up to this many hops.
_PREREQUISITE_DEPTH_CAP = 10


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

    # PS→KU edge union: the same vocabulary LifePathBackend's alignment queries
    # traverse. USES_KU is THE composition edge; CONTAINS_KNOWLEDGE and
    # TRAINS_KU are the sanctioned siblings.
    _STEP_KNOWLEDGE_EDGES = "USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU"

    @staticmethod
    def _build_prerequisite_subquery(
        knowledge_var: str = "k", depth: int = 3, carry: str = ""
    ) -> str:
        """
        Build pure Cypher prerequisite subquery using semantic relationships.

        Traverses OUTGOING edges — the sanctioned direction is
        ``(dependent)-[:REQUIRES_KNOWLEDGE]->(prerequisite)`` (see
        GRAPH_CONTRACT.yaml and UserProgressBackend.get_prerequisite_map).

        Args:
            knowledge_var: Variable name for knowledge node in query
            depth: Maximum prerequisite depth
            carry: Comma-separated variables to keep in scope through the
                aggregating WITH (the collect() would otherwise drop them)

        Returns:
            Cypher subquery fragment for prerequisite discovery
        """
        prerequisite_types = [
            SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            SemanticRelationshipType.REQUIRES_PRACTICAL_APPLICATION,
            SemanticRelationshipType.REQUIRES_CONCEPTUAL_FOUNDATION,
            SemanticRelationshipType.BUILDS_ON_FOUNDATION,
        ]
        # All four collapse onto REQUIRES_KNOWLEDGE (roadmap Phase 1), so dedupe.
        # NO semantic_type filter here on purpose: this validates the ACTUAL
        # prerequisite structure of the path, which is the ingestion-written
        # REQUIRES_KNOWLEDGE edge (no semantic_type property). Filtering by the
        # four semantic predicates would exclude those real edges and re-empty the
        # query — the opposite of the intent. This is prerequisite structure, not
        # a semantic-type-scoped traversal.
        rel_pattern = "|".join(sorted({str(st.to_neo4j_name()) for st in prerequisite_types}))
        carry_clause = f"{carry}, " if carry else ""
        return f"""
        OPTIONAL MATCH ({knowledge_var})-[:{rel_pattern}*1..{depth}]->(prereq:Entity)
        WITH {carry_clause}{knowledge_var}, collect(DISTINCT prereq) as prereqs
        """

    # ========================================================================
    # KNOWLEDGE AGGREGATION (LpOperations "KNOWLEDGE AGGREGATION" contract)
    # ========================================================================

    async def get_all_knowledge_uids(self, path_uid: str) -> Result[set[str]]:
        """All distinct KU UIDs a path teaches, across every step.

        Traverses the canonical PS→KU union (``USES_KU|CONTAINS_KNOWLEDGE|
        TRAINS_KU``); dedupes KUs shared by several steps. An unknown or
        stepless path yields an empty set (not an error).
        """
        query = f"""
        MATCH (path:Entity {{uid: $path_uid}})-[:HAS_STEP]->(step:Entity {{entity_type: 'path_step'}})
        MATCH (step)-[:{self._STEP_KNOWLEDGE_EDGES}]->(ku:Entity {{entity_type: 'ku'}})
        RETURN collect(DISTINCT ku.uid) AS uids
        """
        result = await self.execute_query(query, {"path_uid": path_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        uids = records[0]["uids"] if records else []
        return Result.ok({uid for uid in uids if uid})

    async def get_knowledge_scope_summary(self, path_uid: str) -> Result[LpKnowledgeScopeSummary]:
        """Structural facts about a path's KU coverage — one row.

        Measures only what the graph knows: step count, distinct-KU count,
        breadth density (mean distinct KUs per step), and the longest
        REQUIRES_KNOWLEDGE prerequisite chain among those KUs. A multi-KU step
        counts once (KUs hang off steps as edges — never count the (step, ku)
        fan-out as steps). The interpreted ``complexity_score`` is derived from
        these facts at the service layer, not here. An unknown or stepless path
        returns all-zeros.
        """
        query = f"""
        MATCH (path:Entity {{uid: $path_uid}})
        OPTIONAL MATCH (path)-[:HAS_STEP]->(step:Entity {{entity_type: 'path_step'}})
        OPTIONAL MATCH (step)-[:{self._STEP_KNOWLEDGE_EDGES}]->(ku:Entity {{entity_type: 'ku'}})
        WITH path,
             count(DISTINCT step) AS total_steps,
             count(DISTINCT ku) AS total_unique_kus,
             count(DISTINCT CASE WHEN ku IS NOT NULL THEN [step.uid, ku.uid] END) AS step_ku_pairs,
             collect(DISTINCT ku) AS kus

        // Longest REQUIRES_KNOWLEDGE prerequisite chain among the path's KUs.
        // The [null] pad keeps the row alive when the path has no KUs (UNWIND of
        // [] yields no rows); a KU with no prerequisites contributes depth 0.
        UNWIND (kus + [null]) AS k
        OPTIONAL MATCH prereq_path = (k)-[:REQUIRES_KNOWLEDGE*1..{_PREREQUISITE_DEPTH_CAP}]->(:Entity)
        WITH total_steps, total_unique_kus, step_ku_pairs,
             max(coalesce(length(prereq_path), 0)) AS max_prerequisite_depth

        RETURN total_steps,
               total_unique_kus,
               CASE WHEN total_steps = 0 THEN 0.0
                    ELSE toFloat(step_ku_pairs) / total_steps END AS kus_per_step,
               max_prerequisite_depth
        """
        result = await self.execute_query(query, {"path_uid": path_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(
                LpKnowledgeScopeSummary(
                    total_steps=0,
                    total_unique_kus=0,
                    kus_per_step=0.0,
                    max_prerequisite_depth=0,
                )
            )
        record = records[0]
        return Result.ok(
            LpKnowledgeScopeSummary(
                total_steps=int(record["total_steps"]),
                total_unique_kus=int(record["total_unique_kus"]),
                kus_per_step=float(record["kus_per_step"]),
                max_prerequisite_depth=int(record["max_prerequisite_depth"]),
            )
        )

    async def validate_path_prerequisites(self, path_uid: str) -> Result[list[dict[str, Any]]]:
        """Run prerequisite validation query for a learning path.

        One row per STEP: a step's KUs are graph edges (USES_KU et al.), not
        a ``knowledge_uid`` node property, and a multi-KU step must not be
        counted once per KU — the service derives ``total_steps`` from row
        counts. The first step is validated too — its ``earlier_knowledge``
        is simply empty, so any prerequisite it carries is unmet by
        construction.
        """
        query = f"""
        MATCH (path:Entity {{uid: $path_uid}})
        MATCH (path)-[r:HAS_STEP]->(step:Entity {{entity_type: 'path_step'}})
        MATCH (step)-[:{self._STEP_KNOWLEDGE_EDGES}]->(k:Entity {{entity_type: 'ku'}})

        // Get all prerequisites using pure Cypher
        {self._build_prerequisite_subquery("k", 3, carry="path, step, r")}

        // Collapse the per-KU fan-out to ONE row per step. The [null] pad
        // keeps zero-prerequisite KUs alive through UNWIND; collect() drops it.
        UNWIND (prereqs + [null]) as p
        WITH path, step, r.sequence as step_seq,
             collect(DISTINCT k.uid) as knowledge_uids,
             collect(DISTINCT p) as step_prereqs

        // Check if prerequisites are covered by earlier steps' knowledge.
        // OPTIONAL: the first step has no earlier steps and must still be
        // returned (a bare MATCH would drop it from the results).
        OPTIONAL MATCH (path)-[r2:HAS_STEP]->(earlier:Entity {{entity_type: 'path_step'}})
            -[:{self._STEP_KNOWLEDGE_EDGES}]->(ek:Entity {{entity_type: 'ku'}})
        WHERE r2.sequence < step_seq

        WITH step, step_seq, knowledge_uids, step_prereqs,
             collect(DISTINCT ek.uid) as earlier_knowledge

        // Find unmet prerequisites
        WITH step, step_seq, knowledge_uids,
             [p IN step_prereqs WHERE NOT p.uid IN earlier_knowledge | p.uid] as unmet_prereqs

        RETURN {{
            step_uid: step.uid,
            knowledge_uids: knowledge_uids,
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
        """Run blocker identification query for a user on a learning path.

        One entry per STEP — a step's KUs are graph edges, not a node
        property, and the per-KU fan-out is collapsed so a multi-KU step is
        one entry (``total_steps``/``blocked_steps`` count steps, not KUs).
        ``blocking_prerequisites`` holds UIDs (they feed user-facing
        "Focus on mastering: …" strings in the service).
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        MATCH (path:Entity {{uid: $path_uid}})

        // Get user's mastered knowledge
        OPTIONAL MATCH (u)-[m:MASTERED]->(mastered:Entity)
        WITH u, path, collect(mastered.uid) as mastered_uids

        // Get path steps and their knowledge units (graph edges, not properties)
        MATCH (path)-[r:HAS_STEP]->(step:Entity {{entity_type: 'path_step'}})
        MATCH (step)-[:{self._STEP_KNOWLEDGE_EDGES}]->(k:Entity {{entity_type: 'ku'}})

        // Check prerequisites
        {self._build_prerequisite_subquery("k", 2, carry="step, r, mastered_uids")}

        // Collapse the per-KU fan-out to ONE row per step (same pattern as
        // validate_path_prerequisites)
        UNWIND (prereqs + [null]) as p
        WITH step, r.sequence as seq, mastered_uids,
             collect(DISTINCT k.uid) as knowledge_uids,
             collect(DISTINCT p) as step_prereqs

        WITH step, seq, knowledge_uids,
             [p IN step_prereqs WHERE NOT p.uid IN mastered_uids | p.uid] as blocking_prereqs

        // Identify blockers
        WITH step, seq, knowledge_uids,
             blocking_prereqs,
             size(blocking_prereqs) > 0 as is_blocked

        ORDER BY seq

        // Find first blocker
        WITH collect({{
            step_uid: step.uid,
            step_title: step.title,
            knowledge_uids: knowledge_uids,
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
        # Discovery — a RECOMMENDATION is the purest form of it: this enumerates
        # every path the user has not completed and ranks them. Draft paths
        # withheld; NULL-tolerant so the pre-publication_state corpus still
        # recommends (#1006).
        #
        # `step` below is deliberately NOT gated, unlike the bridging step in the
        # KU→path surfaces (Codex #1008). The distinction is what reaches the
        # caller: there, the bridge carries the CLAIM "this path teaches that KU"
        # and a draft step makes the claim false. Here the steps are internal to
        # a readiness score — only `path` is returned, and a path's own steps
        # ride along with it (the containment carve-out that lets
        # list_all_paths_with_steps gate `p` but not the steps it collects).
        # A draft step can skew the score; it cannot disclose unfinished content.
        published, published_params = build_publication_clause("path")

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
          AND {published}

        // Calculate path readiness over the path's knowledge units
        // (graph edges from each step, not a node property)
        MATCH (path)-[:HAS_STEP]->(step:Entity {{entity_type: 'path_step'}})
        MATCH (step)-[:{self._STEP_KNOWLEDGE_EDGES}]->(k:Entity {{entity_type: 'ku'}})

        // Get prerequisites
        {self._build_prerequisite_subquery("k", 2, carry="path, mastered_uids")}

        // Aggregate prerequisites across ALL of the path's knowledge units —
        // one readiness row per path, not one per (step, ku). The [null] pad
        // keeps zero-prereq rows alive through UNWIND; collect() drops it.
        UNWIND (prereqs + [null]) as p
        WITH path, mastered_uids, collect(DISTINCT p) as all_prereqs

        WITH path,
             size([p IN all_prereqs WHERE p.uid IN mastered_uids]) as met,
             size(all_prereqs) as total

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
                path: {{uid: path.uid, name: path.title, title: path.title}},
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
        params: dict[str, Any] = {"user_uid": user_uid, **published_params}
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
        """Get next path step based on adaptive intelligence.

        A prerequisite counts as complete when the user has MASTERED it. See
        UserProgressBackend.calculate_knowledge_coverage for why this is edge
        existence rather than ADR-002's never-built `mastery_level >= 0.7`.
        """
        query = """
        MATCH (current:Entity {uid: $current_uid})-[r:ENABLES_KNOWLEDGE]->(next:Entity)

        // Get user progress for prerequisites
        OPTIONAL MATCH (next)-[:REQUIRES_KNOWLEDGE]->(prereq)
        OPTIONAL MATCH (:User {uid: $user_uid})-[mastery:MASTERED]->(prereq)

        WITH next, r,
             count(prereq) as total_prereqs,
             count(mastery) as completed_prereqs,
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
        # Discovery: forward enablement from mastered knowledge to steps the
        # user has NOT started — a recommendation, so draft steps are withheld.
        # Same ruling as the ZPD proximal zone. NULL-tolerant (#1006).
        published, published_params = build_publication_clause("next")
        query = f"""
        // Find knowledge units user has mastered
        MATCH (:User {{uid: $user_uid}})-[:MASTERED]->(mastered:Entity)

        // Find next steps enabled by mastered knowledge
        MATCH (mastered)-[r:ENABLES_KNOWLEDGE]->(next:Entity)

        // Check if user hasn't started this yet. "Started" spans both live
        // states: MASTERED is the terminal state of VIEWED → IN_PROGRESS →
        // MASTERED and its writers DELETE the IN_PROGRESS edge, so the two are
        // mutually exclusive — neither arm alone covers "already engaged".
        WHERE NOT exists((:User {{uid: $user_uid}})-[:IN_PROGRESS|MASTERED]->(next))
          AND {published}

        // Check prerequisite readiness
        OPTIONAL MATCH (next)-[:REQUIRES_KNOWLEDGE]->(prereq)
        OPTIONAL MATCH (:User {{uid: $user_uid}})-[prereq_mastery:MASTERED]->(prereq)

        WITH next, r,
             count(prereq) as total_prereqs,
             count(prereq_mastery) as completed_prereqs

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
            {
                "user_uid": user_uid,
                "max_difficulty": max_difficulty,
                "limit": limit,
                **published_params,
            },
        )
