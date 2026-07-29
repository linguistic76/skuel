"""
Infrastructure Service Protocols
=================================

Interfaces for infrastructure and system services.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from core.models.type_hints import FilterValue, Metadata, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from core.events.base import BaseEvent
    from core.models.enums.neo_labels import NeoLabel
    from core.models.user import User
    from core.services.ingestion.types import (
        BundleStats,
        DryRunPreview,
        IncrementalStats,
        IngestionStats,
    )


# A subscriber for events of type ``E``. Sync and async handlers are both
# registered through the same call — ``InMemoryEventBus.subscribe`` sorts them
# with ``inspect.iscoroutinefunction`` — so the alias carries both arms.
# Parameterising by the event type is what makes a cross-event miswiring
# (subscribing a TaskCompleted handler to GoalCreated) a type error.
type EventHandler[E: BaseEvent] = Callable[[E], None] | Callable[[E], Awaitable[None]]


@runtime_checkable
class EventBusOperations(Protocol):
    """Event bus operations for type-safe event publishing and subscription.

    Modern typed event bus interface - events are strongly-typed objects,
    not string-based messages.

    Note: Event bus methods return None for simplicity - event publishing
    is fire-and-forget. Subscription is synchronous configuration.
    """

    def publish(self, event: "BaseEvent") -> None:
        """
        Publish a typed event to the bus (sync version).

        Args:
            event: Event object (instance of a domain event class)
        """
        ...

    def subscribe[E: "BaseEvent"](self, event_type: type[E], handler: "EventHandler[E]") -> None:
        """
        Subscribe to events of a given type.

        Args:
            event_type: Event class to subscribe to (e.g., TaskCompleted)
            handler: Function to call when published (sync or async), taking
                an instance of *event_type*
        """
        ...

    def unsubscribe[E: "BaseEvent"](self, event_type: type[E], handler: "EventHandler[E]") -> None:
        """
        Unsubscribe a previously-registered handler.

        Required for handler lifecycles that need to detach when a subscriber
        (e.g. a background worker or recorder) is torn down.

        Args:
            event_type: Event class to unsubscribe from
            handler: Handler function previously passed to subscribe()
        """
        ...

    async def publish_async(self, event: "BaseEvent") -> None:
        """
        Publish a typed event asynchronously (preferred for async contexts).

        Args:
            event: Event object (instance of a domain event class)
        """
        ...


@runtime_checkable
class DrainableEventBusOperations(Protocol):
    """Narrower protocol for event buses that support graceful drain/cancel.

    Used in shutdown paths to drain in-flight handlers before teardown.
    InMemoryEventBus satisfies this; other bus implementations need not.
    """

    def get_pending_task_count(self) -> int: ...

    async def wait_for_pending_tasks(self, timeout_seconds: float | None = None) -> None: ...

    def cancel_all_tasks(self) -> int: ...


@runtime_checkable
class UserCrudOperations(Protocol):
    """User identity CRUD. Used by: UserCoreService.

    See: /docs/patterns/BACKEND_OPERATIONS_ISP.md
    """

    async def create_user(self, user: "User") -> Result["User"]:
        """Create a new user."""
        ...

    async def get_user_by_uid(self, user_uid: UserUID) -> Result["User | None"]:
        """Get user by UID."""
        ...

    async def get_user_by_username(self, username: str) -> Result["User | None"]:
        """Get user by username."""
        ...

    async def update_user(self, user: "User") -> Result["User"]:
        """Update user data."""
        ...

    async def atomic_append_dual_track_checkin(
        self,
        user_uid: UserUID,
        snapshot: "dict[str, Any]",
        history_limit: int,
        dimension: str,
    ) -> Result[bool]:
        """Atomically append a user-level dual-track check-in snapshot to the
        ``:User`` node's ``dual_track_checkins`` log, keyed by ``dimension`` —
        serialized via a node write-lock so concurrent same-user appends can't lose
        a snapshot (ADR-030)."""
        ...

    async def atomic_append_knowledge_checkin(
        self,
        user_uid: UserUID,
        snapshot: "dict[str, Any]",
        history_limit: int,
        ku_uid: str,
    ) -> Result[bool]:
        """Atomically append a Knowledge dual-track check-in snapshot to the
        ``:User`` node's ``knowledge_checkins`` log, keyed by ``ku_uid`` — serialized
        via a node write-lock so concurrent same-(user, Ku) appends can't lose a
        snapshot (ADR-030)."""
        ...

    async def delete_user(self, user_uid: UserUID) -> Result[bool]:
        """Soft-delete a user: mark status=DELETED, scrub PII, preserve graph."""
        ...

    async def hard_delete_user(self, user_uid: UserUID) -> Result[int]:
        """Delete a user + every OWNS-linked entity (GDPR erasure)."""
        ...

    async def find_by(self, **filters: FilterValue) -> Result[list["User"]]:
        """Find users by field filters.

        The implementer builds a Cypher WHERE clause and hands the dict
        straight to ``session.run`` as query parameters, so the values are
        driver primitives — ``FilterValue``, not a boundary.
        """
        ...


@runtime_checkable
class UserLearningStateOperations(Protocol):
    """Learning state management. Used by: UserProgressRecorderService.

    See: /docs/patterns/BACKEND_OPERATIONS_ISP.md
    """

    async def update_user_progress(
        self, user_uid: UserUID, progress_updates: Metadata
    ) -> Result[bool]:
        """Update user's learning progress."""
        ...

    async def record_knowledge_mastery(
        self,
        user_uid: UserUID,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int = 1,
        confidence_level: float = 0.8,
    ) -> Result[bool]:
        """Record user's mastery level for a knowledge unit."""
        ...

    async def record_knowledge_progress(
        self,
        user_uid: UserUID,
        knowledge_uid: str,
        progress: float,
        time_invested_minutes: int = 0,
        difficulty_rating: float | None = None,
    ) -> Result[bool]:
        """Record user's progress on a knowledge unit."""
        ...

    async def get_user_mastery(
        self,
        user_uid: UserUID,
        concept_uid: str,
    ) -> Result[float]:
        """Get user's mastery level for a knowledge concept (0.0-1.0)."""
        ...

    async def enroll_in_learning_path(
        self,
        user_uid: UserUID,
        learning_path_uid: str,
        target_completion: str | None = None,
        weekly_time_commitment: int = 300,
        motivation_note: str = "",
    ) -> Result[bool]:
        """Enroll user in a learning path."""
        ...

    async def complete_learning_path(
        self,
        user_uid: UserUID,
        learning_path_uid: str,
        completion_score: float = 1.0,
        feedback_rating: int | None = None,
    ) -> Result[bool]:
        """Mark a learning path as completed."""
        ...

    async def express_interest_in_knowledge(
        self,
        user_uid: UserUID,
        knowledge_uid: str,
        interest_score: float = 0.8,
        interest_source: str = "discovery",
        priority: str = "medium",
        notes: str = "",
    ) -> Result[bool]:
        """Record user's interest in a knowledge unit."""
        ...

    async def bookmark_knowledge(
        self,
        user_uid: UserUID,
        knowledge_uid: str,
        bookmark_reason: str = "reference",
        tags: list[str] | None = None,
        reminder_date: str | None = None,
    ) -> Result[bool]:
        """Bookmark a knowledge unit for later review."""
        ...


@runtime_checkable
class UserActivityOperations(Protocol):
    """Activity tracking. Used by: UserActivityService.

    See: /docs/patterns/BACKEND_OPERATIONS_ISP.md
    """

    async def update_user_activity(
        self, user_uid: UserUID, activity_data: Metadata
    ) -> Result[bool]:
        """Update user's activity tracking data."""
        ...

    async def add_conversation_message(
        self, user_uid: UserUID, role: str, content: str, metadata: Metadata | None = None
    ) -> Result[bool]:
        """Add a conversation message to user's history."""
        ...

    async def get_active_learners(
        self, since_hours: int = 24, limit: int = 100
    ) -> Result[list["User"]]:
        """Get list of active learners."""
        ...


@runtime_checkable
class UserOperations(
    UserCrudOperations, UserLearningStateOperations, UserActivityOperations, Protocol
):
    """Full user backend operations (composed). Use narrowest sub-protocol for ISP.

    Composed from:
    - UserCrudOperations (6 methods) — identity CRUD
    - UserLearningStateOperations (8 methods) — learning state management
    - UserActivityOperations (3 methods) — activity tracking

    See: /docs/patterns/BACKEND_OPERATIONS_ISP.md
    """

    ...


@runtime_checkable
class SchemaQueryExecutor(Protocol):
    """Minimal raw-query slice consumed by Neo4jSchemaService.

    The schema service implements its own introspection (labels, properties,
    indexes, constraints) on top of a single primitive: raw query execution.
    Narrowing the constructor dependency to this one method lets any adapter
    exposing ``execute_query`` drive the service without satisfying the wider
    six-method ``SchemaOperations`` contract. See: BACKEND_OPERATIONS_ISP.md.
    """

    async def execute_query(self, query: str, params: Metadata | None = None) -> list[Metadata]:
        """Execute a graph query for schema introspection."""
        ...


@runtime_checkable
class SchemaOperations(SchemaQueryExecutor, Protocol):
    """Database schema operations."""

    async def get_node_labels(self) -> list[str]:
        """Get all node labels in the database."""
        ...

    async def get_relationship_types(self) -> list[str]:
        """Get all relationship types."""
        ...

    async def get_node_properties(self, label: "NeoLabel") -> list[dict[str, str]]:
        """Get properties for a node label."""
        ...

    async def create_index(self, label: "NeoLabel", property: str) -> bool:
        """Create an index on a property."""
        ...

    async def create_constraint(
        self, label: "NeoLabel", property: str, constraint_type: str
    ) -> bool:
        """Create a constraint."""
        ...


@runtime_checkable
class Closeable(Protocol):
    """Protocol for objects that can be closed."""

    def close(self) -> None:
        """Close the resource."""
        ...


@runtime_checkable
class AsyncCloseable(Protocol):
    """Protocol for objects that can be closed asynchronously."""

    async def close(self) -> None:
        """Close the resource asynchronously."""
        ...


@runtime_checkable
class IngestionOperations(Protocol):
    """Content ingestion operations for MD/YAML → Neo4j pipeline.

    Covers the public async API surface of UnifiedIngestionService.
    All methods return Result[T] for consistent error handling.

    See: /docs/architecture/CORE_SYSTEMS_ARCHITECTURE.md
    """

    async def ingest_file(
        self, file_path: Path, *, user_uid: UserUID | None = None
    ) -> Result[dict[str, Any]]:
        """Ingest a single MD or YAML file into Neo4j.

        Args:
            file_path: Path to file to ingest
            user_uid: Override user UID for multi-tenant entities.

        boundary: Two code paths — node ingestion returns {uid, title, entity_type,
        format, success, nodes_created, nodes_updated, relationships_created,
        chunks_generated}; edge ingestion returns {from_uid, to_uid, relationship,
        created, success}. Unifying would require a tagged union.
        """
        ...

    async def ingest_directory(
        self,
        directory: Path,
        pattern: str = "*",
        batch_size: int = 500,
        max_concurrent: int = 20,
        ingestion_mode: Literal["full", "incremental", "smart"] = "full",
        force: bool = False,
        validate_targets: bool = False,
        dry_run: bool = False,
        *,
        user_uid: UserUID | None = None,
    ) -> "Result[IngestionStats | IncrementalStats | DryRunPreview]":
        """Ingest all supported files in a directory.

        ``force=True`` re-processes unchanged files while keeping tracked-mode
        semantics (wall, metadata re-stamping, deletion reconciliation) —
        force ≠ full.
        """
        ...

    async def ingest_vault(
        self,
        vault_path: Path,
        subdirs: list[str] | None = None,
        *,
        user_uid: UserUID | None = None,
    ) -> "Result[IngestionStats]":
        """Ingest an Obsidian vault or specific subdirectories."""
        ...

    async def ingest_bundle(
        self, bundle_path: Path, *, user_uid: "UserUID | None" = None
    ) -> "Result[BundleStats]":
        """Ingest a domain bundle using manifest file."""
        ...
