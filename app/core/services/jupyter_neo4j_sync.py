"""
Jupyter-Neo4j-Obsidian Bi-directional Sync Service
====================================================

Enables editing Neo4j content through Jupyter notebooks with
bi-directional sync to Obsidian vault.

Architecture:
- Jupyter edits Neo4j directly
- Changes tracked with versioning
- Sync back to Obsidian markdown files
- Conflict resolution with user control
"""

import hashlib
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from core.models.curriculum import Curriculum as KnowledgeUnit
from core.services.sync_types import SyncStats
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor

# Primary alias
KnowledgeUnitPure = KnowledgeUnit

logger = get_logger("skuel.services.jupyter_neo4j_sync")


class SyncDirection(Enum):
    """Direction of synchronization."""

    OBSIDIAN_TO_NEO4J = "obsidian_to_neo4j"
    NEO4J_TO_OBSIDIAN = "neo4j_to_obsidian"
    BIDIRECTIONAL = "bidirectional"


class ConflictResolution(Enum):
    """Strategies for resolving sync conflicts."""

    NEO4J_WINS = "neo4j_wins"  # Neo4j changes overwrite Obsidian
    OBSIDIAN_WINS = "obsidian_wins"  # Obsidian changes overwrite Neo4j
    MANUAL = "manual"  # User decides
    MERGE = "merge"  # Attempt automatic merge
    NEWER_WINS = "newer_wins"  # Most recent change wins


class JupyterNeo4jSync:
    """
    Manages bi-directional sync between Jupyter-edited Neo4j content
    and Obsidian markdown files.

    Features:
    - Edit Neo4j content via Jupyter notebooks
    - Track changes with content hashing
    - Sync changes back to Obsidian
    - Handle conflicts gracefully
    - Maintain audit trail
    """

    def __init__(
        self,
        executor: "QueryExecutor",
        vault_path: Path,
        conflict_strategy: ConflictResolution = ConflictResolution.MANUAL,
    ) -> None:
        """
        Initialize sync service.

        Args:
            executor: QueryExecutor for database operations,
            vault_path: Path to Obsidian vault,
            conflict_strategy: How to handle conflicts
        """
        self.executor = executor
        self.vault_path = vault_path
        self.conflict_strategy = conflict_strategy
        self.logger = logger

    async def get_content_for_jupyter(self, uid: str) -> Result[dict[str, Any]]:
        """
        Fetch content from Neo4j for editing in Jupyter.

        Returns a dictionary with content and metadata suitable
        for Jupyter notebook editing.

        Current schema (October 2025):
        - version, type, uid, title, content
        - domain, quality_score, complexity
        - tags, prerequisites, enables, related_to

        Args:
            uid: Ku unit UID

        Returns:
            Content formatted for Jupyter editing
        """
        query = """
        MATCH (ku:Entity {uid: $uid})
        OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq)
        OPTIONAL MATCH (ku)-[:ENABLES_KNOWLEDGE]->(enabled)
        OPTIONAL MATCH (ku)-[:RELATED_TO]->(related)
        RETURN ku,
               collect(DISTINCT prereq.uid) as prerequisites,
               collect(DISTINCT enabled.uid) as enables,
               collect(DISTINCT related.uid) as related_to
        """

        result = await self.executor.execute_query(query, {"uid": uid})
        if result.is_error:
            self.logger.error(f"Failed to fetch content for Jupyter: {result.error}")
            return Result.fail(
                Errors.database(operation="fetch_for_jupyter", message=str(result.error))
            )

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.fail(Errors.not_found(resource="Knowledge unit", identifier=uid))

        ku_data = record["ku"]

        # Format for Jupyter editing (current schema)
        jupyter_content = {
            "version": ku_data.get("version", "1.0"),
            "type": ku_data.get("type", "Entity"),
            "uid": ku_data.get("uid"),
            "title": ku_data.get("title"),
            "content": ku_data.get("content", ""),
            "domain": ku_data.get("domain", "personal"),
            "quality_score": ku_data.get("quality_score", 0.85),
            "complexity": ku_data.get("complexity", "basic"),
            "tags": ku_data.get("tags", []),
            "prerequisites": [p for p in record["prerequisites"] if p],
            "enables": [e for e in record["enables"] if e],
            "related_to": [r for r in record["related_to"] if r],
            "edit_timestamp": datetime.now().isoformat(),
        }

        return Result.ok(jupyter_content)

    async def save_from_jupyter(
        self, uid: str, edited_content: dict[str, Any], editor: str = "jupyter"
    ) -> Result[dict[str, Any]]:
        """
        Save edited content from Jupyter back to Neo4j.

        Tracks changes and prepares for Obsidian sync.

        Current schema (October 2025):
        - version, type, uid, title, content
        - domain, quality_score, complexity
        - tags, prerequisites, enables, related_to

        Args:
            uid: Ku unit UID,
            edited_content: Content edited in Jupyter,
            editor: Editor identifier

        Returns:
            Save result with conflict information if any
        """
        try:
            # Calculate new content hash
            content = edited_content.get("content", "")
            new_hash = hashlib.sha256(content.encode()).hexdigest()[:8]

            # Check for conflicts
            conflict_check = await self._check_for_conflicts(uid, new_hash)
            if conflict_check.is_error:
                return Result.fail(conflict_check.expect_error())

            # Update Neo4j (current schema)
            update_query = """
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
            """

            update_result = await self.executor.execute_query(
                update_query,
                {
                    "uid": uid,
                    "title": edited_content.get("title"),
                    "word_count": len(content.split()) if content else 0,
                    "domain": edited_content.get("domain", "personal"),
                    "complexity": edited_content.get("complexity", "basic"),
                    "quality_score": edited_content.get("quality_score", 0.85),
                    "tags": edited_content.get("tags", []),
                    "content_hash": new_hash,
                    "editor": editor,
                },
            )

            if update_result.is_error:
                return Result.fail(
                    Errors.database(
                        operation="save_from_jupyter", message="Failed to update knowledge unit"
                    )
                )

            records = update_result.value or []
            if not records:
                return Result.fail(
                    Errors.database(
                        operation="save_from_jupyter", message="Failed to update knowledge unit"
                    )
                )

            # Update relationships
            await self._update_relationships(
                uid,
                edited_content.get("prerequisites", []),
                edited_content.get("enables", []),
                edited_content.get("related_to", []),
            )

            # Track change for sync
            await self._track_change(uid, "jupyter_edit", new_hash)

            return Result.ok(
                {
                    "uid": uid,
                    "content_hash": new_hash,
                    "updated_at": datetime.now().isoformat(),
                    "needs_sync": True,
                }
            )

        except Exception as e:
            self.logger.error(f"Failed to save from Jupyter: {e}")
            return Result.fail(Errors.database(operation="save_from_jupyter", message=str(e)))

    async def sync_to_obsidian(
        self, uid: str | None = None, force: bool = False
    ) -> Result[SyncStats]:
        """
        Sync Neo4j changes back to Obsidian markdown files.

        Args:
            uid: Specific UID to sync, or None for all pending,
            force: Force sync even without changes

        Returns:
            Sync results with statistics (frozen dataclass)
        """
        try:
            # Find items needing sync
            if uid:
                query = "MATCH (ku:Entity {uid: $uid}) RETURN ku"
                params: dict[str, Any] = {"uid": uid}
            else:
                query = """
                MATCH (ku:Entity)
                WHERE ku.needs_obsidian_sync = true OR $force = true
                RETURN ku
                LIMIT 100
                """
                params = {"force": force}

            query_result = await self.executor.execute_query(query, params)
            if query_result.is_error:
                return Result.fail(
                    Errors.integration(
                        service="obsidian_sync",
                        operation="sync_to_obsidian",
                        message=str(query_result.error),
                    )
                )

            records = query_result.value or []

            # Mutable accumulation variables
            synced_count = 0
            conflicts_count = 0
            errors_list: list[dict[str, str]] = []

            for record in records:
                ku_data = record["ku"]
                sync_result = await self._sync_single_to_obsidian(ku_data)

                if sync_result.is_ok:
                    synced_count += 1
                    # Mark as synced
                    await self._mark_synced(ku_data["uid"])
                else:
                    if "conflict" in str(sync_result.error):
                        conflicts_count += 1
                    errors_list.append({"uid": ku_data["uid"], "error": str(sync_result.error)})

            # Build immutable result
            stats = SyncStats(
                total=len(records),
                synced=synced_count,
                conflicts=conflicts_count,
                errors=errors_list,
            )

            return Result.ok(stats)

        except Exception as e:
            self.logger.error(f"Failed to sync to Obsidian: {e}")
            return Result.fail(
                Errors.integration(
                    service="obsidian_sync", operation="sync_to_obsidian", message=str(e)
                )
            )

    async def _sync_single_to_obsidian(self, ku_data: dict[str, Any]) -> Result[Path]:
        """
        Sync a single knowledge unit to Obsidian.

        Current schema (October 2025): Exports to YAML files

        Args:
            ku_data: Ku unit data from Neo4j

        Returns:
            Path to synchronized file
        """
        try:
            # Fetch relationships from Neo4j
            uid = ku_data.get("uid")
            if not uid:
                return Result.fail(
                    Errors.validation(message="Knowledge unit UID is required", field="uid")
                )
            rel_query = """
            MATCH (ku:Entity {uid: $uid})
            OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq)
            OPTIONAL MATCH (ku)-[:ENABLES_KNOWLEDGE]->(enabled)
            OPTIONAL MATCH (ku)-[:RELATED_TO]->(related)
            RETURN collect(DISTINCT prereq.uid) as prerequisites,
                   collect(DISTINCT enabled.uid) as enables,
                   collect(DISTINCT related.uid) as related_to
            """
            rel_result = await self.executor.execute_query(rel_query, {"uid": uid})
            if rel_result.is_ok:
                rel_records = rel_result.value or []
                record = rel_records[0] if rel_records else None

                if record:
                    ku_data["prerequisites"] = [p for p in record["prerequisites"] if p]
                    ku_data["enables"] = [e for e in record["enables"] if e]
                    ku_data["related_to"] = [r for r in record["related_to"] if r]

            # Determine file path (YAML extension)
            domain = ku_data.get("domain", "personal")
            filename = uid.replace(":", "_") + ".yaml"
            file_path = self.vault_path / "domains" / domain / filename

            # Check for conflicts
            if file_path.exists():
                existing_content = file_path.read_text()
                existing_hash = hashlib.sha256(existing_content.encode()).hexdigest()[:8]

                if existing_hash != ku_data.get("last_obsidian_hash"):
                    # Conflict detected
                    return await self._handle_conflict(ku_data, file_path, existing_content)

            # Generate YAML content
            yaml_content = self._generate_markdown(ku_data)

            # Write to file
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(yaml_content)

            # Update hash tracking
            await self._update_obsidian_hash(
                ku_data["uid"], hashlib.sha256(yaml_content.encode()).hexdigest()[:8]
            )

            self.logger.info(f"Synced {ku_data['uid']} to {file_path}")
            return Result.ok(file_path)

        except Exception as e:
            self.logger.error(f"Failed to sync single item: {e}")
            return Result.fail(Errors.system(message=f"Sync failed: {e}", operation="sync_single"))

    def _generate_markdown(self, ku_data: dict[str, Any]) -> str:
        """
        Generate YAML content from knowledge unit data.

        Current schema (October 2025):
        - version, type, uid, title, content
        - domain, quality_score, complexity
        - tags, prerequisites, enables, related_to

        Args:
            ku_data: Ku unit data

        Returns:
            Formatted YAML string
        """
        # Build YAML structure matching current schema
        yaml_data = {
            "version": ku_data.get("version", "1.0"),
            "type": ku_data.get("type", "Entity"),
            "uid": ku_data.get("uid"),
            "title": ku_data.get("title"),
            "content": ku_data.get("content", ""),
            "domain": ku_data.get("domain", "personal"),
            "quality_score": ku_data.get("quality_score", 0.85),
            "complexity": ku_data.get("complexity", "basic"),
            "tags": ku_data.get("tags", []),
            "prerequisites": ku_data.get("prerequisites", []),
            "enables": ku_data.get("enables", []),
            "related_to": ku_data.get("related_to", []),
        }

        # Generate YAML
        return yaml.dump(yaml_data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    async def _check_for_conflicts(self, uid: str, _new_hash: str) -> Result[bool]:
        """
        Check for edit conflicts.

        Args:
            uid: Ku unit UID,
            new_hash: New content hash

        Returns:
            True if no conflicts, error if conflicts exist
        """
        query = """
        MATCH (ku:Entity {uid: $uid})
        RETURN ku.content_hash as current_hash,
               ku.needs_obsidian_sync as pending_sync
        """

        result = await self.executor.execute_query(query, {"uid": uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        record = records[0] if records else None

        if record and record["pending_sync"]:
            return Result.fail(
                Errors.business(
                    rule="sync_conflict",
                    message="Unsynchronized changes exist",
                    uid=uid,
                    pending_sync=True,
                )
            )

        return Result.ok(True)

    async def _handle_conflict(
        self, ku_data: dict[str, Any], file_path: Path, _existing_content: str
    ) -> Result[Path]:
        """
        Handle sync conflicts based on strategy.

        Args:
            ku_data: Neo4j knowledge unit data,
            file_path: Obsidian file path (YAML),
            existing_content: Current Obsidian content

        Returns:
            Result of conflict resolution
        """
        if self.conflict_strategy == ConflictResolution.NEO4J_WINS:
            # Neo4j overwrites Obsidian
            yaml_content = self._generate_markdown(ku_data)
            file_path.write_text(yaml_content)
            return Result.ok(file_path)

        elif self.conflict_strategy == ConflictResolution.OBSIDIAN_WINS:
            # Skip sync, Obsidian keeps its version
            return Result.fail(
                Errors.business(
                    rule="conflict_resolution", message="Conflict: Obsidian version preserved"
                )
            )

        elif self.conflict_strategy == ConflictResolution.NEWER_WINS:
            # Compare timestamps
            neo4j_time = ku_data.get("last_modified")
            obsidian_time = file_path.stat().st_mtime

            if neo4j_time is not None and neo4j_time > obsidian_time:
                yaml_content = self._generate_markdown(ku_data)
                file_path.write_text(yaml_content)
                return Result.ok(file_path)
            else:
                return Result.fail(
                    Errors.business(
                        rule="conflict_resolution", message="Conflict: Obsidian version is newer"
                    )
                )

        else:  # MANUAL or MERGE
            # Create conflict file for manual resolution
            conflict_path = file_path.with_suffix(".conflict.yaml")
            yaml_content = self._generate_markdown(ku_data)
            conflict_path.write_text(yaml_content)

            return Result.fail(
                Errors.business(
                    rule="conflict_resolution",
                    message=f"Conflict: Manual resolution required. See {conflict_path}",
                    conflict_file=str(conflict_path),
                )
            )

    async def _update_relationships(
        self, uid: str, prerequisites: list[str], enables: list[str], related_to: list[str]
    ) -> None:
        """
        Update knowledge unit relationships.

        Args:
            uid: Ku unit UID,
            prerequisites: List of prerequisite UIDs,
            enables: List of enabled UIDs,
            related_to: List of related UIDs
        """
        # Clear existing relationships
        await self.executor.execute_query(
            """
            MATCH (ku:Entity {uid: $uid})-[r:REQUIRES_KNOWLEDGE|ENABLES_KNOWLEDGE|RELATED_TO]->()
            DETACH DELETE r
            """,
            {"uid": uid},
        )

        # Create prerequisite relationships
        for prereq_uid in prerequisites:
            await self.executor.execute_query(
                """
                MATCH (ku:Entity {uid: $uid})
                MATCH (prereq:Entity {uid: $prereq_uid})
                CREATE (ku)-[:REQUIRES_KNOWLEDGE]->(prereq)
                """,
                {"uid": uid, "prereq_uid": prereq_uid},
            )

        # Create enables relationships
        for enable_uid in enables:
            await self.executor.execute_query(
                """
                MATCH (ku:Entity {uid: $uid})
                MATCH (enabled:Entity {uid: $enable_uid})
                CREATE (ku)-[:ENABLES_KNOWLEDGE]->(enabled)
                """,
                {"uid": uid, "enable_uid": enable_uid},
            )

        # Create related_to relationships
        for related_uid in related_to:
            await self.executor.execute_query(
                """
                MATCH (ku:Entity {uid: $uid})
                MATCH (related:Entity {uid: $related_uid})
                CREATE (ku)-[:RELATED_TO]->(related)
                """,
                {"uid": uid, "related_uid": related_uid},
            )

    async def _track_change(self, uid: str, change_type: str, content_hash: str) -> None:
        """Track changes for audit and sync purposes."""
        query = """
        CREATE (c:ChangeLog {
            uid: $uid,
            change_type: $change_type,
            content_hash: $content_hash,
            timestamp: datetime()
        })
        """
        result = await self.executor.execute_query(
            query, {"uid": uid, "change_type": change_type, "content_hash": content_hash}
        )
        if result.is_error:
            self.logger.warning(f"Failed to track change for {uid}: {result.error}")

    async def _mark_synced(self, uid: str) -> None:
        """Mark a knowledge unit as synced."""
        query = """
        MATCH (ku:Entity {uid: $uid})
        SET ku.needs_obsidian_sync = false,
            ku.last_synced = datetime()
        """
        result = await self.executor.execute_query(query, {"uid": uid})
        if result.is_error:
            self.logger.warning(f"Failed to mark {uid} as synced: {result.error}")

    async def _update_obsidian_hash(self, uid: str, hash_value: str) -> None:
        """Update the Obsidian content hash for tracking."""
        query = """
        MATCH (ku:Entity {uid: $uid})
        SET ku.last_obsidian_hash = $hash
        """
        result = await self.executor.execute_query(query, {"uid": uid, "hash": hash_value})
        if result.is_error:
            self.logger.warning(f"Failed to update obsidian hash for {uid}: {result.error}")
