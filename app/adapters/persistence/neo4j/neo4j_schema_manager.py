"""
Neo4j Schema Manager
====================

Auto-creates Neo4j indexes and constraints from model field metadata.
When you add `field(metadata={'index': True})` to a model field,
the index is automatically created in Neo4j.

Key Features:
- Auto-creates indexes from field metadata
- Supports unique constraints
- Syncs schema on application startup
- Idempotent (safe to run multiple times)
- Reports created/existing indexes
"""

import re
from dataclasses import fields, is_dataclass
from typing import Any, TypeVar

from neo4j import AsyncDriver

from core.models.enums.neo_labels import NeoLabel
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

T = TypeVar("T")
logger = get_logger(__name__)

# =============================================================================
# DDL Injection Guards
# =============================================================================

_VALID_NEO4J_LABELS: frozenset[str] = frozenset(v.value for v in NeoLabel)
_VALID_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_VALID_SIMILARITY = frozenset({"cosine", "euclidean"})


def _validate_label(label: str) -> None:
    if label not in _VALID_NEO4J_LABELS:
        raise ValueError(f"Invalid Neo4j label: {label!r}")


def _validate_identifier(name: str, context: str = "field") -> None:
    if not _VALID_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid {context} name: {name!r}")


def _validate_similarity(similarity: str) -> None:
    if similarity not in _VALID_SIMILARITY:
        raise ValueError(
            f"Invalid similarity function: {similarity!r} (must be cosine or euclidean)"
        )


class Neo4jSchemaManager:
    """
    Manages Neo4j schema (indexes, constraints) based on model metadata.

    Usage:
        schema_manager = Neo4jSchemaManager(driver)
        await schema_manager.sync_indexes(TaskPure, "Task")
        # Creates indexes for all fields with metadata={'index': True}
    """

    def __init__(self, driver: AsyncDriver) -> None:
        """
        Initialize schema manager.

        Args:
            driver: Neo4j async driver
        """
        self.driver = driver
        self.logger = get_logger("skuel.schema_manager")

    async def sync_indexes(
        self, entity_class: type[T], label: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Sync indexes for a model class based on field metadata.

        Scans model fields for metadata={'index': True} and creates
        corresponding Neo4j indexes.

        Args:
            entity_class: Domain model class (must be dataclass),
            label: Neo4j label (defaults to class name)

        Returns:
            Result with dict of created/existing indexes,

        Example:
            @dataclass(frozen=True)
            class Task:
                uid: str = field(metadata={'index': True, 'unique': True})
                priority: Priority = field(metadata={'index': True})
                title: str  # No index

            await schema_manager.sync_indexes(Task, "Task")
            # Creates:
            # - UNIQUE constraint on uid
            # - Index on priority
        """
        if not is_dataclass(entity_class):
            return Result.fail(
                Errors.validation(
                    f"Entity class must be a dataclass, got {entity_class}", field="entity_class"
                )
            )

        label = label or entity_class.__name__
        results = {"created": [], "existing": [], "failed": []}

        try:
            for field_info in fields(entity_class):
                # Check if field has index metadata
                if not field_info.metadata.get("index"):
                    continue

                field_name = field_info.name
                is_unique = field_info.metadata.get("unique", False)

                if is_unique:
                    # Create unique constraint
                    result = await self._create_unique_constraint(label, field_name)
                else:
                    # Create regular index
                    result = await self._create_index(label, field_name)

                if result.is_ok:
                    status = result.value
                    if status == "created":
                        results["created"].append(f"{label}.{field_name}")
                        (self.logger.info(f"Created index: {label}.{field_name}"),)
                    else:
                        results["existing"].append(f"{label}.{field_name}")
                        (self.logger.debug(f"Index already exists: {label}.{field_name}"),)
                else:
                    results["failed"].append(f"{label}.{field_name}")
                    self.logger.error(
                        f"Failed to create index: {label}.{field_name}: {result.error}"
                    )

            return Result.ok(results)

        except Exception as e:
            self.logger.error(f"Schema sync failed for {label}: {e}")
            return Result.fail(Errors.system(f"Schema sync failed: {e}", operation="sync_indexes"))

    async def _create_index(self, label: str, field_name: str) -> Result[str]:
        """
        Create a regular index on a field.

        Args:
            label: Neo4j label,
            field_name: Field to index

        Returns:
            Result with 'created' or 'existing'
        """
        _validate_label(label)
        _validate_identifier(field_name)
        index_name = f"{label}_{field_name}_idx"

        try:
            # Neo4j 5.x syntax - IF NOT EXISTS makes this idempotent
            query = f"""
            CREATE INDEX {index_name} IF NOT EXISTS
            FOR (n:{label}) ON (n.{field_name})
            """

            async with self.driver.session() as session:
                await session.run(query)

            # Check if it was just created or already existed
            # (IF NOT EXISTS doesn't tell us, so we assume created for now)
            return Result.ok("created")

        except Exception as e:
            self.logger.error(f"Failed to create index {index_name}: {e}")
            return Result.fail(
                Errors.database(
                    operation="create_index", message=f"Index creation failed: {e}", entity=label
                )
            )

    async def _create_unique_constraint(self, label: str, field_name: str) -> Result[str]:
        """
        Create a unique constraint on a field.

        Args:
            label: Neo4j label,
            field_name: Field to constrain

        Returns:
            Result with 'created' or 'existing'
        """
        _validate_label(label)
        _validate_identifier(field_name)
        constraint_name = f"{label}_{field_name}_unique"

        try:
            # Neo4j 5.x syntax for unique constraint
            query = f"""
            CREATE CONSTRAINT {constraint_name} IF NOT EXISTS
            FOR (n:{label}) REQUIRE n.{field_name} IS UNIQUE
            """

            async with self.driver.session() as session:
                await session.run(query)

            return Result.ok("created")

        except Exception as e:
            self.logger.error(f"Failed to create constraint {constraint_name}: {e}")
            return Result.fail(
                Errors.database(
                    operation="create_constraint",
                    message=f"Constraint creation failed: {e}",
                    entity=label,
                )
            )

    async def list_indexes(self, label: str | None = None) -> Result[list[dict[str, Any]]]:
        """
        List all indexes in Neo4j, optionally filtered by label.

        Args:
            label: Optional label to filter by,

        Returns:
            Result with list of index information
        """
        try:
            query = "SHOW INDEXES"

            async with self.driver.session() as session:
                result = await session.run(query)
                indexes = await result.data()

            # Filter by label if provided
            if label:
                indexes = [idx for idx in indexes if label in str(idx.get("labelsOrTypes", []))]

            return Result.ok(indexes)

        except Exception as e:
            self.logger.error(f"Failed to list indexes: {e}")
            return Result.fail(
                Errors.database(operation="list_indexes", message=f"List indexes failed: {e}")
            )

    async def list_constraints(self, label: str | None = None) -> Result[list[dict[str, Any]]]:
        """
        List all constraints in Neo4j, optionally filtered by label.

        Args:
            label: Optional label to filter by,

        Returns:
            Result with list of constraint information
        """
        try:
            query = "SHOW CONSTRAINTS"

            async with self.driver.session() as session:
                result = await session.run(query)
                constraints = await result.data()

            # Filter by label if provided
            if label:
                constraints = [c for c in constraints if label in str(c.get("labelsOrTypes", []))]

            return Result.ok(constraints)

        except Exception as e:
            self.logger.error(f"Failed to list constraints: {e}")
            return Result.fail(
                Errors.database(
                    operation="list_constraints", message=f"List constraints failed: {e}"
                )
            )

    async def create_vector_index(
        self,
        label: str,
        field_name: str = "embedding",
        dimension: int = 1024,
        similarity: str = "cosine",
    ) -> Result[str]:
        """
        Create a vector index for embedding similarity search.

        Used for Neo4j GenAI plugin vector search functionality.
        Requires Neo4j 5.x+ with GenAI plugin installed.

        Args:
            label: Neo4j label (e.g., "Entity", "Task", "Goal", "ContentChunk")
            field_name: Field containing embedding vector (default: "embedding")
            dimension: Vector dimension (default 1024 for bge-large-en-v1.5)
            similarity: Similarity function - "cosine" (default), "euclidean", or "dot"

        Returns:
            Result with 'created' or error

        Example:
            # Create vector index for Knowledge Units
            await schema_manager.create_vector_index("Entity", dimension=1024)

            # Create vector index for ContentChunk nodes
            await schema_manager.create_vector_index("ContentChunk", dimension=1024)

            # Creates index: ku_embedding_idx or contentchunk_embedding_idx
            # For query: db.index.vector.queryNodes('ku_embedding_idx', k, embedding)
        """
        _validate_label(label)
        _validate_identifier(field_name)
        _validate_similarity(similarity)
        index_name = f"{label.lower()}_{field_name}_idx"

        try:
            # Neo4j 5.x vector index syntax
            # Note: Vector indexes use a different syntax than standard indexes
            query = f"""
            CREATE VECTOR INDEX {index_name} IF NOT EXISTS
            FOR (n:{label}) ON (n.{field_name})
            OPTIONS {{
                indexConfig: {{
                    `vector.dimensions`: {dimension},
                    `vector.similarity_function`: '{similarity}'
                }}
            }}
            """

            async with self.driver.session() as session:
                await session.run(query)

            self.logger.info(
                f"Created vector index: {index_name} (dim={dimension}, similarity={similarity})"
            )
            return Result.ok("created")

        except Exception as e:
            self.logger.error(f"Failed to create vector index {index_name}: {e}")
            return Result.fail(
                Errors.database(
                    operation="create_vector_index",
                    message=f"Vector index creation failed: {e}",
                    entity=label,
                )
            )

    async def drop_index(self, index_name: str) -> Result[None]:
        """
        Drop an index by name.

        Args:
            index_name: Name of index to drop,

        Returns:
            Result indicating success or failure
        """
        _validate_identifier(index_name, context="index name")
        try:
            query = f"DROP INDEX {index_name} IF EXISTS"

            async with self.driver.session() as session:
                await session.run(query)

            self.logger.info(f"Dropped index: {index_name}")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Failed to drop index {index_name}: {e}")
            return Result.fail(
                Errors.database(operation="drop_index", message=f"Drop index failed: {e}")
            )

    async def create_composite_index(
        self, label: str, field_names: list[str], index_name: str | None = None
    ) -> Result[str]:
        """
        Create a composite index on multiple fields.

        Args:
            label: Neo4j label
            field_names: List of fields to include in the index
            index_name: Optional custom index name

        Returns:
            Result with 'created' or error
        """
        if not field_names:
            return Result.fail(
                Errors.validation("field_names cannot be empty", field="field_names")
            )

        _validate_label(label)
        for f in field_names:
            _validate_identifier(f)
        name = index_name or f"{label}_{'_'.join(field_names)}_idx"
        if index_name:
            _validate_identifier(index_name, context="index name")
        fields_str = ", ".join(f"n.{f}" for f in field_names)

        try:
            query = f"""
            CREATE INDEX {name} IF NOT EXISTS
            FOR (n:{label}) ON ({fields_str})
            """

            async with self.driver.session() as session:
                await session.run(query)

            self.logger.info(f"Created composite index: {name}")
            return Result.ok("created")

        except Exception as e:
            self.logger.error(f"Failed to create composite index {name}: {e}")
            return Result.fail(
                Errors.database(
                    operation="create_composite_index",
                    message=f"Composite index creation failed: {e}",
                    entity=label,
                )
            )

    async def sync_auth_indexes(self) -> Result[dict[str, Any]]:
        """
        Create authentication-specific indexes for optimal query performance.

        Creates:
        - Composite index on AuthEvent(email, event_type, timestamp) for rate limiting
        - Index on Session(session_token) for session lookup
        - Unique constraint on User(email) for email uniqueness

        Returns:
            Result with summary of created indexes
        """
        results = {"created": [], "failed": []}

        # Rate limiting index: AuthEvent(email, event_type, timestamp)
        # Used by count_recent_failed_attempts() query
        rate_limit_result = await self.create_composite_index(
            "AuthEvent",
            ["email", "event_type", "timestamp"],
            "auth_events_rate_limit",
        )
        if rate_limit_result.is_ok:
            results["created"].append("auth_events_rate_limit")
        else:
            results["failed"].append("auth_events_rate_limit")

        # Session token index (single field)
        session_result = await self._create_index("Session", "session_token")
        if session_result.is_ok:
            results["created"].append("Session_session_token_idx")
        else:
            results["failed"].append("Session_session_token_idx")

        # User email uniqueness constraint
        email_result = await self._create_unique_constraint("User", "email")
        if email_result.is_ok:
            results["created"].append("User_email_unique")
        else:
            results["failed"].append("User_email_unique")

        self.logger.info(
            f"Auth indexes synced: {len(results['created'])} created, {len(results['failed'])} failed"
        )

        return Result.ok(results)

    async def sync_vector_indexes(
        self,
        entity_labels: list[str],
        dimension: int = 1024,
        similarity: str = "cosine",
    ) -> Result[dict[str, Any]]:
        """
        Sync vector indexes for all embedding-enabled entities.

        Creates vector indexes for semantic similarity search using Neo4j GenAI plugin.
        Only run this after enabling GenAI plugin in Neo4j/AuraDB.

        Args:
            entity_labels: List of Neo4j labels with embedding fields (e.g., ["Entity", "Task", "Goal"])
            dimension: Vector dimension (default 1024 for bge-large-en-v1.5)
            similarity: Similarity function (default "cosine")

        Returns:
            Result with summary of created vector indexes

        Example:
            # Create vector indexes for all priority entities
            await schema_manager.sync_vector_indexes(
                entity_labels=["Entity", "Task", "Goal", "LpStep"],
                dimension=1024,
                similarity="cosine"
            )
        """
        results = {"created": [], "failed": []}

        for label in entity_labels:
            result = await self.create_vector_index(
                label=label, field_name="embedding", dimension=dimension, similarity=similarity
            )

            if result.is_ok:
                results["created"].append(f"{label.lower()}_embedding_idx")
            else:
                results["failed"].append(f"{label.lower()}_embedding_idx")

        self.logger.info(
            f"Vector indexes synced: {len(results['created'])} created, {len(results['failed'])} failed"
        )

        return Result.ok(results)

    async def sync_all_models(self, model_registry: dict[str, type[T]]) -> Result[dict[str, Any]]:
        """
        Sync indexes for all registered models.

        Args:
            model_registry: Dict of label -> model class,

        Returns:
            Result with summary of all sync operations

        Example:
            model_registry = {
                'Task': TaskPure,
                'Event': EventPure,
                'Habit': HabitPure
            }
            await schema_manager.sync_all_models(model_registry)
        """
        summary: dict[str, Any] = {
            "total_models": len(model_registry),
            "successful": 0,
            "failed": 0,
            "details": {},
        }

        for label, model_class in model_registry.items():
            result = await self.sync_indexes(model_class, label)

            if result.is_ok:
                summary["successful"] += 1
                summary["details"][label] = result.value
            else:
                summary["failed"] += 1
                summary["details"][label] = {"error": str(result.error)}

        self.logger.info(
            f"Schema sync complete: {summary['successful']}/{summary['total_models']} successful"
        )

        return Result.ok(summary)
