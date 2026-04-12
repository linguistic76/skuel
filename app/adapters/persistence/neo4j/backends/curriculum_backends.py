"""Curriculum backends: Ku, PathStep, LearningPath, Exercise, RevisedExercise, ExerciseReport."""

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
from core.models.exercises.exercise import Exercise
from core.models.ku.ku import Ku
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName
from core.models.report.exercise_report import ExerciseReport
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import (
    CurriculumExerciseResult,
    PsDeleteStepRow,
    PsKnowledgeItemResult,
    PsKnowledgeSummaryResult,
    PsStandaloneStepRow,
    PsStepWithContextRow,
    PsStepWithKnowledgeRow,
    RequiredKnowledgeResult,
    RevisionChainResult,
)
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.journal.je_input import JeInput  # noqa: F401
    from core.models.journal.je_output import JeOutput  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401
    from core.models.submissions.report_schedule import ReportSchedule  # noqa: F401


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

    async def get_by_namespace(self, namespace: str) -> Result[list[Neo4jProperties]]:
        """Get all Kus in a specific namespace."""
        query = """
        MATCH (ku:Entity:Ku {namespace: $namespace})
        RETURN ku
        ORDER BY ku.title ASC
        """
        return await self.execute_query(query, {"namespace": namespace})

    async def search_by_alias(self, alias: str) -> Result[list[Neo4jProperties]]:
        """Search Kus by alias (case-insensitive substring)."""
        query = """
        MATCH (ku:Entity:Ku)
        WHERE any(a IN ku.aliases WHERE toLower(a) CONTAINS toLower($alias))
        RETURN ku
        ORDER BY ku.title ASC
        """
        return await self.execute_query(query, {"alias": alias})

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
        OPTIONAL MATCH (ps:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku)
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
        OPTIONAL MATCH (ps:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku)
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
        """Get learning paths containing this KU."""
        query = """
        MATCH (lp:Lp)-[:CONTAINS_KNOWLEDGE|INCLUDES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
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
        """Get events practicing this knowledge."""
        query = """
        MATCH (event:Event)-[:PRACTICES_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
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
    # KNOWLEDGE RELATIONSHIP CRUD (CONTAINS_KNOWLEDGE edges)
    # ========================================================================

    async def add_knowledge(self, ps_uid: str, ku_uid: str) -> Result[bool]:
        """MERGE CONTAINS_KNOWLEDGE relationship between PS and KU."""
        query = """
        MATCH (ps:Entity {uid: $ps_uid})
        MATCH (ku:Entity {uid: $ku_uid})
        MERGE (ps)-[r:CONTAINS_KNOWLEDGE]->(ku)
        SET r.created_at = COALESCE(r.created_at, datetime()),
            r.updated_at = datetime()
        RETURN r
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid, "ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        success = len(result.value or []) > 0
        if success:
            self.logger.info(f"Created CONTAINS_KNOWLEDGE: {ps_uid} -> {ku_uid}")
        return Result.ok(success)

    async def remove_knowledge(self, ps_uid: str, ku_uid: str) -> Result[bool]:
        """DELETE CONTAINS_KNOWLEDGE relationship between PS and KU."""
        query = """
        MATCH (ps:Entity {uid: $ps_uid})-[r:CONTAINS_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
        DELETE r
        RETURN count(r) as deleted
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid, "ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        deleted = records[0]["deleted"] if records else 0
        success = deleted > 0
        if success:
            self.logger.info(f"Removed CONTAINS_KNOWLEDGE: {ps_uid} -> {ku_uid}")
        return Result.ok(success)

    async def list_knowledge(self, ps_uid: str) -> Result[list[PsKnowledgeItemResult]]:
        """List CONTAINS_KNOWLEDGE relationships."""
        query = """
        MATCH (ps:Entity {uid: $ps_uid})-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN ku.uid as uid, ku.title as title, ku.domain as domain,
               r.created_at as created_at
        ORDER BY r.created_at, ku.title
        """
        result = await self.execute_query(query, {"ps_uid": ps_uid})
        if result.is_error:
            return Result.fail(result)
        items: list[PsKnowledgeItemResult] = [
            {
                "uid": r["uid"],
                "title": r["title"],
                "domain": r["domain"],
                "created_at": r["created_at"],
            }
            for r in result.value or []
        ]
        return Result.ok(items)

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
        MATCH (ps:Entity {uid: $ps_uid})-[:USES_KU|CONTAINS_KNOWLEDGE]->(ku:Entity)
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
        MATCH (ps:Entity:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE]->(ku:Entity {uid: $ku_uid})
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

    async def get_step_with_knowledge(self, uid: str) -> Result[list[PsStepWithKnowledgeRow]]:
        """Get step node with CONTAINS_KNOWLEDGE relationships."""
        query = """
        MATCH (s:Entity {uid: $uid})
        OPTIONAL MATCH (s)-[r:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN s, collect(ku.uid) as knowledge_uids
        """
        return cast(
            "Result[list[PsStepWithKnowledgeRow]]",
            await self.execute_query(query, {"uid": uid}),
        )

    async def get_step_with_context(self, uid: str) -> Result[list[PsStepWithContextRow]]:
        """Get step with comprehensive 11-part graph context in a single query."""
        query = """
        MATCH (ps:Entity {uid: $uid})

        // 1. Knowledge references
        OPTIONAL MATCH (ps)-[r_ku:CONTAINS_KNOWLEDGE]->(ku:Entity)
        WITH ps, collect({
            uid: ku.uid,
            title: ku.title,
            confidence: coalesce(r_ku.confidence, 1.0)
        }) as knowledge_rels

        // 2. Prerequisite steps
        OPTIONAL MATCH (ps)-[:REQUIRES_STEP]->(prereq_step:Entity {entity_type: 'path_step'})
        WITH ps, knowledge_rels, collect({
            uid: prereq_step.uid,
            title: prereq_step.title,
            completed: prereq_step.completed
        }) as prereq_steps

        // 3. Prerequisite knowledge
        OPTIONAL MATCH (ps)-[:REQUIRES_KNOWLEDGE {type: 'prerequisite'}]->(prereq_ku:Entity)
        WITH ps, knowledge_rels, prereq_steps, collect({
            uid: prereq_ku.uid,
            title: prereq_ku.title
        }) as prereq_knowledge

        // 4. Guiding principles (direct on PathStep)
        OPTIONAL MATCH (ps)-[:GUIDED_BY_PRINCIPLE]->(principle:Principle)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, collect(DISTINCT {
            uid: principle.uid,
            title: principle.title
        }) as principles

        // 5. Informed choices (direct on PathStep)
        OPTIONAL MATCH (ps)-[:INFORMS_CHOICE]->(choice:Choice)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, collect(DISTINCT {
            uid: choice.uid,
            title: choice.title
        }) as choices

        // 6. Practice opportunities: Habits (direct on PathStep)
        OPTIONAL MATCH (ps)-[:BUILDS_HABIT]->(habit:Habit)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, collect(DISTINCT {
            uid: habit.uid,
            title: habit.title,
            current_streak: habit.current_streak
        }) as habits

        // 7. Practice opportunities: Tasks (direct on PathStep)
        OPTIONAL MATCH (ps)-[:ASSIGNS_TASK]->(task:Task)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, collect(DISTINCT {
            uid: task.uid,
            title: task.title,
            status: task.status
        }) as tasks

        // 8. Practice opportunities: Events (direct on PathStep)
        OPTIONAL MATCH (ps)-[:SCHEDULES_EVENT]->(event:Event)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, collect(DISTINCT {
            uid: event.uid,
            title: event.title,
            event_date: event.event_date
        }) as events

        // 9. Practice opportunities: Goals (direct on PathStep)
        OPTIONAL MATCH (ps)-[:SUPPORTS_GOAL]->(goal:Goal)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, collect(DISTINCT {
            uid: goal.uid,
            title: goal.title,
            status: goal.status
        }) as goals

        // 10. Learning path context (if part of sequence)
        OPTIONAL MATCH (lp:Entity {entity_type: 'learning_path'})-[r_path:HAS_STEP|CONTAINS_STEP]->(ps)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, goals, {
            uid: lp.uid,
            name: lp.title,
            goal: lp.goal,
            sequence: coalesce(r_path.sequence, 0)
        } as path_context

        // 11. Dependent steps (steps that require this one)
        OPTIONAL MATCH (dependent:Entity {entity_type: 'path_step'})-[:REQUIRES_STEP]->(ps)
        WITH ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices, habits, tasks, events, goals, path_context, collect({
            uid: dependent.uid,
            title: dependent.title,
            completed: dependent.completed
        }) as dependent_steps

        RETURN ps, knowledge_rels, prereq_steps, prereq_knowledge, principles, choices,
               habits, tasks, events, goals, path_context, dependent_steps
        """
        return cast(
            "Result[list[PsStepWithContextRow]]",
            await self.execute_query(query, {"uid": uid}),
        )

    async def update_step_fields(
        self, _uid: str, set_clauses: list[str], params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]:
        """Update step fields and return step with knowledge relationships."""
        query = f"""
        MATCH (s:Entity {{uid: $uid}})
        SET {", ".join(set_clauses)}
        WITH s
        OPTIONAL MATCH (s)-[:CONTAINS_KNOWLEDGE]->(ku:Entity)
        RETURN s, collect(ku.uid) as knowledge_uids
        """
        return await self.execute_query(query, params)

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
    ) -> Result[list[dict[str, Any]]]:
        """List step nodes with knowledge relationships, pagination, and optional filters."""
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

        return await self.execute_query(query, params)

    # ========================================================================
    # SEARCH QUERIES (migrated from PsSearchService)
    # ========================================================================

    async def get_steps_for_learning_path(
        self, path_uid: str, limit: int = 100
    ) -> Result[list[dict[str, Any]]]:
        """Get PathStep nodes belonging to a learning path, ordered by sequence.

        Args:
            path_uid: Learning path UID
            limit: Maximum results

        Returns:
            Result containing raw PS node records
        """
        query = """
        MATCH (lp:Entity {uid: $path_uid})-[:HAS_STEP]->(ps:Entity {entity_type: 'path_step'})
        RETURN ps
        ORDER BY ps.sequence ASC
        LIMIT $limit
        """
        return await self.execute_query(query, {"path_uid": path_uid, "limit": limit})

    async def get_standalone_steps(self, limit: int = 50) -> Result[list[PsStandaloneStepRow]]:
        """Get PathStep nodes not belonging to any learning path.

        Args:
            limit: Maximum results

        Returns:
            Result containing raw PS node records
        """
        query = """
        MATCH (ps:Entity {entity_type: 'path_step'})
        WHERE NOT (ps)<-[:HAS_STEP]-(:Entity {entity_type: 'learning_path'})
        RETURN ps
        ORDER BY ps.updated_at DESC
        LIMIT $limit
        """
        return cast(
            "Result[list[PsStandaloneStepRow]]",
            await self.execute_query(query, {"limit": limit}),
        )

    async def get_steps_using_ku(
        self, ku_uid: str, limit: int = 20
    ) -> Result[list[dict[str, Any]]]:
        """Get PathStep nodes that contain/teach a knowledge unit.

        Graph Pattern: (PS)-[:CONTAINS_KNOWLEDGE]->(Ku)

        Args:
            ku_uid: Knowledge unit UID
            limit: Maximum results

        Returns:
            Result containing raw PS node records
        """
        query = """
        MATCH (ku:Entity {uid: $ku_uid})<-[:CONTAINS_KNOWLEDGE]-(ps:Entity {entity_type: 'path_step'})
        RETURN ps
        ORDER BY ps.sequence ASC
        LIMIT $limit
        """
        return await self.execute_query(query, {"ku_uid": ku_uid, "limit": limit})

    async def get_prioritized_steps(
        self, user_uid: UserUID, limit: int = 20
    ) -> Result[list[dict[str, Any]]]:
        """Get PathStep nodes prioritized by user context.

        Prioritization order: in-progress first, then by status, then by priority,
        then by recency.

        Args:
            user_uid: User UID for personalization
            limit: Maximum results

        Returns:
            Result containing raw PS node records
        """
        query = """
        MATCH (ps:Entity {entity_type: 'path_step'})
        OPTIONAL MATCH (u:User {uid: $user_uid})-[progress:STUDYING]->(ps)
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
        return await self.execute_query(query, {"user_uid": user_uid, "limit": limit})


class LpBackend(
    _LpStepMixin,
    _LpProgressMixin,
    _LpIntelligenceMixin,
    UniversalNeo4jBackend[LearningPath],
):
    """Domain backend for LearningPath entities.

    Extends UniversalNeo4jBackend[LearningPath] with:
    - ``_LpStepMixin`` — step management CRUD + path CRUD (14 methods)
    - ``_LpProgressMixin`` — KU mastery progress + search queries (6 methods)
    - ``_LpIntelligenceMixin`` — intelligence + adaptive learning (8 methods)
    """


class ExerciseBackend(UniversalNeo4jBackend[Exercise]):
    """
    Domain backend for Exercise entities.

    Extends UniversalNeo4jBackend[Exercise] with exercise-specific Cypher
    that was previously inline in ExerciseService.

    Methods:
    - create_owns_relationship      — MERGE OWNS (user -> exercise)
    - create_for_group_relationship — MERGE FOR_GROUP (exercise -> group)
    - get_user_exercises             — OWNS query for user's exercises
    - get_student_exercises          — MEMBER_OF + FOR_GROUP traversal
    - get_student_exercises_with_status — Above + FULFILLS_EXERCISE submission check
    - get_exercises_for_curriculum   — Reverse REQUIRES_KNOWLEDGE lookup
    - link_to_curriculum             — MERGE REQUIRES_KNOWLEDGE relationship
    - unlink_from_curriculum         — DELETE REQUIRES_KNOWLEDGE relationship
    - get_required_knowledge         — Query all KUs required by an exercise
    - get_exercise_for_submission    — FULFILLS_EXERCISE reverse lookup
    """

    async def link_to_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """
        Create REQUIRES_KNOWLEDGE relationship from exercise to curriculum KU.

        Args:
            exercise_uid: Exercise UID (entity_type='exercise')
            curriculum_uid: Curriculum KU UID (entity_type='ku' or 'resource')

        Returns:
            Result[bool] - True if relationship created
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MATCH (curriculum:Entity {{uid: $curriculum_uid}})
            WHERE curriculum.entity_type IN ['ku', 'resource']
            MERGE (exercise)-[r:{RelationshipName.REQUIRES_KNOWLEDGE}]->(curriculum)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"exercise_uid": exercise_uid, "curriculum_uid": curriculum_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="Exercise or Curriculum KU",
                    identifier=f"{exercise_uid} -> {curriculum_uid}",
                )
            )
        return Result.ok(True)

    async def unlink_from_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """
        Remove REQUIRES_KNOWLEDGE relationship between exercise and curriculum KU.

        Args:
            exercise_uid: Exercise UID
            curriculum_uid: Curriculum KU UID

        Returns:
            Result[bool] - True if relationship removed
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
                  -[r:{RelationshipName.REQUIRES_KNOWLEDGE}]->
                  (curriculum:Entity {{uid: $curriculum_uid}})
            DELETE r
            RETURN true as success
            """,
            {"exercise_uid": exercise_uid, "curriculum_uid": curriculum_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="REQUIRES_KNOWLEDGE relationship",
                    identifier=f"{exercise_uid} -> {curriculum_uid}",
                )
            )
        return Result.ok(True)

    async def get_required_knowledge(
        self, exercise_uid: str
    ) -> Result[list[RequiredKnowledgeResult]]:
        """
        Get all curriculum KUs required by an exercise.

        Args:
            exercise_uid: Exercise UID

        Returns:
            Result containing list of curriculum KU summaries
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
                  -[:{RelationshipName.REQUIRES_KNOWLEDGE}]->
                  (curriculum:Entity)
            RETURN curriculum.uid as uid,
                   curriculum.title as title,
                   curriculum.entity_type as entity_type,
                   curriculum.complexity as complexity,
                   curriculum.learning_level as learning_level
            ORDER BY curriculum.title
            """,
            {"exercise_uid": exercise_uid},
        )
        if result.is_error:
            return Result.fail(result)
        items: list[RequiredKnowledgeResult] = [dict(record) for record in (result.value or [])]  # type: ignore[misc]
        return Result.ok(items)

    async def create_owns_relationship(
        self, user_uid: UserUID, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create OWNS relationship from user to exercise.

        Args:
            user_uid: User who owns this exercise
            exercise_uid: Exercise UID

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})
            MATCH (e:Entity {{uid: $exercise_uid}})
            MERGE (u)-[:{RelationshipName.OWNS.value}]->(e)
            RETURN true as success
            """,
            {"user_uid": user_uid, "exercise_uid": exercise_uid},
        )

    async def create_for_group_relationship(
        self, exercise_uid: str, group_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create FOR_GROUP relationship from exercise to group.

        Args:
            exercise_uid: Exercise UID
            group_uid: Target group UID

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MATCH (group:Group {{uid: $group_uid}})
            MERGE (exercise)-[:{RelationshipName.FOR_GROUP}]->(group)
            RETURN true as success
            """,
            {"exercise_uid": exercise_uid, "group_uid": group_uid},
        )

    async def get_user_exercises(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all exercises owned by a user via OWNS relationship.

        Args:
            user_uid: User UID

        Returns:
            Result containing exercise node records
        """
        return await self.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(e:Exercise)
            RETURN e
            ORDER BY e.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_student_exercises(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get assigned exercises for a student via MEMBER_OF -> Group <- FOR_GROUP.

        Args:
            user_uid: Student UID

        Returns:
            Result containing exercise node records
        """
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            MATCH (exercise:Entity {{entity_type: 'exercise'}})-[:{RelationshipName.FOR_GROUP}]->(group)
            WHERE exercise.scope = 'assigned'
            RETURN exercise
            ORDER BY exercise.due_date ASC, exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_student_exercises_with_status(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get assigned exercises with submission + report status for a student.

        Returns exercise properties enriched with:
        - has_submission: bool
        - submission_uid: str | None (most recent submission)
        - submission_status: str | None
        - has_report: bool
        - report_uid: str | None (most recent report)
        - report_outcome: str | None (assessment_outcome on the report)
        - group_name: str

        Args:
            user_uid: Student UID

        Returns:
            Result containing enriched exercise records
        """
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            MATCH (exercise:Entity {{entity_type: 'exercise'}})-[:{RelationshipName.FOR_GROUP}]->(group)
            WHERE exercise.scope = 'assigned'
            OPTIONAL MATCH (user)-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH exercise, group, sub, report
            ORDER BY sub.created_at DESC
            WITH exercise, group,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   group.title AS group_name
            ORDER BY exercise.due_date ASC, exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_enrolled_ps_exercises_with_status(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get personal exercises linked to PathSteps the user is enrolled in.

        Returns the same shape as get_student_exercises_with_status() so results
        can be merged at the service layer. Exercises are discovered via:
            (user)-[:IN_PROGRESS]->(ps)-[:RELATED_TO]->(exercise {scope: 'personal'})

        Args:
            user_uid: Student UID

        Returns:
            Result containing enriched exercise records (group_name is empty string)
        """
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.IN_PROGRESS}]->(ps:Entity)
            MATCH (ps)-[:{RelationshipName.RELATED_TO}]->(exercise:Entity {{entity_type: 'exercise'}})
            WHERE exercise.scope = 'personal'
            WITH DISTINCT user, exercise
            OPTIONAL MATCH (user)-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH exercise, sub, report
            ORDER BY sub.created_at DESC
            WITH exercise,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   '' AS group_name
            ORDER BY exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_ps_exercises_with_status(
        self, ps_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get exercises linked to a specific PathStep with submission/feedback status.

        Scoped version of get_enrolled_ps_exercises_with_status() — returns the same
        shape (compatible with ExerciseStatusRow) but for a single PathStep.
        """
        return await self.execute_query(
            f"""
            MATCH (ps:Entity {{uid: $ps_uid}})-[:{RelationshipName.RELATED_TO}]->(exercise:Entity {{entity_type: 'exercise'}})
            OPTIONAL MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH exercise, sub, report
            ORDER BY sub.created_at DESC
            WITH exercise,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   '' AS group_name
            ORDER BY exercise.title
            """,
            {"ps_uid": ps_uid, "user_uid": user_uid},
        )

    async def get_exercises_for_curriculum(
        self, curriculum_uid: str
    ) -> Result[list[CurriculumExerciseResult]]:
        """Get all exercises that require a specific curriculum KU.

        Args:
            curriculum_uid: Curriculum KU UID

        Returns:
            Result containing exercise summary records
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{entity_type: 'exercise'}})
                  -[:{RelationshipName.REQUIRES_KNOWLEDGE}]->
                  (curriculum:Entity {{uid: $curriculum_uid}})
            RETURN exercise.uid as uid,
                   exercise.title as title,
                   exercise.scope as scope,
                   exercise.due_date as due_date,
                   exercise.status as status,
                   exercise.form_schema as form_schema
            ORDER BY exercise.created_at DESC
            """,
            {"curriculum_uid": curriculum_uid},
        )
        if result.is_error:
            return Result.fail(result)
        items: list[CurriculumExerciseResult] = [
            dict(record)
            for record in (result.value or [])  # type: ignore[misc]
        ]
        return Result.ok(items)

    async def get_exercise_for_submission(
        self, submission_uid: str
    ) -> Result[Neo4jProperties | None]:
        """Get the exercise that a submission fulfills via FULFILLS_EXERCISE relationship.

        Args:
            submission_uid: Submission UID

        Returns:
            Result containing exercise summary dict or None if not linked
        """
        result = await self.execute_query(
            f"""
            MATCH (s:Entity {{uid: $uid}})-[:{RelationshipName.FULFILLS_EXERCISE}]->(ex:Entity:Exercise)
            RETURN ex.uid AS exercise_uid, ex.title AS exercise_title
            LIMIT 1
            """,
            {"uid": submission_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        return Result.ok(dict(records[0]))

    async def get_exercises_for_path_steps(
        self, ps_uids: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Get exercises associated with a list of PathStep UIDs.

        Traverses PathStep -[:USES_KU|CONTAINS_KNOWLEDGE]-> Ku <-[:REQUIRES_KNOWLEDGE]- Exercise
        to find exercises that practice knowledge from those PathSteps.

        Args:
            ps_uids: List of PathStep UIDs

        Returns:
            Result containing distinct exercise property dicts
        """
        if not ps_uids:
            return Result.ok([])

        result = await self.execute_query(
            f"""
            MATCH (ps:Entity:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE]->(ku:Entity)
                  <-[:{RelationshipName.REQUIRES_KNOWLEDGE}]-(ex:Entity {{entity_type: 'exercise'}})
            WHERE ps.uid IN $ps_uids
            RETURN DISTINCT ex.uid AS uid,
                   ex.title AS title,
                   ex.scope AS scope,
                   ex.description AS description,
                   ex.status AS status
            ORDER BY ex.title
            """,
            {"ps_uids": ps_uids},
        )
        if result.is_error:
            return Result.fail(result)
        items = [dict(record) for record in (result.value or [])]
        return Result.ok(items)

    # ========================================================================
    # TEACHER REVIEW OPERATIONS (migrated from TeacherReviewService)
    # ========================================================================

    async def get_exercises_with_submission_counts(
        self, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get teacher's exercises with submission and reviewed counts."""
        query = f"""
        MATCH (user:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(exercise:Entity:Exercise)
        OPTIONAL MATCH (s:Entity {{entity_type: 'exercise_submission'}})-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise)
        WITH exercise, count(s) AS total_count,
             count(CASE WHEN s.status = 'completed' THEN 1 END) AS reviewed_count
        RETURN exercise.uid AS uid, exercise.title AS title,
               exercise.scope AS scope, exercise.created_at AS created_at,
               total_count, reviewed_count,
               total_count - reviewed_count AS pending_count
        ORDER BY exercise.created_at DESC
        """
        return await self.execute_query(query, {"teacher_uid": teacher_uid})


class RevisedExerciseBackend(UniversalNeo4jBackend["RevisedExercise"]):
    """
    Domain backend for RevisedExercise entities.

    Provides relationship-specific Cypher for the five-phase learning loop:
    - verify_teacher_authority    — Check teacher review authority graph path
    - create_owns_relationship   — MERGE OWNS (teacher -> revised exercise)
    - auto_share_with_student    — MERGE SHARES_WITH (student -> revised exercise)
    - list_for_student           — Query revisions targeting a student
    - link_to_report             — MERGE RESPONDS_TO_REPORT relationship
    - link_to_exercise           — MERGE REVISES_EXERCISE relationship
    - get_revision_chain         — Query all revisions of an original exercise
    """

    async def link_to_report(self, re_uid: str, report_uid: str) -> Result[bool]:
        """Create RESPONDS_TO_REPORT relationship from revised exercise to report."""
        result = await self.execute_query(
            f"""
            MATCH (re:Entity {{uid: $re_uid, entity_type: 'revised_exercise'}})
            MATCH (fb:Entity {{uid: $report_uid}})
            WHERE fb.entity_type IN ['exercise_report', 'activity_report']
            MERGE (re)-[r:{RelationshipName.RESPONDS_TO_REPORT}]->(fb)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"re_uid": re_uid, "report_uid": report_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="RESPONDS_TO_REPORT relationship",
                    identifier=f"{re_uid} -> {report_uid}",
                )
            )
        return Result.ok(True)

    async def link_to_exercise(self, re_uid: str, exercise_uid: str) -> Result[bool]:
        """Create REVISES_EXERCISE relationship from revised exercise to original exercise."""
        result = await self.execute_query(
            f"""
            MATCH (re:Entity {{uid: $re_uid, entity_type: 'revised_exercise'}})
            MATCH (ex:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MERGE (re)-[r:{RelationshipName.REVISES_EXERCISE}]->(ex)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"re_uid": re_uid, "exercise_uid": exercise_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="REVISES_EXERCISE relationship",
                    identifier=f"{re_uid} -> {exercise_uid}",
                )
            )
        return Result.ok(True)

    async def verify_teacher_authority(
        self, teacher_uid: str, report_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify teacher has review authority over a report.

        Checks the graph path (OWNS-based, per ADR-040):
        - (ExerciseReport)-[:REPORT_FOR]->(Submission) exists
        - (Student)-[:OWNS]->(Submission)
        - Teacher identity is role-gated at the route level (@require_role)

        teacher_uid is retained for audit logging and future per-teacher scoping.

        Args:
            teacher_uid: Teacher user UID (for audit; access is role-gated at route)
            report_uid: Report UID
            student_uid: Student user UID

        Returns:
            Result containing matching submission records (empty if no authority)
        """
        return await self.execute_query(
            """
            MATCH (fb:Entity {uid: $report_uid})-[:REPORT_FOR]->(submission:Entity)
            MATCH (student:User {uid: $student_uid})-[:OWNS]->(submission)
            WHERE submission.entity_type = 'exercise_submission'
            RETURN submission.uid AS submission_uid
            """,
            {
                "report_uid": report_uid,
                "teacher_uid": teacher_uid,
                "student_uid": student_uid,
            },
        )

    async def create_owns_relationship(
        self, teacher_uid: str, re_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create OWNS relationship from teacher to revised exercise.

        Args:
            teacher_uid: Teacher user UID
            re_uid: Revised exercise UID

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (u:User {{uid: $teacher_uid}})
            MATCH (re:Entity {{uid: $re_uid}})
            MERGE (u)-[:{RelationshipName.OWNS.value}]->(re)
            RETURN true as success
            """,
            {"teacher_uid": teacher_uid, "re_uid": re_uid},
        )

    async def auto_share_with_student(
        self, student_uid: str, re_uid: str, shared_at: str
    ) -> Result[list[Neo4jProperties]]:
        """Auto-share revised exercise with student via SHARES_WITH.

        Same pattern as assignment auto-sharing (ADR-040).

        Args:
            student_uid: Student user UID
            re_uid: Revised exercise UID
            shared_at: ISO timestamp for the share

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (student:User {{uid: $student_uid}})
            MATCH (re:Entity {{uid: $re_uid}})
            MERGE (student)-[r:{RelationshipName.SHARES_WITH.value}]->(re)
            ON CREATE SET r.shared_at = $shared_at, r.role = 'student'
            SET re.visibility = 'shared'
            RETURN true as success
            """,
            {
                "student_uid": student_uid,
                "re_uid": re_uid,
                "shared_at": shared_at,
            },
        )

    async def list_for_student(
        self, student_uid: str, teacher_uid: str | None = None
    ) -> Result[list[Neo4jProperties]]:
        """List revised exercises targeting a specific student.

        Args:
            student_uid: The student whose revisions to list
            teacher_uid: If provided, only return revisions owned by this teacher

        Returns:
            Result containing revised exercise node records
        """
        if teacher_uid:
            query = f"""
            MATCH (u:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(re:RevisedExercise {{student_uid: $student_uid}})
            RETURN re
            ORDER BY re.created_at DESC
            """
            params: dict[str, str] = {"student_uid": student_uid, "teacher_uid": teacher_uid}
        else:
            query = """
            MATCH (re:RevisedExercise {student_uid: $student_uid})
            RETURN re
            ORDER BY re.created_at DESC
            """
            params = {"student_uid": student_uid}

        return await self.execute_query(query, params)

    async def get_by_report_uid(self, report_uid: str) -> Result[list[Neo4jProperties]]:
        """Look up a RevisedExercise by the report it responds to."""
        query = """
        MATCH (re:RevisedExercise {report_uid: $report_uid})
        RETURN re
        LIMIT 1
        """
        return await self.execute_query(query, {"report_uid": report_uid})

    async def get_revision_chain(self, exercise_uid: str) -> Result[list[RevisionChainResult]]:
        """
        Get all revised exercises in the revision chain for an original exercise.

        Returns revisions ordered by revision_number ascending.
        """
        result = await self.execute_query(
            f"""
            MATCH (re:Entity {{entity_type: 'revised_exercise'}})
                  -[:{RelationshipName.REVISES_EXERCISE}]->
                  (ex:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            RETURN re.uid as uid,
                   re.title as title,
                   re.revision_number as revision_number,
                   re.student_uid as student_uid,
                   re.report_uid as report_uid,
                   re.status as status,
                   re.created_at as created_at
            ORDER BY re.revision_number ASC
            """,
            {"exercise_uid": exercise_uid},
        )
        if result.is_error:
            return Result.fail(result)
        items: list[RevisionChainResult] = [
            dict(record)
            for record in (result.value or [])  # type: ignore[misc]
        ]
        return Result.ok(items)

    async def get_for_teacher(
        self, teacher_uid: str, limit: int = 50
    ) -> Result[list[Neo4jProperties]]:
        """
        List all RevisedExercises created by a teacher, ordered by most recent.

        Traverses OWNS relationship from teacher to revised exercises for
        authoritative ownership lookup. Includes student and exercise context
        for teacher dashboard display.

        Args:
            teacher_uid: The teacher's user UID
            limit: Maximum records to return (default 50)

        Returns:
            Result containing revised exercise records with student/exercise context
        """
        return await self.execute_query(
            f"""
            MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(re:RevisedExercise)
            OPTIONAL MATCH (re)-[:{RelationshipName.REVISES_EXERCISE.value}]->(ex:Entity {{entity_type: 'exercise'}})
            RETURN re.uid AS uid,
                   re.title AS title,
                   re.revision_number AS revision_number,
                   re.student_uid AS student_uid,
                   re.report_uid AS report_uid,
                   re.status AS status,
                   re.created_at AS created_at,
                   ex.uid AS exercise_uid,
                   ex.title AS exercise_title
            ORDER BY re.created_at DESC
            LIMIT $limit
            """,
            {"teacher_uid": teacher_uid, "limit": limit},
        )


class ExerciseReportBackend(UniversalNeo4jBackend[ExerciseReport]):
    """
    Domain backend for ExerciseReport entities.

    Provides relationship-specific Cypher for the five-phase learning loop:
    - get_report_for_submission     — REPORT_FOR reverse lookup
    - get_reports_for_student_exercise — all reports for a student on an exercise
    - get_reports_by_teacher        — all reports created by a teacher (user_uid)
    - create_ai_report_node         — atomic create + OWNS + REPORT_FOR + submission update
    """

    async def get_report_for_submission(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """
        Find the ExerciseReport linked to a submission via REPORT_FOR.

        Returns the most recent report first (there may be multiple — one per
        review round). Includes teacher name for display.

        Args:
            submission_uid: The ExerciseSubmission UID

        Returns:
            Result containing report records ordered by created_at DESC
        """
        return await self.execute_query(
            f"""
            MATCH (report:ExerciseReport)-[:{RelationshipName.REPORT_FOR.value}]->(sub:Entity {{uid: $submission_uid}})
            OPTIONAL MATCH (teacher:User {{uid: report.user_uid}})
            RETURN report.uid AS uid,
                   report.title AS title,
                   report.report_content AS report_content,
                   report.status AS status,
                   report.processor_type AS processor_type,
                   report.assessment_outcome AS assessment_outcome,
                   report.assessment_score AS assessment_score,
                   report.created_at AS created_at,
                   report.user_uid AS teacher_uid,
                   teacher.username AS teacher_name
            ORDER BY report.created_at DESC
            """,
            {"submission_uid": submission_uid},
        )

    async def get_reports_for_student_exercise(
        self, student_uid: str, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """
        Find all ExerciseReports for a student's submissions on a given exercise.

        Traverses: (Student)-[:OWNS]->(Submission)-[:FULFILLS_EXERCISE]->(Exercise)
                   (Report)-[:REPORT_FOR]->(Submission)

        Useful for reviewing the full feedback history on a student's work
        on a specific exercise across all revision rounds.

        Args:
            student_uid: The student's user UID
            exercise_uid: The Exercise UID

        Returns:
            Result containing report records with submission context, ordered by created_at DESC
        """
        return await self.execute_query(
            f"""
            MATCH (student:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(sub:Entity)
            MATCH (sub)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MATCH (report:ExerciseReport)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
            OPTIONAL MATCH (teacher:User {{uid: report.user_uid}})
            RETURN report.uid AS uid,
                   report.title AS title,
                   report.report_content AS report_content,
                   report.status AS status,
                   report.processor_type AS processor_type,
                   report.assessment_outcome AS assessment_outcome,
                   report.assessment_score AS assessment_score,
                   report.created_at AS created_at,
                   report.user_uid AS teacher_uid,
                   teacher.username AS teacher_name,
                   sub.uid AS submission_uid,
                   sub.title AS submission_title
            ORDER BY report.created_at DESC
            """,
            {"student_uid": student_uid, "exercise_uid": exercise_uid},
        )

    async def get_reports_by_teacher(
        self, teacher_uid: str, limit: int = 50
    ) -> Result[list[Neo4jProperties]]:
        """
        List all ExerciseReports created by a teacher, ordered by most recent.

        Uses user_uid field (denormalized on creation) for O(1) lookup.
        Includes submission and student context for dashboard display.

        Args:
            teacher_uid: The teacher's user UID
            limit: Maximum records to return (default 50)

        Returns:
            Result containing report records with student/submission context
        """
        return await self.execute_query(
            f"""
            MATCH (report:ExerciseReport {{user_uid: $teacher_uid}})
            OPTIONAL MATCH (report)-[:{RelationshipName.REPORT_FOR.value}]->(sub:Entity)
            OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(sub)
            RETURN report.uid AS uid,
                   report.title AS title,
                   report.status AS status,
                   report.processor_type AS processor_type,
                   report.assessment_outcome AS assessment_outcome,
                   report.assessment_score AS assessment_score,
                   report.created_at AS created_at,
                   sub.uid AS submission_uid,
                   sub.title AS submission_title,
                   student.uid AS student_uid,
                   student.username AS student_name
            ORDER BY report.created_at DESC
            LIMIT $limit
            """,
            {"teacher_uid": teacher_uid, "limit": limit},
        )

    async def create_ai_report_node(self, params: dict[str, str]) -> Result[list[Neo4jProperties]]:
        """
        Atomically create an AI-generated ExerciseReport entity in Neo4j.

        Single transaction creates:
        - :Entity:ExerciseReport node with all report fields
        - (creator)-[:OWNS]->(report) relationship
        - (report)-[:REPORT_FOR]->(submission) relationship
        - Denormalised report_content + report_generated_at on the submission

        Args:
            params: Dict with keys: submission_uid, report_uid, user_uid,
                    feedback_text, title, entity_type, completed_status,
                    processor_type, assessment_outcome, now

        Returns:
            Result containing record with report_uid on success
        """
        return await self.execute_query(
            f"""
            MATCH (submission:Entity {{uid: $submission_uid}})
            OPTIONAL MATCH (creator:User {{uid: $user_uid}})

            SET submission.report_content = $feedback_text,
                submission.report_generated_at = datetime($now),
                submission.updated_at = datetime($now)

            CREATE (fb:Entity:ExerciseReport {{
                uid: $report_uid,
                title: $title,
                entity_type: $entity_type,
                user_uid: $user_uid,
                status: $completed_status,
                processor_type: $processor_type,
                assessment_outcome: $assessment_outcome,
                content: $feedback_text,
                report_content: $feedback_text,
                report_generated_at: datetime($now),
                subject_uid: $submission_uid,
                created_by: $user_uid,
                created_at: datetime($now),
                updated_at: datetime($now)
            }})

            WITH submission, creator, fb
            CREATE (fb)-[:{RelationshipName.REPORT_FOR.value}]->(submission)

            WITH submission, creator, fb
            WHERE creator IS NOT NULL
            CREATE (creator)-[:{RelationshipName.OWNS.value}]->(fb)

            RETURN fb.uid AS report_uid
            """,
            params,
        )

    async def get_linked_ku_and_student(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """
        Get Ku UIDs and student UID linked to a submission via APPLIES_KNOWLEDGE.

        Used by mastery propagation after AI report generation.

        Returns:
            Records with ku_uid and student_uid fields
        """
        return await self.execute_query(
            f"""
            MATCH (submission:Entity {{uid: $submission_uid}})-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(ku:Entity {{entity_type: 'ku'}})
            OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission)
            RETURN ku.uid AS ku_uid, student.uid AS student_uid
            """,
            {"submission_uid": submission_uid},
        )


# Entity types that can be shared while active (not just completed)
_ACTIVITY_ENTITY_TYPES = frozenset({"task", "goal", "habit", "event", "choice", "principle"})
