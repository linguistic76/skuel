"""Curriculum core backends: Ku, PathStep, LearningPath.

The Exercise/RevisedExercise/EntryReport trio lives in ``exercise_backends.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from adapters.persistence.neo4j._adaptive_mixin import _AdaptiveMixin
from adapters.persistence.neo4j._knowledge_context_mixin import _KnowledgeContextMixin
from adapters.persistence.neo4j._learning_state_mixin import _LearningStateMixin
from adapters.persistence.neo4j._lp_intelligence_mixin import _LpIntelligenceMixin
from adapters.persistence.neo4j._lp_progress_mixin import _LpProgressMixin
from adapters.persistence.neo4j._lp_step_mixin import _LpStepMixin
from adapters.persistence.neo4j._organizes_mixin import _OrganizesMixin
from adapters.persistence.neo4j._semantic_mixin import _SemanticMixin
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.ku.ku import Ku
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import (
    PsDeleteStepRow,
    PsKnowledgeSummaryResult,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.report_schedule import ReportSchedule  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401


class KuBackend(UniversalNeo4jBackend[Ku]):
    """Domain backend for atomic Knowledge Unit entities.

    Lightweight reference nodes with reverse-traversal methods:
    - get_path_steps_using(ku_uid) — PathSteps that USES_KU this Ku
    """

    async def get_path_steps_using(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all PathSteps that use this atomic Ku via USES_KU."""
        query = """
        MATCH (ps:Entity)-[:USES_KU]->(ku:Entity {uid: $ku_uid})
        RETURN ps.uid AS uid, ps.title AS title,
               ps.description AS description
        ORDER BY ps.title
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_cited_resources(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get the curated Resources this Ku cites via CITES_RESOURCE.

        Focused traversal on the Ku backend (the entity-agnostic
        ``_KnowledgeContextMixin.get_cited_resources`` is PS-oriented and not
        mixed into this lightweight backend). Rows carry a ``resource`` map plus
        the edge's ``locator`` free-string anchor (null for whole-work
        citations); the service flattens them for the shared resource chip.
        """
        query = """
        MATCH (source:Entity {uid: $ku_uid})-[cite:CITES_RESOURCE]->(r:Resource)
        RETURN r {.*} AS resource, cite.locator AS locator
        ORDER BY r.title
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def get_usage_summary(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Count path steps using (USES_KU), training (TRAINS_KU), and organized children."""
        query = """
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        OPTIONAL MATCH (uses:Entity)-[:USES_KU]->(ku)
        OPTIONAL MATCH (trains:Entity)-[:TRAINS_KU]->(ku)
        OPTIONAL MATCH (ku)-[:ORGANIZES]->(child:Entity)
        RETURN count(DISTINCT uses) as path_steps_using,
               count(DISTINCT trains) as path_steps_training,
               count(DISTINCT child) as organized_children
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def is_trained(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Check if any PathStep trains this Ku via TRAINS_KU."""
        query = """
        MATCH (ps:Entity)-[:TRAINS_KU]->(ku:Entity:Ku {uid: $ku_uid})
        RETURN count(ps) > 0 as trained
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def is_organized(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Check if this Ku has ORGANIZES children (acts as MOC)."""
        query = """
        MATCH (ku:Entity:Ku {uid: $ku_uid})-[:ORGANIZES]->(child:Entity)
        RETURN count(child) > 0 as organized
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_organization_depth(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get depth of the ORGANIZES tree below this Ku."""
        query = """
        MATCH path = (ku:Entity:Ku {uid: $ku_uid})-[:ORGANIZES*]->(descendant:Entity)
        RETURN max(length(path)) as max_depth
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def search_by_alias(self, alias: str) -> Result[list[Neo4jProperties]]:
        """Search Kus by alias (case-insensitive substring)."""
        query = """
        MATCH (ku:Entity:Ku)
        WHERE any(a IN ku.aliases WHERE toLower(a) CONTAINS toLower($alias))
        RETURN ku
        ORDER BY ku.title ASC
        """
        return await self.execute_query(query, {"alias": alias})

    async def nous_subtopic_pairs(self) -> Result[list[Neo4jProperties]]:
        """Distinct co-occurring (nous, nous_subtopic) pairs on this Ku's own label.

        The Ku contribution to the dependent nous→sub-topic /search dropdown.
        Scoped to `:Ku` only — cross-domain aggregation (folding in the PathStep
        contribution) belongs in the service layer, NOT the persistence layer
        (`SearchRouter.nous_subtopic_map` merges this with `PsBackend`'s pairs).
        Graph-derived so it can't drift from the vault vocabulary (content
        boundary — the taxonomy lives in the vault, never in the repo).

        Pairing is CO-OCCURRENCE: a (topic, sub-topic) pair exists once ≥1
        entity carries both, so the dropdown follows wherever the content
        actually connects them — every offered pair has at least one matching
        entity. The two frontmatter lists are fully independent (any lengths,
        any combination); there is deliberately NO alignment/equal-length
        authoring contract (Mike's ruling, 2026-07-16: the design goes where
        whatever there is to share leads — no false restrictions). Returns rows
        with ``nous`` + ``subtopic`` keys.
        """
        query = """
        MATCH (n:Ku)
        WHERE n.nous IS NOT NULL AND n.nous_subtopic IS NOT NULL
        UNWIND n.nous AS nous
        UNWIND n.nous_subtopic AS subtopic
        RETURN DISTINCT nous, subtopic
        ORDER BY nous, subtopic
        """
        return await self.execute_query(query, {})

    # ========================================================================
    # SUBSTANCE METRICS
    # ========================================================================

    async def batch_increment_substance(
        self,
        ku_uids: list[str],
        metric: str,
        timestamp_field: str,
        timestamp_str: str,
    ) -> Result[int]:
        """Atomically increment a substance metric for multiple KUs and connected PathSteps."""
        query = f"""
        UNWIND $ku_uids AS ku_uid
        MATCH (ku:Entity {{uid: ku_uid}})
        SET ku.{metric} = COALESCE(ku.{metric}, 0) + 1,
            ku.{timestamp_field} = datetime($timestamp),
            ku._substance_cache_timestamp = NULL
        WITH ku
        OPTIONAL MATCH (ps:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU|TRAINS_KU]->(ku)
        WITH ps WHERE ps IS NOT NULL
        SET ps.{metric} = COALESCE(ps.{metric}, 0) + 1,
            ps.{timestamp_field} = datetime($timestamp),
            ps._substance_cache_timestamp = NULL
        RETURN count(ps) as updated_count
        """
        result = await self.execute_query(query, {"ku_uids": ku_uids, "timestamp": timestamp_str})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok(records[0]["updated_count"] if records else 0)

    async def increment_substance(
        self,
        ku_uid: str,
        metric: str,
        timestamp_field: str,
        timestamp_str: str,
    ) -> Result[int]:
        """Atomically increment a substance metric for a single KU and connected PathSteps."""
        query = f"""
        MATCH (ku:Entity {{uid: $ku_uid}})
        SET ku.{metric} = COALESCE(ku.{metric}, 0) + 1,
            ku.{timestamp_field} = datetime($timestamp),
            ku._substance_cache_timestamp = NULL
        WITH ku
        OPTIONAL MATCH (ps:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU|TRAINS_KU]->(ku)
        WITH ku, ps WHERE ps IS NOT NULL
        SET ps.{metric} = COALESCE(ps.{metric}, 0) + 1,
            ps.{timestamp_field} = datetime($timestamp),
            ps._substance_cache_timestamp = NULL
        RETURN ku.{metric} as new_count
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid, "timestamp": timestamp_str})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok(records[0]["new_count"] if records else 0)

    # ========================================================================
    # KU RELATIONSHIP QUERIES (migrated from ku_relationships.py helpers)
    # ========================================================================

    async def get_related_knowledge_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get related knowledge units (RELATED_TO relationship)."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})-[:RELATED_TO]-(related:Entity)
        RETURN related.uid as uid
        LIMIT 50
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_broader_concept_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get broader concepts (HAS_BROADER relationship)."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})-[:HAS_BROADER]->(broader:Entity)
        RETURN broader.uid as uid
        LIMIT 20
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_narrower_concept_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get narrower concepts (HAS_NARROWER relationship)."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})-[:HAS_NARROWER]->(narrower:Entity)
        RETURN narrower.uid as uid
        LIMIT 50
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_learning_path_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get learning paths containing this KU.

        Both arms of the old ``CONTAINS_KNOWLEDGE|INCLUDES_KNOWLEDGE`` alternation
        were wrong at this endpoint. ``INCLUDES_KNOWLEDGE`` is not a
        ``RelationshipName`` member at all, and ``CONTAINS_KNOWLEDGE`` is a
        PathStep→Ku edge, not a LearningPath→Ku one — so the query named a
        relationship pair the graph cannot hold (findings §8). A path reaches a Ku
        through its PathSteps, or directly via its ``required_knowledge``
        prerequisites.
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})
        MATCH (lp:LearningPath)
        WHERE (lp)-[:REQUIRES_KNOWLEDGE]->(ku)
           OR (lp)-[:HAS_STEP]->(:Entity)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku)
        RETURN lp.uid as uid
        LIMIT 50
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_applying_task_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get tasks applying this knowledge."""
        query = """
        MATCH (task:Task)-[:APPLIES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN task.uid as uid
        LIMIT 100
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_practicing_event_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get events applying (practicing) this knowledge via APPLIES_KNOWLEDGE."""
        query = """
        MATCH (event:Event)-[:APPLIES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN event.uid as uid
        LIMIT 100
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_reinforcing_habit_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get habits reinforcing this knowledge."""
        query = """
        MATCH (habit:Habit)-[:APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        RETURN habit.uid as uid
        LIMIT 100
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    # ========================================================================
    # PREREQUISITE & DEPENDENCY QUERIES (migrated from ContextRetriever)
    # ========================================================================

    async def get_unmastered_prerequisites(
        self, ku_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get unmastered prerequisites for a knowledge unit (depth 1..3).

        Traverses REQUIRES_KNOWLEDGE chains up to 3 hops, filtering out
        prerequisites the user has already MASTERED.

        Returns:
            Single record with 'prerequisites' key containing list of
            {uid, title} dicts.
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})
        OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE*1..3]->(prereq:Entity)
        WHERE NOT EXISTS {
            MATCH (u:User {uid: $user_uid})-[:MASTERED]->(prereq)
        }
        RETURN collect(DISTINCT {uid: prereq.uid, title: prereq.title}) AS prerequisites
        """
        return await self.execute_query(query, {"ku_uid": ku_uid, "user_uid": user_uid})

    async def count_dependents(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Count entities that depend on this knowledge unit via REQUIRES_KNOWLEDGE.

        Returns:
            Single record with 'unlocks_count' key.
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})<-[:REQUIRES_KNOWLEDGE]-(dependent:Entity)
        RETURN count(DISTINCT dependent) AS unlocks_count
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    # ========================================================================
    # LEARNING STATE (Ku-native — two-tier: Studying + Understood)
    # ========================================================================

    async def mark_in_progress(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Mark a Ku as actively being studied (IN_PROGRESS relationship)."""
        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        MERGE (user)-[r:IN_PROGRESS]->(ku)
        ON CREATE SET
            r.started_at = datetime(),
            r.last_activity_at = datetime(),
            r.progress_score = 0.0
        ON MATCH SET
            r.last_activity_at = datetime()
        RETURN ku.uid AS uid
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def mark_mastered(
        self,
        user_uid: UserUID,
        ku_uid: str,
        mastery_score: float = 0.7,
        method: str = "self_report",
    ) -> Result[list[Neo4jProperties]]:
        """Mark a Ku as understood/mastered by the user."""
        query = """
        MATCH (user:User {uid: $user_uid})
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        MERGE (user)-[r:MASTERED]->(ku)
        ON CREATE SET
            r.mastered_at = datetime(),
            r.mastery_score = $mastery_score,
            r.confidence = $mastery_score,
            r.method = $method
        ON MATCH SET
            r.mastery_score = CASE
                WHEN $mastery_score > r.mastery_score THEN $mastery_score
                ELSE r.mastery_score
            END,
            r.confidence = CASE
                WHEN $mastery_score > coalesce(r.confidence, 0) THEN $mastery_score
                ELSE r.confidence
            END,
            r.method = $method
        RETURN ku.uid AS uid
        """
        return await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "ku_uid": ku_uid,
                "mastery_score": mastery_score,
                "method": method,
            },
        )

    async def get_ku_learning_state(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get user's learning state for a Ku (IN_PROGRESS, MASTERED, MARKED_AS_READ)."""
        query = """
        MATCH (ku:Entity:Ku {uid: $ku_uid})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u2:User {uid: $user_uid})-[m:MASTERED]->(ku)
        OPTIONAL MATCH (u3:User {uid: $user_uid})-[mr:MARKED_AS_READ]->(ku)
        RETURN
            p IS NOT NULL AS is_studying,
            m IS NOT NULL AS is_understood,
            mr IS NOT NULL AS is_marked_as_read
        """
        return await self.execute_query(query, {"user_uid": user_uid, "ku_uid": ku_uid})

    async def count_studying_kus(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Count Kus the user has marked as studying (IN_PROGRESS or MARKED_AS_READ)."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:IN_PROGRESS|MARKED_AS_READ]->(ku:Entity:Ku)
        RETURN count(ku) AS cnt
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def get_user_learning_states(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all Kus with their learning state for a user."""
        query = """
        MATCH (ku:Entity:Ku)
        WHERE EXISTS { (u:User {uid: $user_uid})-[:IN_PROGRESS|MASTERED|MARKED_AS_READ]->(ku) }
        OPTIONAL MATCH (u:User {uid: $user_uid})-[p:IN_PROGRESS]->(ku)
        OPTIONAL MATCH (u2:User {uid: $user_uid})-[m:MASTERED]->(ku)
        OPTIONAL MATCH (u3:User {uid: $user_uid})-[mr:MARKED_AS_READ]->(ku)
        RETURN ku.uid AS uid, ku.title AS title,
               (p IS NOT NULL OR mr IS NOT NULL) AS is_studying,
               m IS NOT NULL AS is_understood
        ORDER BY ku.title ASC
        """
        return await self.execute_query(query, {"user_uid": user_uid})


class PsBackend(
    _OrganizesMixin,
    _LearningStateMixin,
    _SemanticMixin,
    _KnowledgeContextMixin,
    _AdaptiveMixin,
    UniversalNeo4jBackend[PathStep],
):
    """Domain backend for PathStep entities.

    Extends UniversalNeo4jBackend[PathStep] with:
    - Knowledge relationship CRUD (CONTAINS_KNOWLEDGE / USES_KU edges)
    - KU completion progress tracking
    - ``_OrganizesMixin`` — ORGANIZES relationship management (12 methods)
    - ``_LearningStateMixin`` — user progress tracking: VIEWED, IN_PROGRESS,
      MASTERED, BOOKMARKED, MARKED_AS_READ (13 methods)
    - ``_SemanticMixin`` — semantic relationships + graph analysis (11 methods)
    - ``_KnowledgeContextMixin`` — context, discovery, readiness (13 methods)
    - ``_AdaptiveMixin`` — practice, search, adaptive mastery tracking (10 methods)
    """

    async def nous_subtopic_pairs(self) -> Result[list[Neo4jProperties]]:
        """Distinct co-occurring (nous, nous_subtopic) pairs on this PathStep label.

        The PathStep contribution to the dependent nous→sub-topic /search
        dropdown. Scoped to `:PathStep` only — mirror of `KuBackend.nous_subtopic_pairs`
        (see its docstring for the co-occurrence semantics: the two frontmatter
        lists are fully independent, no alignment/length contract); the
        cross-domain merge lives in `SearchRouter.nous_subtopic_map`, not here.
        Graph-derived (content boundary).
        """
        query = """
        MATCH (n:PathStep)
        WHERE n.nous IS NOT NULL AND n.nous_subtopic IS NOT NULL
        UNWIND n.nous AS nous
        UNWIND n.nous_subtopic AS subtopic
        RETURN DISTINCT nous, subtopic
        ORDER BY nous, subtopic
        """
        return await self.execute_query(query, {})

    # ========================================================================
    # STEP SEQUENCE (for attach_step_to_path)
    # ========================================================================

    async def get_next_step_sequence(self, path_uid: str) -> Result[int]:
        """Get the next available sequence number for a path's steps."""
        query = """
        MATCH (p:Entity {uid: $path_uid})-[r:HAS_STEP]->()
        RETURN coalesce(max(r.sequence), -1) + 1 as next_sequence
        """
        result = await self.execute_query(query, {"path_uid": path_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(0)
        return Result.ok(result.value[0].get("next_sequence", 0))

    # ========================================================================
    # KNOWLEDGE RELATIONSHIPS (CONTAINS_KNOWLEDGE edges — written at ingestion)
    # ========================================================================

    async def get_knowledge_summary(self, ps_uid: str) -> Result[PsKnowledgeSummaryResult]:
        """Aggregate count and UIDs of knowledge in this step."""
        query = """
        MATCH (ps:Entity {uid: $ps_uid})
        OPTIONAL MATCH (ps)-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN count(r) as count, collect(ku.uid) as uids
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok({"count": 0, "uids": []})
        record = records[0]
        return Result.ok(
            {
                "count": record["count"],
                "uids": [uid for uid in record["uids"] if uid],
            }
        )

    # ========================================================================
    # KU COMPLETION PROGRESS TRACKING
    # ========================================================================

    async def get_ku_completion_progress(
        self, ps_uid: str, user_uid: UserUID
    ) -> Result[Neo4jProperties]:
        """Return total and mastered KU counts for PathStep progress calculation.

        Progress = mastered_kus / total_kus (via USES_KU + CONTAINS_KNOWLEDGE).

        Args:
            ps_uid: PathStep UID
            user_uid: User UID

        Returns:
            Result containing dict with total_kus and mastered_kus
        """
        query = """
        MATCH (ps:Entity {uid: $ps_uid})-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity)
        WITH collect(DISTINCT ku) as all_kus, count(DISTINCT ku) as total
        OPTIONAL MATCH (user:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
        WHERE mastered IN all_kus
        RETURN total as total_kus, count(DISTINCT mastered) as mastered_kus
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok({"total_kus": 0, "mastered_kus": 0})
        record = result.value[0]
        return Result.ok(
            {
                "total_kus": record["total_kus"],
                "mastered_kus": record["mastered_kus"],
            }
        )

    # ========================================================================
    # KU → PATHSTEP LOOKUP (for progress tracking)
    # ========================================================================

    async def find_path_steps_for_ku(self, ku_uid: str) -> Result[list[str]]:
        """Find all PathStep UIDs that contain a given KU via USES_KU or CONTAINS_KNOWLEDGE."""
        query = """
        MATCH (ps:Entity:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity {uid: $ku_uid})
        RETURN ps.uid as ps_uid
        """
        result = await self.execute_query(query, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["ps_uid"] for record in (result.value or [])])

    # ========================================================================
    # CORE CRUD QUERIES (migrated from PsCoreService)
    # ========================================================================

    async def create_step_node(
        self,
        params: dict[str, Any],
        has_knowledge: bool = False,
        path_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """Create step node with conditional knowledge and path relationships."""
        query = """
        CREATE (s:Entity {
            uid: $uid,
            entity_type: 'path_step',
            title: $title,
            intent: $intent,
            description: $description,
            learning_path_uid: $learning_path_uid,
            sequence: $sequence,
            mastery_threshold: $mastery_threshold,
            current_mastery: $current_mastery,
            estimated_hours: $estimated_hours,
            step_difficulty: $step_difficulty,
            status: $status,
            completed: $completed,
            domain: $domain
        })
        """
        if has_knowledge:
            query += """
            WITH s
            UNWIND $knowledge_uids AS ku_uid
            MATCH (ku:Entity {uid: ku_uid})
            MERGE (s)-[r:CONTAINS_KNOWLEDGE]->(ku)
            ON CREATE SET r.created_at = datetime()
            """
        if path_uid:
            query += """
            WITH s
            MATCH (p:Entity {uid: $path_uid})
            MERGE (p)-[r:HAS_STEP]->(s)
            ON CREATE SET r.sequence = $sequence
            """
        query += """
        WITH s
        RETURN s
        """
        return await self.execute_query(query, params)

    @staticmethod
    def _step_with_knowledge_to_model(record: dict[str, Any]) -> PathStep:
        """Reconstruct a PathStep from an ``s, knowledge_uids`` record.

        Enum conversion (domain, status, step_difficulty) and type coercion are
        handled by the generic node mapper. Defaults are injected for required
        fields that older nodes may be missing (pre-schema writes).

        GRAPH-NATIVE: knowledge_uids come from a CONTAINS_KNOWLEDGE traversal,
        not node properties, so they are injected into the data dict.
        """
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

        data: dict[str, Any] = dict(record["s"])
        data.setdefault("title", "Path Step")
        data.setdefault("intent", "Complete this path step")
        data.setdefault("mastery_threshold", 0.7)
        data.setdefault("current_mastery", 0.0)
        data.setdefault("estimated_hours", 1.0)
        data.setdefault("domain", "PERSONAL")
        data["knowledge_uids"] = [uid for uid in record["knowledge_uids"] if uid]
        return from_neo4j_node(data, PathStep)

    async def get_step_with_knowledge(self, uid: str) -> Result[PathStep | None]:
        """Get a step (with its CONTAINS_KNOWLEDGE UIDs) as a typed model, or None."""
        query = """
        MATCH (s:Entity {uid: $uid})
        OPTIONAL MATCH (s)-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN s, collect(ku.uid) as knowledge_uids
        """
        result = await self.execute_query(query, {"uid": uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        return Result.ok(self._step_with_knowledge_to_model(records[0]))

    async def update_step_fields(
        self, _uid: str, set_clauses: list[str], params: dict[str, Any]
    ) -> Result[PathStep | None]:
        """Update step fields; return the updated step as a typed model (None if absent)."""
        query = f"""
        MATCH (s:Entity {{uid: $uid}})
        SET {", ".join(set_clauses)}
        WITH s
        OPTIONAL MATCH (s)-[:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN s, collect(ku.uid) as knowledge_uids
        """
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        return Result.ok(self._step_with_knowledge_to_model(records[0]))

    async def delete_step_node(self, uid: str) -> Result[list[PsDeleteStepRow]]:
        """DETACH DELETE a step node and return deletion count."""
        query = """
        MATCH (s:Entity {uid: $uid})
        DETACH DELETE s
        RETURN count(s) as deleted_count
        """
        return cast(
            "Result[list[PsDeleteStepRow]]",
            await self.execute_query(query, {"uid": uid}),
        )

    async def list_steps_raw(
        self,
        path_uid: str | None,
        limit: int,
        offset: int,
        order_field: str,
        order_direction: str,
        user_uid: UserUID | None = None,
    ) -> Result[list[PathStep]]:
        """List steps (with knowledge UIDs) as typed models, with pagination and filters."""
        where_clause = "WHERE s.user_uid = $user_uid " if user_uid else ""

        if path_uid:
            query = f"""
            MATCH (p:Entity {{uid: $path_uid}})-[:HAS_STEP]->(s:Entity {{entity_type: 'path_step'}})
            {where_clause}
            OPTIONAL MATCH (s)-[:CONTAINS_KNOWLEDGE]->(ku:Entity)
            WITH s, collect(ku.uid) as knowledge_uids
            RETURN s, knowledge_uids
            ORDER BY {order_field} {order_direction}
            SKIP $offset
            LIMIT $limit
            """
        else:
            query = f"""
            MATCH (s:Entity {{entity_type: 'path_step'}})
            {where_clause}
            OPTIONAL MATCH (s)-[:CONTAINS_KNOWLEDGE]->(ku:Entity)
            WITH s, collect(ku.uid) as knowledge_uids
            RETURN s, knowledge_uids
            ORDER BY {order_field} {order_direction}
            SKIP $offset
            LIMIT $limit
            """

        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if path_uid:
            params["path_uid"] = path_uid
        if user_uid:
            params["user_uid"] = user_uid

        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [self._step_with_knowledge_to_model(record) for record in (result.value or [])]
        )

    # ========================================================================
    # SEARCH QUERIES (migrated from PsSearchService)
    # ========================================================================

    def _records_to_steps(
        self, result: Result[list[dict[str, Any]]], node_key: str = "ps"
    ) -> Result[list[PathStep]]:
        """Convert raw PS node records to PathStep models (Tier 6: conversion
        lives below the hexagonal boundary — services receive typed models)."""
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [from_neo4j_node(record[node_key], PathStep) for record in (result.value or [])]
        )

    async def get_standalone_steps(self, limit: int = 50) -> Result[list[PathStep]]:
        """Get PathStep nodes not belonging to any learning path.

        Args:
            limit: Maximum results

        Returns:
            Result containing PathStep models
        """
        query = """
        MATCH (ps:Entity {entity_type: 'path_step'})
        WHERE NOT (ps)<-[:HAS_STEP]-(:Entity {entity_type: 'learning_path'})
        RETURN ps
        ORDER BY ps.updated_at DESC
        LIMIT $limit
        """
        return self._records_to_steps(await self.execute_query(query, {"limit": limit}))

    async def get_prioritized_steps(
        self, user_uid: UserUID, limit: int = 20
    ) -> Result[list[PathStep]]:
        """Get PathStep nodes prioritized by user context.

        Prioritization order: in-progress first, then by status, then by priority,
        then by recency.

        Args:
            user_uid: User UID for personalization
            limit: Maximum results

        Returns:
            Result containing PathStep models
        """
        query = """
        MATCH (ps:Entity {entity_type: 'path_step'})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[progress:IN_PROGRESS]->(ps)
        RETURN ps, progress
        ORDER BY
            CASE
                WHEN progress IS NOT NULL THEN 0
                ELSE 1
            END,
            CASE ps.status
                WHEN 'in_progress' THEN 0
                WHEN 'not_started' THEN 1
                ELSE 2
            END,
            CASE ps.priority
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            ps.updated_at DESC
        LIMIT $limit
        """
        return self._records_to_steps(
            await self.execute_query(query, {"user_uid": user_uid, "limit": limit})
        )


class LpBackend(
    _LpStepMixin,
    _LpProgressMixin,
    _LpIntelligenceMixin,
    UniversalNeo4jBackend[LearningPath],
):
    """Domain backend for LearningPath entities.

    Extends UniversalNeo4jBackend[LearningPath] with:
    - ``_LpStepMixin`` — step management CRUD + path CRUD + exercise traversal (15 methods)
    - ``_LpProgressMixin`` — KU mastery progress + search queries (6 methods)
    - ``_LpIntelligenceMixin`` — intelligence + adaptive learning (8 methods)
    """
