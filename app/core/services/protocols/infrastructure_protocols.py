"""
Infrastructure Service Protocols
=================================

Interfaces for infrastructure and system services.
"""

from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from core.models.type_hints import Metadata
from core.utils.result_simplified import Result


@runtime_checkable
class EventBusOperations(Protocol):
    """Event bus operations for type-safe event publishing and subscription.

    Modern typed event bus interface - events are strongly-typed objects,
    not string-based messages.

    Note: Event bus methods return None for simplicity - event publishing
    is fire-and-forget. Subscription is synchronous configuration.
    """

    def publish(self, event: Any) -> None:
        """
        Publish a typed event to the bus (sync version).

        Args:
            event: Event object (instance of a domain event class)
        """
        ...

    def subscribe(self, event_type: type, handler: Any) -> None:
        """
        Subscribe to events of a given type.

        Args:
            event_type: Event class to subscribe to (e.g., TaskCompleted)
            handler: Function to call when event is published (sync or async)
        """
        ...

    async def publish_async(self, event: Any) -> None:
        """
        Publish a typed event asynchronously (preferred for async contexts).

        Args:
            event: Event object (instance of a domain event class)
        """
        ...


@runtime_checkable
class UserOperations(Protocol):
    """User management operations.

    Note: Using Any for user type to avoid circular imports.
    Implementations should use the concrete User model from core.models.user.
    All methods return Result[T] for consistent error handling.
    """

    async def create_user(self, user: Any) -> Result[Any]:
        """Create a new user. Returns Result[User]."""
        ...

    async def get_user_by_uid(self, user_uid: str) -> Result[Any | None]:
        """Get user by UID. Returns Result[Optional[User]]."""
        ...

    async def get_user_by_username(self, username: str) -> Result[Any | None]:
        """Get user by username. Returns Result[Optional[User]]."""
        ...

    async def update_user(self, user: Any) -> Result[Any]:
        """Update user data. Returns Result[User]."""
        ...

    async def delete_user(self, user_uid: str) -> Result[bool]:
        """DETACH DELETE a user. Returns Result[bool]."""
        ...

    async def update_user_progress(self, user_uid: str, progress_updates: Metadata) -> Result[bool]:
        """Update user's learning progress. Returns Result[bool]."""
        ...

    async def get_user_context(self, user_uid: str) -> Result[Any]:
        """Get user context (UserContext). Returns Result[UserContext]."""
        ...

    async def get(self, user_uid: str) -> Result[Any | None]:
        """Get user by UID. Alias for get_user_by_uid. Returns Result[Optional[User]]."""
        ...

    async def find_by(self, **filters: Any) -> Result[list[Any]]:
        """
        Find users by arbitrary filters.

        Args:
            **filters: Field filters (e.g., email="test@example.com", is_active=True)

        Returns:
            Result[list[User]]: Matching users
        """
        ...

    async def record_knowledge_mastery(
        self,
        user_uid: str,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int = 1,
        confidence_level: float = 0.8,
    ) -> Result[bool]:
        """Record user's mastery level for a knowledge unit. Returns Result[bool]."""
        ...

    async def record_knowledge_progress(
        self,
        user_uid: str,
        knowledge_uid: str,
        progress: float,
        time_invested_minutes: int = 0,
        difficulty_rating: float | None = None,
    ) -> Result[bool]:
        """Record user's progress on a knowledge unit. Returns Result[bool]."""
        ...

    async def get_user_mastery(
        self,
        user_uid: str,
        concept_uid: str,
    ) -> Result[float]:
        """
        Get user's mastery level for a knowledge concept.

        Args:
            user_uid: User UID
            concept_uid: Knowledge unit UID

        Returns:
            Result[float]: Mastery score (0.0-1.0)
        """
        ...

    async def enroll_in_learning_path(
        self,
        user_uid: str,
        learning_path_uid: str,
        target_completion: str | None = None,
        weekly_time_commitment: int = 300,
        motivation_note: str = "",
    ) -> Result[bool]:
        """Enroll user in a learning path. Returns Result[bool]."""
        ...

    async def complete_learning_path_graph(
        self,
        user_uid: str,
        learning_path_uid: str,
        completion_score: float = 1.0,
        feedback_rating: int | None = None,
    ) -> Result[bool]:
        """Mark a learning path as completed in the graph. Returns Result[bool]."""
        ...

    async def express_interest_in_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        interest_score: float = 0.8,
        interest_source: str = "discovery",
        priority: str = "medium",
        notes: str = "",
    ) -> Result[bool]:
        """Record user's interest in a knowledge unit. Returns Result[bool]."""
        ...

    async def bookmark_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        bookmark_reason: str = "reference",
        tags: list | None = None,
        reminder_date: str | None = None,
    ) -> Result[bool]:
        """Bookmark a knowledge unit for later review. Returns Result[bool]."""
        ...

    async def update_user_activity(self, user_uid: str, activity_data: Metadata) -> Result[bool]:
        """Update user's activity tracking data. Returns Result[bool]."""
        ...

    async def add_conversation_message(
        self, user_uid: str, role: str, content: str, metadata: Metadata | None = None
    ) -> Result[bool]:
        """Add a conversation message to user's history. Returns Result[bool]."""
        ...

    async def get_active_learners(
        self, since_hours: int = 24, limit: int = 100
    ) -> Result[list[Any]]:
        """Get list of active learners. Returns Result[List[User]]."""
        ...


@runtime_checkable
class SchemaOperations(Protocol):
    """Database schema operations."""

    async def execute_query(self, query: str, params: Metadata | None = None) -> list[Metadata]:
        """Execute a graph query for schema introspection."""
        ...

    async def get_node_labels(self) -> list[str]:
        """Get all node labels in the database."""
        ...

    async def get_relationship_types(self) -> list[str]:
        """Get all relationship types."""
        ...

    async def get_node_properties(self, label: str) -> list[dict[str, str]]:
        """Get properties for a node label."""
        ...

    async def create_index(self, label: str, property: str) -> bool:
        """Create an index on a property."""
        ...

    async def create_constraint(self, label: str, property: str, constraint_type: str) -> bool:
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

    async def ingest_file(self, file_path: Path) -> Result[dict[str, Any]]:
        """Ingest a single MD or YAML file into Neo4j."""
        ...

    async def ingest_directory(
        self,
        directory: Path,
        pattern: str = "*",
        batch_size: int = 500,
        max_concurrent: int = 20,
        ingestion_mode: Literal["full", "incremental", "smart"] = "full",
        validate_targets: bool = False,
        progress_callback: Any | None = None,
        dry_run: bool = False,
    ) -> Result[Any]:
        """Ingest all supported files in a directory."""
        ...

    async def ingest_vault(
        self,
        vault_path: Path,
        subdirs: list[str] | None = None,
    ) -> Result[Any]:
        """Ingest an Obsidian vault or specific subdirectories."""
        ...

    async def ingest_bundle(self, bundle_path: Path) -> Result[Any]:
        """Ingest a domain bundle using manifest file."""
        ...
