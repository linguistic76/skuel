"""
Jupyter Sync Backend
=====================

Backend for Jupyter-Neo4j-Obsidian bi-directional sync persistence.
Does NOT extend UniversalNeo4jBackend — takes a Neo4jQueryExecutor directly.

Migrates 12 execute_query calls from JupyterNeo4jSync.

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


class JupyterSyncBackend:
    """Backend for Jupyter-Neo4j sync persistence operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    # ========================================================================
    # READ — Fetch content and relationships
    # ========================================================================

    async def get_content_with_relationships(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Fetch entity content with prerequisite/enables/related relationships."""
        return await self._executor.execute_query(
            """
            MATCH (ku:Entity {uid: $uid})
            OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq)
            OPTIONAL MATCH (ku)-[:ENABLES_KNOWLEDGE]->(enabled)
            OPTIONAL MATCH (ku)-[:RELATED_TO]->(related)
            RETURN ku,
                   collect(DISTINCT prereq.uid) as prerequisites,
                   collect(DISTINCT enabled.uid) as enables,
                   collect(DISTINCT related.uid) as related_to
            """,
            {"uid": uid},
        )

    async def get_conflict_state(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Check entity conflict state (content hash + pending sync flag)."""
        return await self._executor.execute_query(
            """
            MATCH (ku:Entity {uid: $uid})
            RETURN ku.content_hash as current_hash,
                   ku.needs_obsidian_sync as pending_sync
            """,
            {"uid": uid},
        )

    async def get_entities_needing_sync(
        self, uid: str | None, force: bool
    ) -> Result[list[dict[str, Any]]]:
        """Get entities that need Obsidian sync."""
        if uid:
            return await self._executor.execute_query(
                "MATCH (ku:Entity {uid: $uid}) RETURN ku",
                {"uid": uid},
            )
        return await self._executor.execute_query(
            """
            MATCH (ku:Entity)
            WHERE ku.needs_obsidian_sync = true OR $force = true
            RETURN ku
            LIMIT 100
            """,
            {"force": force},
        )

    async def get_entity_relationships(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Fetch knowledge relationships for a single entity."""
        return await self._executor.execute_query(
            """
            MATCH (ku:Entity {uid: $uid})
            OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq)
            OPTIONAL MATCH (ku)-[:ENABLES_KNOWLEDGE]->(enabled)
            OPTIONAL MATCH (ku)-[:RELATED_TO]->(related)
            RETURN collect(DISTINCT prereq.uid) as prerequisites,
                   collect(DISTINCT enabled.uid) as enables,
                   collect(DISTINCT related.uid) as related_to
            """,
            {"uid": uid},
        )

    # ========================================================================
    # WRITE — Update content and metadata
    # ========================================================================

    async def update_entity_from_jupyter(
        self, params: dict[str, Any]
    ) -> Result[list[dict[str, Any]]]:
        """Update entity properties from Jupyter-edited content."""
        return await self._executor.execute_query(
            """
            MATCH (ku:Entity {uid: $uid})
            SET ku.title = $title,
                ku.word_count = $word_count,
                ku.domain = $domain,
                ku.complexity = $complexity,
                ku.quality_score = $quality_score,
                ku.tags = $tags,
                ku.content_hash = $content_hash,
                ku.last_modified = datetime(),
                ku.last_editor = $editor,
                ku.needs_obsidian_sync = true
            RETURN ku
            """,
            params,
        )

    async def replace_relationships(
        self, uid: str, prerequisites: list[str], enables: list[str], related_to: list[str]
    ) -> Result[list[dict[str, Any]]]:
        """Replace all knowledge relationships atomically.

        Deletes existing REQUIRES_KNOWLEDGE, ENABLES_KNOWLEDGE, RELATED_TO
        relationships and creates new ones from the provided lists.
        """
        # Delete existing relationships
        await self._executor.execute_query(
            """
            MATCH (ku:Entity {uid: $uid})-[r:REQUIRES_KNOWLEDGE|ENABLES_KNOWLEDGE|RELATED_TO]->()
            DELETE r
            """,
            {"uid": uid},
        )

        # Create prerequisite relationships
        for prereq_uid in prerequisites:
            await self._executor.execute_query(
                """
                MATCH (ku:Entity {uid: $uid})
                MATCH (prereq:Entity {uid: $prereq_uid})
                CREATE (ku)-[:REQUIRES_KNOWLEDGE]->(prereq)
                """,
                {"uid": uid, "prereq_uid": prereq_uid},
            )

        # Create enables relationships
        for enable_uid in enables:
            await self._executor.execute_query(
                """
                MATCH (ku:Entity {uid: $uid})
                MATCH (enabled:Entity {uid: $enable_uid})
                CREATE (ku)-[:ENABLES_KNOWLEDGE]->(enabled)
                """,
                {"uid": uid, "enable_uid": enable_uid},
            )

        # Create related_to relationships
        for related_uid in related_to:
            await self._executor.execute_query(
                """
                MATCH (ku:Entity {uid: $uid})
                MATCH (related:Entity {uid: $related_uid})
                CREATE (ku)-[:RELATED_TO]->(related)
                """,
                {"uid": uid, "related_uid": related_uid},
            )

        return Result.ok([])

    async def track_change(
        self, uid: str, change_type: str, content_hash: str
    ) -> Result[list[dict[str, Any]]]:
        """Create a ChangeLog node for audit purposes."""
        return await self._executor.execute_query(
            """
            CREATE (c:ChangeLog {
                uid: $uid,
                change_type: $change_type,
                content_hash: $content_hash,
                timestamp: datetime()
            })
            """,
            {"uid": uid, "change_type": change_type, "content_hash": content_hash},
        )

    async def mark_synced(self, uid: str) -> Result[list[dict[str, Any]]]:
        """Mark an entity as synced (clear needs_obsidian_sync flag)."""
        return await self._executor.execute_query(
            """
            MATCH (ku:Entity {uid: $uid})
            SET ku.needs_obsidian_sync = false,
                ku.last_synced = datetime()
            """,
            {"uid": uid},
        )

    async def update_obsidian_hash(self, uid: str, hash_value: str) -> Result[list[dict[str, Any]]]:
        """Update the Obsidian content hash for conflict tracking."""
        return await self._executor.execute_query(
            """
            MATCH (ku:Entity {uid: $uid})
            SET ku.last_obsidian_hash = $hash
            """,
            {"uid": uid, "hash": hash_value},
        )
