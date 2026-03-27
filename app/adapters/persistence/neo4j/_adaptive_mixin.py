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

from core.models.type_hints import UserUID
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
        """Find KU UIDs practiced by a completed event via PRACTICES relationship."""
        query = """
        MATCH (event:Event {uid: $event_uid})-[:PRACTICES]->(ku:Entity)
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

    async def semantic_search_chunks(
        self,
        query_embedding: list[float],
        limit: int,
        threshold: float,
        chunk_types: list[str] | None = None,
        ku_uid: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Vector search across ContentChunk nodes for precise RAG retrieval."""
        cypher = """
        CALL db.index.vector.queryNodes(
            'contentchunk_embedding_idx',
            $limit * 2,
            $query_embedding
        ) YIELD node AS chunk, score
        WHERE score >= $threshold
        """
        if chunk_types:
            cypher += " AND chunk.chunk_type IN $chunk_types"
        if ku_uid:
            cypher += """
            AND EXISTS {
                MATCH (chunk)<-[:HAS_CHUNK]-(content:Content {uid: $ku_uid})
            }
            """
        cypher += """
        MATCH (chunk)<-[:HAS_CHUNK]-(content:Content)<-[:HAS_CONTENT]-(ku:Entity)
        RETURN
            chunk.uid as chunk_uid,
            chunk.chunk_type as chunk_type,
            chunk.text as text,
            chunk.context_window as context_window,
            score as similarity_score,
            ku.uid as parent_entity_uid,
            ku.title as parent_ku_title
        ORDER BY score DESC
        LIMIT $limit
        """
        params: dict[str, Any] = {
            "query_embedding": query_embedding,
            "limit": limit,
            "threshold": threshold,
            "chunk_types": chunk_types,
            "ku_uid": ku_uid,
        }
        return await self.execute_query(cypher, params)

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

    async def query_active_learning_paths(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Query user's active/in-progress learning paths."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:ENROLLED_IN]->(lp:Lp)
        WHERE lp.status = 'active' OR lp.status = 'in_progress'
        RETURN lp
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def query_completed_learning_paths(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Query UIDs of completed learning paths for a user."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:COMPLETED]->(lp:Lp)
        RETURN lp.uid as lp_uid
        """
        return await self.execute_query(query, {"user_uid": user_uid})

    async def query_learning_preferences(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Query user's learning preferences node."""
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_PREFERENCE]->(pref:LearningPreference)
        RETURN pref
        LIMIT 1
        """
        return await self.execute_query(query, {"user_uid": user_uid})
