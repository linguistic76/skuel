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
from core.utils.exception_types import FILE_IO_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

_SYNC_EXCEPTIONS = (*NEO4J_EXCEPTIONS, *FILE_IO_EXCEPTIONS)

if TYPE_CHECKING:
    from core.ports.jupyter_sync_protocols import JupyterSyncBackendOperations

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
        backend: "JupyterSyncBackendOperations",
        vault_path: Path,
        conflict_strategy: ConflictResolution = ConflictResolution.MANUAL,
    ) -> None:
        """
        Initialize sync service.

        Args:
            backend: Typed backend for sync persistence,
            vault_path: Path to Obsidian vault,
            conflict_strategy: How to handle conflicts
        """
        self.backend = backend
        self.vault_path = vault_path
        self.conflict_strategy = conflict_strategy
        self.logger = logger

    async def get_content_for_jupyter(self, uid: str) -> Result[dict[str, Any]]:
        """
        Fetch content from Neo4j for editing in Jupyter.

        Returns a dictionary with content and metadata suitable
        for Jupyter notebook editing.

        Args:
            uid: Ku unit UID

        Returns:
            Content formatted for Jupyter editing
        """
        result = await self.backend.get_content_with_relationships(uid)
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
            query_result = await self.backend.get_entities_needing_sync(uid, force)
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
                    mark_result = await self.backend.mark_synced(ku_data["uid"])
                    if mark_result.is_error:
                        self.logger.warning(
                            f"Failed to mark {ku_data['uid']} as synced: {mark_result.error}"
                        )
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

        except _SYNC_EXCEPTIONS as e:
            self.logger.error(f"Failed to sync to Obsidian: {e}")
            return Result.fail(
                Errors.integration(
                    service="obsidian_sync", operation="sync_to_obsidian", message=str(e)
                )
            )
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Failed to sync to Obsidian: {e}")
            return Result.fail(
                Errors.integration(
                    service="obsidian_sync", operation="sync_to_obsidian", message=str(e)
                )
            )

    async def _sync_single_to_obsidian(self, ku_data: dict[str, Any]) -> Result[Path]:
        """
        Sync a single knowledge unit to Obsidian.

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
            rel_result = await self.backend.get_entity_relationships(uid)
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
                    return self._handle_conflict(ku_data, file_path, existing_content)

            # Generate YAML content
            yaml_content = self._generate_markdown(ku_data)

            # Write to file
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(yaml_content)

            # Update hash tracking
            hash_result = await self.backend.update_obsidian_hash(
                ku_data["uid"], hashlib.sha256(yaml_content.encode()).hexdigest()[:8]
            )
            if hash_result.is_error:
                self.logger.warning(
                    f"Failed to update obsidian hash for {ku_data['uid']}: {hash_result.error}"
                )

            self.logger.info(f"Synced {ku_data['uid']} to {file_path}")
            return Result.ok(file_path)

        except _SYNC_EXCEPTIONS as e:
            self.logger.error(f"Failed to sync single item: {e}")
            return Result.fail(Errors.system(message=f"Sync failed: {e}", operation="sync_single"))
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Failed to sync single item: {e}")
            return Result.fail(Errors.system(message=f"Sync failed: {e}", operation="sync_single"))

    def _generate_markdown(self, ku_data: dict[str, Any]) -> str:
        """
        Generate YAML content from knowledge unit data.

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

    def _handle_conflict(
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
