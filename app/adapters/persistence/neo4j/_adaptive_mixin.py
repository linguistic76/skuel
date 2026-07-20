"""
Adaptive Mixin
==============

Practice, keyword search, and adaptive mastery tracking operations for domain
backends.

Provides practice tracking (event-based KU practice, practice count increment),
keyword/vector search (similar by keywords, text search, semantic chunk search),
and adaptive mastery tracking (mastery completion, user masteries, learning
paths, preferences).

Requires on concrete class:
    execute_query, logger  (provided by UniversalNeo4jBackend)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.pathways.learning_path import LearningPath
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins
    import logging

    from core.models.type_hints import Neo4jProperties


class _AdaptiveMixin:
    """Practice, search, and adaptive mastery tracking operations.

    Domain backends that need practice tracking, keyword search, or adaptive
    mastery queries should add ``_AdaptiveMixin`` to their class bases.

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
    # PRACTICE OPERATIONS
    # ========================================================================

    async def find_kus_practiced_by_event(self, event_uid: str) -> Result[list[Neo4jProperties]]:
        """Find KU UIDs practiced by a completed event via APPLIES_KNOWLEDGE.

        APPLIES_KNOWLEDGE is THE Event→Ku edge — the one EVENTS_CONFIG
        registers, Edge-YAML ingestion writes (``connections.applies_knowledge``),
        and ``create_study_session`` MERGEs. The former read matched a
        writer-less "PRACTICES" edge no code path ever wrote (2026-07-10
        audit), so every event completion silently found zero KUs to practice.
        """
        query = f"""
        MATCH (event:Event {{uid: $event_uid}})-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(ku:Entity)
        RETURN DISTINCT ku.uid as ku_uid
        """
        return await self.execute_query(query, {"event_uid": event_uid})

    async def increment_practice_count(
        self, ku_uid: str, occurred_at: str
    ) -> Result[list[Neo4jProperties]]:
        """Increment practice count and update last_practiced_date on a KU."""
        query = """
        MATCH (ku:Entity {uid: $ku_uid})
        SET ku.times_practiced_in_events = COALESCE(ku.times_practiced_in_events, 0) + 1,
            ku.last_practiced_date = datetime($occurred_at)
        RETURN ku.times_practiced_in_events as new_count
        """
        return await self.execute_query(query, {"ku_uid": ku_uid, "occurred_at": occurred_at})

    # ========================================================================
    # SEARCH OPERATIONS
    # ========================================================================

    # semantic_search_chunks lives on VectorSearchBackend (chunk retrieval is a
    # vector-index concern, not a domain backend concern). See
    # adapters/persistence/neo4j/vector_search_backend.py.

    async def find_similar_by_keywords(self, uid: str, limit: int) -> Result[list[Neo4jProperties]]:
        """Find similar entities using keyword matching and structural similarity."""
        query = """
        MATCH (source:Entity {uid: $uid})
        MATCH (similar:Entity)
        WHERE similar.uid <> source.uid

        // Calculate similarity based on:
        // 1. Shared tags
        WITH source, similar,
             size([t IN source.tags WHERE t IN similar.tags]) as shared_tags

        // 2. Same domain
        WITH source, similar, shared_tags,
             CASE WHEN source.domain = similar.domain THEN 2 ELSE 0 END as domain_match

        // 3. Keyword overlap (simple text similarity)
        WITH source, similar, shared_tags, domain_match,
             size([word IN split(toLower(source.title), ' ')
                   WHERE toLower(similar.title) CONTAINS word]) as title_overlap

        // Combine scores
        WITH similar,
             (shared_tags * 3 + domain_match + title_overlap) as similarity_score
        WHERE similarity_score > 0

        RETURN similar
        ORDER BY similarity_score DESC
        LIMIT $limit
        """
        return await self.execute_query(query, {"uid": uid, "limit": limit})

    async def search_by_keywords(
        self, query_text: str, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Keyword-based search using CONTAINS on title/summary/tags."""
        query = """
        MATCH (ku:Entity)
        WHERE toLower(ku.title) CONTAINS toLower($query_text)
           OR toLower(ku.summary) CONTAINS toLower($query_text)
           OR any(tag IN ku.tags WHERE toLower(tag) CONTAINS toLower($query_text))
        RETURN ku
        ORDER BY ku.updated_at DESC
        LIMIT $limit
        """
        return await self.execute_query(query, {"query_text": query_text, "limit": limit})

    # ========================================================================
    # ADAPTIVE MASTERY TRACKING
    # ========================================================================

    async def track_mastery_completion(
        self, user_uid: UserUID, ku_uid: str, completion_time_minutes: int
    ) -> Result[list[Neo4jProperties]]:
        """Create/update MASTERED relationship when user completes a KU."""
        query = """
        MATCH (u:User {uid: $user_uid}), (k:Entity {uid: $ku_uid})
        MERGE (u)-[m:MASTERED]->(k)
        ON CREATE SET
            m.mastery_level = 'introduced',
            m.created_at = datetime(),
            m.time_to_mastery_hours = $completion_time_minutes / 60.0,
            m.source = 'curriculum'
        ON MATCH SET
            m.mastery_level = 'proficient',
            m.updated_at = datetime()
        RETURN m
        """
        return await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "ku_uid": ku_uid,
                "completion_time_minutes": completion_time_minutes,
            },
        )

    async def query_user_masteries(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Query all MASTERED relationships with full metadata for a user."""
        query = """
        MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(k:Entity)
        RETURN
            k.uid as ku_uid,
            m.mastery_level as mastery_level,
            m.confidence_score as confidence_score,
            m.mastery_score as mastery_score,
            m.learning_velocity as learning_velocity,
            m.time_to_mastery_hours as time_to_mastery_hours,
            m.review_frequency_days as review_frequency_days,
            m.mastery_evidence as mastery_evidence,
            m.last_reviewed as last_reviewed,
            m.last_practiced as last_practiced,
            m.learning_path_context as learning_path_context,
            m.difficulty_experienced as difficulty_experienced,
            m.preferred_learning_method as preferred_learning_method,
            m.created_at as created_at,
            m.updated_at as updated_at
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def query_active_learning_paths(self, user_uid: UserUID) -> Result[list[LearningPath]]:
        """Query user's active/in-progress learning paths as typed models.

        Enrollment lifecycle lives on the ENROLLED_IN relationship
        (UserBackend.enroll_in_learning_path sets r.status='active';
        complete_learning_path flips it to 'completed') — not on the LP node.
        Records that fail node→model conversion are skipped with a warning.
        """
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node

        query = """
        MATCH (u:User {uid: $user_uid})-[r:ENROLLED_IN]->(lp:LearningPath)
        WHERE coalesce(r.status, 'active') IN ['active', 'in_progress']
        RETURN lp
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        paths: list[LearningPath] = []
        for record in result.value or []:
            lp_node = record.get("lp")
            if not lp_node:
                continue
            try:
                paths.append(from_neo4j_node(lp_node, LearningPath))
            except DATA_CONVERSION_EXCEPTIONS as e:
                self.logger.warning("Skipping unconvertible LearningPath node: %s", e)
        return Result.ok(paths)

    async def query_completed_learning_paths(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Query UIDs of completed learning paths for a user.

        Reads r.status='completed' on ENROLLED_IN — the state
        UserBackend.complete_learning_path actually writes.
        """
        query = """
        MATCH (u:User {uid: $user_uid})-[r:ENROLLED_IN]->(lp:LearningPath)
        WHERE r.status = 'completed'
        RETURN lp.uid as lp_uid
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    # NOTE: query_learning_preferences removed (SKUEL030 tranche 3) — it walked a
    # HAS_PREFERENCE edge from User to a LearningPreference node, neither of
    # which anything in the repo ever wrote, so it returned None for every user
    # since the day it was written. Its sole caller
    # (PsAdaptiveService._load_learning_preferences) went with it rather than
    # being left to yield a constant None. Capturing real learning preferences
    # is semantic-layer roadmap work, not a repoint.
    #
    # Deliberately written in prose, not Cypher: test_adaptive_mixin_vocabulary
    # scans this module's bracketed edge tokens and now asserts HAS_PREFERENCE
    # is gone, so naming it in Cypher syntax here — even in a comment — would
    # re-trip the guard.
