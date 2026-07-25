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

from adapters.persistence.neo4j.session_runner import Neo4jSessionRunner
from core.constants import EmbeddingGeometry
from core.models.enums.neo_labels import NeoLabel
from core.utils.exception_types import NEO4J_EXCEPTIONS
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


def _validate_label(label: NeoLabel) -> None:
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


class Neo4jSchemaManager(Neo4jSessionRunner):
    """
    Manages Neo4j schema (indexes, constraints) based on model metadata.

    Usage:
        schema_manager = Neo4jSchemaManager(driver)
        await schema_manager.sync_indexes(Task, "Task")
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

        # Resolve the label string (explicit arg or the model class name), then
        # validate + convert to NeoLabel at this boundary — index creation
        # requires a SKUEL-modeled label, so fail fast on an unmodeled one.
        label_str = label or entity_class.__name__
        if not NeoLabel.is_valid(label_str):
            return Result.fail(
                Errors.validation(
                    f"Unknown Neo4j label for index sync: {label_str!r}", field="label"
                )
            )
        neo_label = NeoLabel(label_str)
        results: dict[str, list[str]] = {"created": [], "existing": [], "failed": []}

        try:
            for field_info in fields(entity_class):
                # Check if field has index metadata
                if not field_info.metadata.get("index"):
                    continue

                field_name = field_info.name
                is_unique = field_info.metadata.get("unique", False)

                if is_unique:
                    # Create unique constraint
                    result = await self._create_unique_constraint(neo_label, field_name)
                else:
                    # Create regular index
                    result = await self._create_index(neo_label, field_name)

                if result.is_ok:
                    status = result.value
                    if status == "created":
                        results["created"].append(f"{neo_label}.{field_name}")
                        self.logger.info(f"Created index: {neo_label}.{field_name}")
                    else:
                        results["existing"].append(f"{neo_label}.{field_name}")
                        self.logger.debug(f"Index already exists: {neo_label}.{field_name}")
                else:
                    results["failed"].append(f"{neo_label}.{field_name}")
                    self.logger.error(
                        f"Failed to create index: {neo_label}.{field_name}: {result.error}"
                    )

            return Result.ok(results)

        # intentional-broad: schema sync iterates dataclass fields + DB ops
        except Exception as e:
            self.logger.error(f"Schema sync failed for {neo_label}: {e}")
            return Result.fail(Errors.system(f"Schema sync failed: {e}", operation="sync_indexes"))

    async def _create_index(self, label: NeoLabel, field_name: str) -> Result[str]:
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to create index {index_name}: {e}")
            return Result.fail(
                Errors.database(
                    operation="create_index", message=f"Index creation failed: {e}", entity=label
                )
            )

    async def _create_unique_constraint(self, label: NeoLabel, field_name: str) -> Result[str]:
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to create constraint {constraint_name}: {e}")
            return Result.fail(
                Errors.database(
                    operation="create_constraint",
                    message=f"Constraint creation failed: {e}",
                    entity=label,
                )
            )

    async def list_indexes(self, label: NeoLabel | None = None) -> Result[list[dict[str, Any]]]:
        """
        List all indexes in Neo4j, optionally filtered by label.

        Args:
            label: Optional label to filter by,

        Returns:
            Result with list of index information
        """
        try:
            query = "SHOW INDEXES"

            indexes = await self._run_records(query)

            # Filter by label if provided
            if label:
                indexes = [idx for idx in indexes if label in str(idx.get("labelsOrTypes", []))]

            return Result.ok(indexes)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to list indexes: {e}")
            return Result.fail(
                Errors.database(operation="list_indexes", message=f"List indexes failed: {e}")
            )

    async def list_constraints(self, label: NeoLabel | None = None) -> Result[list[dict[str, Any]]]:
        """
        List all constraints in Neo4j, optionally filtered by label.

        Args:
            label: Optional label to filter by,

        Returns:
            Result with list of constraint information
        """
        try:
            query = "SHOW CONSTRAINTS"

            constraints = await self._run_records(query)

            # Filter by label if provided
            if label:
                constraints = [c for c in constraints if label in str(c.get("labelsOrTypes", []))]

            return Result.ok(constraints)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to list constraints: {e}")
            return Result.fail(
                Errors.database(
                    operation="list_constraints", message=f"List constraints failed: {e}"
                )
            )

    async def create_vector_index(
        self,
        label: NeoLabel,
        field_name: str = "embedding",
        dimension: int = EmbeddingGeometry.DIMENSION,
        similarity: str = "cosine",
    ) -> Result[str]:
        """
        Create a vector index for embedding similarity search.

        Embeddings are generated Python-side (ADR-068) — vector indexes are
        native Neo4j 5.x+, no server plugin required.

        Args:
            label: Neo4j label (e.g., "Entity", "Task", "Goal", "ContentChunk")
            field_name: Field containing embedding vector (default: "embedding")
            dimension: Vector dimension (default EmbeddingGeometry.DIMENSION — frozen, ADR-083)
            similarity: Similarity function - "cosine" (default), "euclidean", or "dot"

        Returns:
            Result with 'created' or error

        Example:
            # Create vector index for Knowledge Units
            await schema_manager.create_vector_index("Entity")

            # Create vector index for ContentChunk nodes
            await schema_manager.create_vector_index("ContentChunk")

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

        except NEO4J_EXCEPTIONS as e:
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to drop index {index_name}: {e}")
            return Result.fail(
                Errors.database(operation="drop_index", message=f"Drop index failed: {e}")
            )

    async def create_composite_index(
        self, label: NeoLabel, field_names: list[str], index_name: str | None = None
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

        except NEO4J_EXCEPTIONS as e:
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
        - Index on Session(token_hash) for session lookup (raw tokens are never
          stored — every lookup hashes the cookie token first, and the
          per-request validation in AuthContextMiddleware makes this hot)
        - Unique constraint on User(email) for email uniqueness
        - Unique constraint on Device(pubkey) — WS handshake auth lookup (ADR-075)
        - Index on User(pairing_code_hash) — enrollment redemption lookup (ADR-075)

        Returns:
            Result with summary of created indexes
        """
        results: dict[str, list[str]] = {"created": [], "failed": []}

        # Rate limiting index: AuthEvent(email, event_type, timestamp)
        # Used by count_recent_failed_attempts() query
        rate_limit_result = await self.create_composite_index(
            NeoLabel.AUTH_EVENT,
            ["email", "event_type", "timestamp"],
            "auth_events_rate_limit",
        )
        if rate_limit_result.is_ok:
            results["created"].append("auth_events_rate_limit")
        else:
            results["failed"].append("auth_events_rate_limit")

        # Session token index — on token_hash, the property actually stored on
        # the node (session_token never leaves the cookie). The original index
        # targeted the nonexistent session_token property, leaving every
        # get_session_by_token a label scan; drop it where it still exists.
        session_result = await self._create_index(NeoLabel.SESSION, "token_hash")
        if session_result.is_ok:
            results["created"].append("Session_token_hash_idx")
        else:
            results["failed"].append("Session_token_hash_idx")
        await self.drop_index("Session_session_token_idx")

        # User email uniqueness constraint
        email_result = await self._create_unique_constraint(NeoLabel.USER, "email")
        if email_result.is_ok:
            results["created"].append("User_email_unique")
        else:
            results["failed"].append("User_email_unique")

        # Device pubkey uniqueness (ADR-075 B2, Kody #529): the WS handshake
        # authenticates by pubkey lookup — duplicate rows would make auth
        # resolve to an arbitrary device, and the enrollment read-then-create
        # pre-check alone is racy. The constraint doubles as the lookup index.
        device_pubkey_result = await self._create_unique_constraint(NeoLabel.DEVICE, "pubkey")
        if device_pubkey_result.is_ok:
            results["created"].append("Device_pubkey_unique")
        else:
            results["failed"].append("Device_pubkey_unique")

        # Pairing-code redemption lookup (ADR-075 B2): enrollment matches User
        # by pairing_code_hash on a public, unauthenticated endpoint —
        # unindexed it would scan the User label per attempt.
        pairing_result = await self._create_index(NeoLabel.USER, "pairing_code_hash")
        if pairing_result.is_ok:
            results["created"].append("User_pairing_code_hash_idx")
        else:
            results["failed"].append("User_pairing_code_hash_idx")

        self.logger.info(
            f"Auth indexes synced: {len(results['created'])} created, {len(results['failed'])} failed"
        )

        return Result.ok(results)

    async def sync_conversation_indexes(self) -> Result[dict[str, Any]]:
        """Create constraints + indexes for persisted discussion sessions (ADR-078).

        - UNIQUE on ConversationSession.session_id, ConversationTurn.turn_id
          (id lookups + MERGE-safe identity)
        - INDEX on ConversationSession.user_uid (the revisit-list query anchor)
        - INDEX on ConversationTurn.session_id (turn fan-out per session)

        Idempotent (``IF NOT EXISTS``). These labels are conversation-persistence
        infrastructure, NOT EntityTypes — they carry no vector/fulltext index, by
        design (the understanding wall, ADR-078 §2).
        """
        results: dict[str, list[str]] = {"created": [], "failed": []}

        async def _constraint(label: NeoLabel, field: str, name: str) -> None:
            result = await self._create_unique_constraint(label, field)
            (results["created"] if result.is_ok else results["failed"]).append(name)

        async def _index(label: NeoLabel, field: str, name: str) -> None:
            result = await self._create_named_index(name, label, field)
            (results["created"] if result.is_ok else results["failed"]).append(name)

        await _constraint(
            NeoLabel.CONVERSATION_SESSION, "session_id", "ConversationSession_session_id_unique"
        )
        await _constraint(NeoLabel.CONVERSATION_TURN, "turn_id", "ConversationTurn_turn_id_unique")
        await _index(NeoLabel.CONVERSATION_SESSION, "user_uid", "conversation_session_user_uid_idx")
        await _index(NeoLabel.CONVERSATION_TURN, "session_id", "conversation_turn_session_id_idx")

        self.logger.info(
            f"Conversation indexes synced: {len(results['created'])} created/verified, "
            f"{len(results['failed'])} failed"
        )
        return Result.ok(results)

    async def sync_vector_indexes(
        self,
        entity_labels: list[str],
        dimension: int = EmbeddingGeometry.DIMENSION,
        similarity: str = "cosine",
    ) -> Result[dict[str, Any]]:
        """
        Sync vector indexes for all embedding-enabled entities.

        Creates native Neo4j vector indexes for semantic similarity search;
        embeddings are generated Python-side (ADR-068), no server plugin.

        Args:
            entity_labels: List of Neo4j labels with embedding fields (e.g., ["Entity", "Task", "Goal"])
            dimension: Vector dimension (default EmbeddingGeometry.DIMENSION — frozen, ADR-083)
            similarity: Similarity function (default "cosine")

        Returns:
            Result with summary of created vector indexes

        Example:
            # Create vector indexes for all priority entities
            await schema_manager.sync_vector_indexes(
                entity_labels=["Entity", "ContentChunk", "Ku", "PathStep"],
            )
        """
        results: dict[str, list[str]] = {"created": [], "failed": []}

        for raw_label in entity_labels:
            # entity_labels arrives as plain strings (e.g. from a CLI script),
            # so validate + convert to NeoLabel at this boundary, failing fast
            # on an unmodeled label rather than silently skipping it.
            if not NeoLabel.is_valid(raw_label):
                return Result.fail(
                    Errors.validation(
                        f"Unknown Neo4j label for vector index: {raw_label!r}",
                        field="entity_labels",
                    )
                )
            label = NeoLabel(raw_label)
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

    async def _create_fulltext_index(
        self, index_name: str, label: NeoLabel, fields: list[str]
    ) -> Result[str]:
        """
        Create a full-text index on one or more fields.

        Full-text indexes support Lucene-based text search (relevance-ranked).
        This is the Cypher-first search foundation — always available, no embeddings needed.

        Args:
            index_name: Name for the index
            label: Neo4j label
            fields: Fields to include in the full-text index

        Returns:
            Result with 'created' or error
        """
        _validate_label(label)
        for f in fields:
            _validate_identifier(f)
        _validate_identifier(index_name, context="index name")

        fields_str = ", ".join(f"n.{f}" for f in fields)

        try:
            query = f"""
            CREATE FULLTEXT INDEX {index_name} IF NOT EXISTS
            FOR (n:{label}) ON EACH [{fields_str}]
            """

            async with self.driver.session() as session:
                await session.run(query)

            return Result.ok("created")

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to create fulltext index {index_name}: {e}")
            return Result.fail(
                Errors.database(
                    operation="create_fulltext_index",
                    message=f"Fulltext index creation failed: {e}",
                    entity=label,
                )
            )

    async def sync_fulltext_indexes(self) -> Result[dict[str, Any]]:
        """
        Create full-text indexes for keyword search across all searchable domains.

        This is the Cypher-first search foundation — pure Neo4j, no embeddings,
        no external dependencies. Always created regardless of INTELLIGENCE_TIER.

        Full-text indexes enable Lucene-based keyword search with relevance ranking,
        replacing sequential CONTAINS scans. Field selections align with
        SEARCH_FIELD_CONFIG in core/services/search/config.py.

        Idempotent — uses IF NOT EXISTS. Safe to call on every startup.
        """
        results: dict[str, Any] = {"created": [], "failed": []}

        # Full-text index definitions: (index_name, label, fields)
        # Fields sourced from SEARCH_FIELD_CONFIG — the single source of truth
        fulltext_definitions: list[tuple[str, NeoLabel, list[str]]] = [
            # Activity Domains (6)
            ("task_fulltext_idx", NeoLabel.TASK, ["title", "description"]),
            ("goal_fulltext_idx", NeoLabel.GOAL, ["title", "description"]),
            ("habit_fulltext_idx", NeoLabel.HABIT, ["title", "description"]),
            ("event_fulltext_idx", NeoLabel.EVENT, ["title", "description"]),
            ("choice_fulltext_idx", NeoLabel.CHOICE, ["title", "description", "context"]),
            ("principle_fulltext_idx", NeoLabel.PRINCIPLE, ["title", "statement", "description"]),
            # Curriculum Domains (4)
            ("ku_fulltext_idx", NeoLabel.KU, ["title", "description"]),
            ("path_step_fulltext_idx", NeoLabel.PATH_STEP, ["title", "intent", "description"]),
            (
                "learning_path_fulltext_idx",
                NeoLabel.LEARNING_PATH,
                ["title", "goal", "description"],
            ),
            ("exercise_fulltext_idx", NeoLabel.EXERCISE, ["title", "instructions"]),
            # Learning Loop (2)
            ("revised_exercise_fulltext_idx", NeoLabel.REVISED_EXERCISE, ["title", "instructions"]),
            (
                "user_entry_fulltext_idx",
                NeoLabel.USER_ENTRY,
                ["title", "processed_content"],
            ),
            # Forms (2)
            (
                "form_template_fulltext_idx",
                NeoLabel.FORM_TEMPLATE,
                ["title", "description", "instructions"],
            ),
            (
                "form_submission_fulltext_idx",
                NeoLabel.FORM_SUBMISSION,
                ["title", "processed_content"],
            ),
        ]

        for index_name, label, index_fields in fulltext_definitions:
            result = await self._create_fulltext_index(index_name, label, index_fields)
            if result.is_ok:
                results["created"].append(index_name)
            else:
                results["failed"].append(index_name)

        created_count = len(results["created"])
        failed_count = len(results["failed"])
        self.logger.info(
            f"Fulltext indexes synced: {created_count} created/verified, {failed_count} failed"
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
                'Task': Task,
                'Event': Event,
                'Habit': Habit
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

    async def _create_named_index(
        self, index_name: str, label: NeoLabel, field_name: str
    ) -> Result[str]:
        """Create a named index (custom name instead of auto-generated)."""
        _validate_label(label)
        _validate_identifier(field_name)
        _validate_identifier(index_name, context="index name")

        try:
            query = f"""
            CREATE INDEX {index_name} IF NOT EXISTS
            FOR (n:{label}) ON (n.{field_name})
            """
            async with self.driver.session() as session:
                await session.run(query)
            return Result.ok("created")
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to create index {index_name}: {e}")
            return Result.fail(
                Errors.database(
                    operation="create_index", message=f"Index creation failed: {e}", entity=label
                )
            )

    async def drop_stale_indexes(self) -> Result[dict[str, Any]]:
        """
        Drop indexes that reference labels no longer in use.

        Stale indexes:
        - ai_report_uid_idx (label AiReport — reports use EntryReport)
        - lpstep_embedding_idx (label LpStep — current label is PathStep)
        - journal_submission_* (label JournalSubmission — predecessor of JeInput)
        - journal_report_* (label JournalReport — predecessor of JeOutput)
        - submission_uid_idx (label Submission — abstract base removed in ADR-054)
        - exercise_submission_* (label ExerciseSubmission — collapsed into UserEntry, ADR-054)
        - je_input_* (label JeInput — collapsed into UserEntry, ADR-054)
        - je_output_* (label JeOutput — collapsed into UserEntry, ADR-054)
        - knowledge_fulltext (legacy — label Entity with old field set)
        - tasks_fulltext (legacy — replaced by task_fulltext_idx)
        - journals_fulltext (legacy — label Document no longer exists)
        - curriculum_fulltext_idx (legacy — Curriculum label replaced by PathStep)
        - lpstep_fulltext_idx (legacy — label Lpstep renamed to PathStep)
        - ku_* hierarchical-KU idxs (legacy — Ku properties no writer produces;
          bootstrap CREATE removed, this drops leftovers from older boots)
        """
        stale_indexes = [
            "ai_report_uid_idx",
            "lpstep_embedding_idx",
            "journal_submission_uid_idx",
            "journal_submission_user_uid_idx",
            "journal_report_uid_idx",
            "journal_report_user_uid_idx",
            # ADR-054: Submission/ExerciseSubmission/JeInput/JeOutput collapsed into UserEntry
            "submission_uid_idx",
            "exercise_submission_uid_idx",
            "exercise_submission_user_uid_idx",
            "exercise_submission_fulltext_idx",
            "je_input_uid_idx",
            "je_input_user_uid_idx",
            "je_input_fulltext_idx",
            "je_output_uid_idx",
            "je_output_user_uid_idx",
            "je_output_fulltext_idx",
            # Legacy fulltext indexes (replaced by sync_fulltext_indexes)
            "knowledge_fulltext",
            "tasks_fulltext",
            "journals_fulltext",
            "curriculum_fulltext_idx",
            "lpstep_fulltext_idx",
            # Legacy hierarchical-KU property indexes — bootstrap CREATE block
            # removed from neo4j_adapter.py (Ku carries none of these props;
            # domain membership is the IN_DOMAIN edge, depth_level a query
            # alias). These drop leftovers on DBs that ran the older bootstrap.
            "ku_knowledge_domain_idx",
            "ku_knowledge_subdomain_idx",
            "ku_md_heading_level_idx",
            "ku_parent_id_idx",
            "ku_depth_level_idx",
            "ku_root_domain_idx",
            "ku_knowledge_path_idx",
            "ku_source_file_idx",
            "ku_schema_version_idx",
            "ku_domain_level_idx",
            "ku_parent_level_idx",
        ]
        results: dict[str, Any] = {"dropped": [], "failed": []}

        for index_name in stale_indexes:
            try:
                # Use raw identifier validation (these names are hardcoded, but be safe)
                _validate_identifier(index_name, context="index name")
                query = f"DROP INDEX {index_name} IF EXISTS"
                async with self.driver.session() as session:
                    await session.run(query)
                results["dropped"].append(index_name)
                self.logger.info(f"Dropped stale index: {index_name}")
            except NEO4J_EXCEPTIONS as e:
                results["failed"].append(index_name)
                self.logger.warning(f"Failed to drop stale index {index_name}: {e}")

        return Result.ok(results)

    async def sync_domain_indexes(self) -> Result[dict[str, Any]]:
        """
        Create all domain indexes for optimal query performance.

        Idempotent — uses IF NOT EXISTS. Safe to call on every startup.

        Creates:
        - Entity.uid UNIQUENESS constraint (base label — globally unique uid)
        - UID indexes for the per-type labels (21)
        - user_uid indexes for all UserOwnedEntity types (14)
        - Status indexes for time-sensitive domains (4)
        - Date indexes for temporal queries (4)
        - Entity type discriminator index (1)
        - Composite indexes for hot query paths (3)
        - :SearchEvent behavioral-log indexes (2)
        """
        results: dict[str, Any] = {"created": [], "failed": []}

        # Entity.uid is GLOBALLY UNIQUE — enforce it with a uniqueness
        # constraint, not a plain index. The constraint (a) makes MERGE-on-uid
        # race-safe, so the UserEntry deterministic-uid upsert can't be
        # double-created or cross-tenant-overwritten under concurrent writes
        # (Codex P2 on #317), and (b) guarantees backend.get(uid) can never
        # silently return one of several same-uid nodes. Neo4j refuses a
        # uniqueness constraint while a plain range index covers the same key,
        # so migrate: drop the legacy entity_uid_idx first (no-op on a fresh
        # DB), then create the constraint — its own backing index serves
        # :Entity {uid} lookups identically, so query speed is unchanged.
        try:
            async with self.driver.session() as session:
                await session.run("DROP INDEX entity_uid_idx IF EXISTS")
        except NEO4J_EXCEPTIONS as e:
            self.logger.warning(f"Could not drop legacy entity_uid_idx (will retry next boot): {e}")
        uid_unique = await self._create_unique_constraint(NeoLabel.ENTITY, "uid")
        if uid_unique.is_ok:
            results["created"].append("Entity_uid_unique")
        else:
            results["failed"].append("Entity_uid_unique")

        async def _idx(name: str, label: NeoLabel, field: str) -> None:
            """Create a single named index and track result."""
            result = await self._create_named_index(name, label, field)
            if result.is_ok:
                results["created"].append(name)
            else:
                results["failed"].append(name)

        async def _composite(name: str, label: NeoLabel, fields: list[str]) -> None:
            """Create a composite index and track result."""
            result = await self.create_composite_index(label, fields, index_name=name)
            if result.is_ok:
                results["created"].append(name)
            else:
                results["failed"].append(name)

        # UID indexes — one per entity type. The base :Entity label uses a
        # uniqueness CONSTRAINT instead (created above), whose backing index
        # serves :Entity {uid} lookups, so it is intentionally absent here.
        uid_labels: list[tuple[str, NeoLabel]] = [
            ("task_uid_idx", NeoLabel.TASK),
            ("goal_uid_idx", NeoLabel.GOAL),
            ("habit_uid_idx", NeoLabel.HABIT),
            ("event_uid_idx", NeoLabel.EVENT),
            ("choice_uid_idx", NeoLabel.CHOICE),
            ("principle_uid_idx", NeoLabel.PRINCIPLE),
            ("ku_uid_idx", NeoLabel.KU),
            ("exercise_uid_idx", NeoLabel.EXERCISE),
            ("learning_path_uid_idx", NeoLabel.LEARNING_PATH),
            ("path_step_uid_idx", NeoLabel.PATH_STEP),
            ("life_path_uid_idx", NeoLabel.LIFE_PATH),
            ("resource_uid_idx", NeoLabel.RESOURCE),
            ("user_entry_uid_idx", NeoLabel.USER_ENTRY),
            ("entry_report_uid_idx", NeoLabel.ENTRY_REPORT),
            ("activity_report_uid_idx", NeoLabel.ACTIVITY_REPORT),
            ("form_template_uid_idx", NeoLabel.FORM_TEMPLATE),
            ("form_submission_uid_idx", NeoLabel.FORM_SUBMISSION),
            ("revised_exercise_uid_idx", NeoLabel.REVISED_EXERCISE),
        ]
        for name, label in uid_labels:
            await _idx(name, label, "uid")

        # User UID indexes — all UserOwnedEntity types
        user_uid_labels: list[tuple[str, NeoLabel]] = [
            ("task_user_uid_idx", NeoLabel.TASK),
            ("goal_user_uid_idx", NeoLabel.GOAL),
            ("habit_user_uid_idx", NeoLabel.HABIT),
            ("event_user_uid_idx", NeoLabel.EVENT),
            ("choice_user_uid_idx", NeoLabel.CHOICE),
            ("principle_user_uid_idx", NeoLabel.PRINCIPLE),
            ("user_entry_user_uid_idx", NeoLabel.USER_ENTRY),
            ("entry_report_user_uid_idx", NeoLabel.ENTRY_REPORT),
            ("activity_report_user_uid_idx", NeoLabel.ACTIVITY_REPORT),
            ("form_submission_user_uid_idx", NeoLabel.FORM_SUBMISSION),
            ("revised_exercise_user_uid_idx", NeoLabel.REVISED_EXERCISE),
            ("life_path_user_uid_idx", NeoLabel.LIFE_PATH),
        ]
        for name, label in user_uid_labels:
            await _idx(name, label, "user_uid")

        # Status indexes — time-sensitive activity domains
        status_labels: list[tuple[str, NeoLabel]] = [
            ("task_status_idx", NeoLabel.TASK),
            ("goal_status_idx", NeoLabel.GOAL),
            ("habit_status_idx", NeoLabel.HABIT),
            ("event_status_idx", NeoLabel.EVENT),
        ]
        for name, label in status_labels:
            await _idx(name, label, "status")

        # Date indexes — temporal queries
        date_indexes: list[tuple[str, NeoLabel, str]] = [
            ("task_due_date_idx", NeoLabel.TASK, "due_date"),
            ("event_event_date_idx", NeoLabel.EVENT, "event_date"),
            ("goal_target_date_idx", NeoLabel.GOAL, "target_date"),
        ]
        for name, label, field in date_indexes:
            await _idx(name, label, field)

        # Entity type discriminator index
        await _idx("entity_type_idx", NeoLabel.ENTITY, "entity_type")

        # Composite indexes — hot query paths
        await _composite("task_user_status_idx", NeoLabel.TASK, ["user_uid", "status"])
        await _composite("goal_user_status_idx", NeoLabel.GOAL, ["user_uid", "status"])
        await _composite("entity_user_type_idx", NeoLabel.ENTITY, ["user_uid", "entity_type"])

        # Search behavioral log (:SearchEvent, discovery analytics) — gap
        # aggregation groups by query_normalized and windows on created_at
        await _idx("search_event_query_idx", NeoLabel.SEARCH_EVENT, "query_normalized")
        await _idx("search_event_created_idx", NeoLabel.SEARCH_EVENT, "created_at")

        created_count = len(results["created"])
        failed_count = len(results["failed"])
        self.logger.info(
            f"Domain indexes synced: {created_count} created/verified, {failed_count} failed"
        )

        return Result.ok(results)
