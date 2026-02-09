"""
Ingestion History Service - Audit Trail for Ingestion Operations
=================================================================

Tracks all ingestion operations in Neo4j for audit trail and history UI.

Graph Model:
    (:IngestionHistory {
        operation_id: "uuid",
        operation_type: "file" | "directory" | "vault" | "bundle",
        started_at: datetime(),
        completed_at: datetime() | null,
        status: "in_progress" | "completed" | "failed",
        user_uid: "user_admin",
        source_path: "/vault/docs",
        total_files: 100,
        successful: 98,
        failed: 2,
        nodes_created: 120,
        nodes_updated: 45,
        relationships_created: 200
    })-[:HAD_ERROR]->(:IngestionError {
        file: "/vault/bad.md",
        error: "Missing required field",
        stage: "validation"
    })

Usage:
    service = IngestionHistoryService(driver)
    operation_id = await service.create_entry("directory", "user_admin", "/vault/docs")
    # ... perform ingestion ...
    await service.update_entry(operation_id, "completed", stats, errors)
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from neo4j import AsyncDriver

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.ingestion.ingestion_history")


@dataclass
class IngestionHistoryEntry:
    """Record of an ingestion operation."""

    operation_id: str
    operation_type: str  # "file" | "directory" | "vault" | "bundle"
    started_at: datetime
    completed_at: datetime | None
    status: str  # "in_progress" | "completed" | "failed"
    user_uid: str
    source_path: str
    stats: dict[str, Any]  # IngestionStats/IncrementalStats as dict
    errors: list[dict[str, Any]]  # IngestionError dicts


class IngestionHistoryService:
    """Tracks ingestion operations in Neo4j for audit trail."""

    def __init__(self, driver: AsyncDriver) -> None:
        """
        Initialize ingestion history service.

        Args:
            driver: Neo4j async driver
        """
        self.driver = driver
        self.logger = logger

    async def ensure_constraints(self) -> None:
        """Ensure Neo4j constraints for IngestionHistory nodes."""
        constraint_query = """
        CREATE CONSTRAINT IF NOT EXISTS
        FOR (ih:IngestionHistory)
        REQUIRE ih.operation_id IS UNIQUE
        """
        await self.driver.execute_query(constraint_query, database_="neo4j")
        self.logger.info("IngestionHistory constraints ensured")

    async def create_entry(
        self,
        operation_type: str,
        user_uid: str,
        source_path: str,
    ) -> Result[str]:
        """
        Create ingestion history node and return operation_id.

        Args:
            operation_type: Type of operation ("file", "directory", "vault", "bundle")
            user_uid: Admin user who triggered the ingestion
            source_path: Source path being ingested

        Returns:
            Result with operation_id (UUID)
        """
        operation_id = str(uuid.uuid4())
        started_at = datetime.now()

        query = """
        CREATE (ih:IngestionHistory {
            operation_id: $operation_id,
            operation_type: $operation_type,
            started_at: datetime($started_at),
            status: 'in_progress',
            user_uid: $user_uid,
            source_path: $source_path
        })
        RETURN ih.operation_id AS operation_id
        """

        try:
            await self.driver.execute_query(
                query,
                {
                    "operation_id": operation_id,
                    "operation_type": operation_type,
                    "started_at": started_at.isoformat(),
                    "user_uid": user_uid,
                    "source_path": source_path,
                },
                database_="neo4j",
            )

            self.logger.info(f"Created ingestion history entry: {operation_id}")
            return Result.ok(operation_id)

        except Exception as e:
            self.logger.error(f"Failed to create ingestion history entry: {e}")
            return Result.fail(
                Errors.database(
                    "create_ingestion_history",
                    "Failed to create ingestion history entry",
                    details={"error": str(e)},
                )
            )

    async def update_entry(
        self,
        operation_id: str,
        status: str,
        stats: dict[str, Any],
        errors: list[dict[str, Any]] | None = None,
    ) -> Result[None]:
        """
        Update ingestion history with results.

        Args:
            operation_id: UUID of the ingestion operation
            status: Final status ("completed" or "failed")
            stats: Statistics from IngestionStats/IncrementalStats (as dict)
            errors: List of error dicts (optional)

        Returns:
            Result indicating success or failure
        """
        completed_at = datetime.now()

        query = """
        MATCH (ih:IngestionHistory {operation_id: $operation_id})
        SET ih.completed_at = datetime($completed_at),
            ih.status = $status,
            ih.total_files = $total_files,
            ih.successful = $successful,
            ih.failed = $failed,
            ih.nodes_created = $nodes_created,
            ih.nodes_updated = $nodes_updated,
            ih.relationships_created = $relationships_created,
            ih.duration_seconds = $duration_seconds
        """

        params: dict[str, Any] = {
            "operation_id": operation_id,
            "completed_at": completed_at.isoformat(),
            "status": status,
            "total_files": stats.get("total_files", 0),
            "successful": stats.get("successful", 0),
            "failed": stats.get("failed", 0),
            "nodes_created": stats.get("nodes_created", 0),
            "nodes_updated": stats.get("nodes_updated", 0),
            "relationships_created": stats.get("relationships_created", 0),
            "duration_seconds": stats.get("duration_seconds", 0.0),
        }

        try:
            await self.driver.execute_query(query, params, database_="neo4j")

            # Create error nodes if any
            if errors:
                await self._create_error_nodes(operation_id, errors)

            self.logger.info(f"Updated ingestion history entry: {operation_id} (status: {status})")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Failed to update ingestion history entry: {e}")
            return Result.fail(
                Errors.database(
                    "update_ingestion_history",
                    "Failed to update ingestion history entry",
                    details={"error": str(e)},
                )
            )

    async def _create_error_nodes(
        self,
        operation_id: str,
        errors: list[dict[str, Any]],
    ) -> None:
        """
        Create error nodes and link them to ingestion history.

        Args:
            operation_id: UUID of the ingestion operation
            errors: List of error dicts
        """
        query = """
        MATCH (ih:IngestionHistory {operation_id: $operation_id})
        UNWIND $errors AS error
        CREATE (e:IngestionError {
            file: error.file,
            error: error.error,
            stage: error.stage,
            error_type: error.error_type,
            entity_type: error.entity_type,
            suggestion: error.suggestion
        })
        CREATE (ih)-[:HAD_ERROR]->(e)
        """

        try:
            await self.driver.execute_query(
                query,
                {"operation_id": operation_id, "errors": errors},
                database_="neo4j",
            )
            self.logger.info(f"Created {len(errors)} error nodes for ingestion {operation_id}")
        except Exception as e:
            self.logger.error(f"Failed to create error nodes: {e}")

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[IngestionHistoryEntry]]:
        """
        Retrieve ingestion history (paginated).

        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            Result with list of IngestionHistoryEntry objects
        """
        query = """
        MATCH (ih:IngestionHistory)
        OPTIONAL MATCH (ih)-[:HAD_ERROR]->(e:IngestionError)
        WITH ih, COLLECT(e) AS errors
        RETURN ih, errors
        ORDER BY ih.started_at DESC
        SKIP $offset
        LIMIT $limit
        """

        try:
            result = await self.driver.execute_query(
                query,
                {"limit": limit, "offset": offset},
                database_="neo4j",
            )

            entries: list[IngestionHistoryEntry] = []
            for record in result.records:
                ih = record["ih"]
                errors = record["errors"]

                # Convert Neo4j datetime to Python datetime
                started_at = ih["started_at"]
                completed_at = ih.get("completed_at")

                # Convert error nodes to dicts
                error_dicts = [
                    {
                        "file": e["file"],
                        "error": e["error"],
                        "stage": e["stage"],
                        "error_type": e.get("error_type", "unknown"),
                        "entity_type": e.get("entity_type"),
                        "suggestion": e.get("suggestion"),
                    }
                    for e in errors
                    if e is not None
                ]

                # Build stats dict
                stats_dict = {
                    "total_files": ih.get("total_files", 0),
                    "successful": ih.get("successful", 0),
                    "failed": ih.get("failed", 0),
                    "nodes_created": ih.get("nodes_created", 0),
                    "nodes_updated": ih.get("nodes_updated", 0),
                    "relationships_created": ih.get("relationships_created", 0),
                    "duration_seconds": ih.get("duration_seconds", 0.0),
                }

                entry = IngestionHistoryEntry(
                    operation_id=ih["operation_id"],
                    operation_type=ih["operation_type"],
                    started_at=started_at,
                    completed_at=completed_at,
                    status=ih["status"],
                    user_uid=ih["user_uid"],
                    source_path=ih["source_path"],
                    stats=stats_dict,
                    errors=error_dicts,
                )
                entries.append(entry)

            return Result.ok(entries)

        except Exception as e:
            self.logger.error(f"Failed to retrieve ingestion history: {e}")
            return Result.fail(
                Errors.database(
                    "get_ingestion_history",
                    "Failed to retrieve ingestion history",
                    details={"error": str(e)},
                )
            )

    async def get_entry(self, operation_id: str) -> Result[IngestionHistoryEntry | None]:
        """
        Get specific ingestion operation by ID.

        Args:
            operation_id: UUID of the ingestion operation

        Returns:
            Result with IngestionHistoryEntry or None if not found
        """
        query = """
        MATCH (ih:IngestionHistory {operation_id: $operation_id})
        OPTIONAL MATCH (ih)-[:HAD_ERROR]->(e:IngestionError)
        WITH ih, COLLECT(e) AS errors
        RETURN ih, errors
        """

        try:
            result = await self.driver.execute_query(
                query,
                {"operation_id": operation_id},
                database_="neo4j",
            )

            if not result.records:
                return Result.ok(None)

            record = result.records[0]
            ih = record["ih"]
            errors = record["errors"]

            # Convert Neo4j datetime to Python datetime
            started_at = ih["started_at"]
            completed_at = ih.get("completed_at")

            # Convert error nodes to dicts
            error_dicts = [
                {
                    "file": e["file"],
                    "error": e["error"],
                    "stage": e["stage"],
                    "error_type": e.get("error_type", "unknown"),
                    "entity_type": e.get("entity_type"),
                    "suggestion": e.get("suggestion"),
                }
                for e in errors
                if e is not None
            ]

            # Build stats dict
            stats_dict = {
                "total_files": ih.get("total_files", 0),
                "successful": ih.get("successful", 0),
                "failed": ih.get("failed", 0),
                "nodes_created": ih.get("nodes_created", 0),
                "nodes_updated": ih.get("nodes_updated", 0),
                "relationships_created": ih.get("relationships_created", 0),
                "duration_seconds": ih.get("duration_seconds", 0.0),
            }

            entry = IngestionHistoryEntry(
                operation_id=ih["operation_id"],
                operation_type=ih["operation_type"],
                started_at=started_at,
                completed_at=completed_at,
                status=ih["status"],
                user_uid=ih["user_uid"],
                source_path=ih["source_path"],
                stats=stats_dict,
                errors=error_dicts,
            )

            return Result.ok(entry)

        except Exception as e:
            self.logger.error(f"Failed to retrieve ingestion entry: {e}")
            return Result.fail(
                Errors.database(
                    "get_ingestion_entry",
                    "Failed to retrieve ingestion entry",
                    details={"error": str(e)},
                )
            )

    async def get_total_count(self) -> Result[int]:
        """
        Get total count of ingestion history entries.

        Returns:
            Result with total count
        """
        query = """
        MATCH (ih:IngestionHistory)
        RETURN COUNT(ih) AS total
        """

        try:
            result = await self.driver.execute_query(query, database_="neo4j")
            total = result.records[0]["total"] if result.records else 0
            return Result.ok(total)

        except Exception as e:
            self.logger.error(f"Failed to get ingestion history count: {e}")
            return Result.fail(
                Errors.database(
                    "get_ingestion_count",
                    "Failed to get ingestion history count",
                    details={"error": str(e)},
                )
            )


__all__ = ["IngestionHistoryEntry", "IngestionHistoryService"]
