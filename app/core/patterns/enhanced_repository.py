"""
Enhanced Repository pattern with bulk operations support.

This extends the base Repository pattern with graph-native bulk operations,
completing the generic programming evolution.
"""

from typing import Any, Protocol, TypeVar

from core.patterns.repository import Repository
from core.utils.result_simplified import Result

T = TypeVar("T")
ID = TypeVar("ID")


class BulkRepository(Repository[T, ID], Protocol):
    """
    Extended repository interface with bulk operations.

    Adds efficient batch operations while maintaining the simplicity
    of the base Repository pattern.
    """

    async def bulk_save(self, entities: list[T], batch_size: int = 1000) -> Result[dict[str, Any]]:
        """
        Save multiple entities in a single operation.

        Args:
            entities: List of entities to save,
            batch_size: Number of entities per transaction

        Returns:
            Result with statistics (nodes_created, nodes_updated, etc.)
        """
        ...

    async def bulk_delete(self, ids: list[ID], cascade: bool = False) -> Result[int]:
        """
        Delete multiple entities by ID.

        Args:
            ids: List of IDs to delete,
            cascade: If True, delete related entities

        Returns:
            Result with count of deleted entities
        """
        ...

    async def upsert_with_relationships(
        self, entities: list[T], relationship_config: dict[str, Any]
    ) -> Result[dict[str, Any]]:
        """
        Upsert entities with their relationships in a single operation.

        Args:
            entities: Entities to upsert,
            relationship_config: Configuration for relationships

        Returns:
            Result with operation statistics
        """
        ...


class VectorizedRepository(Protocol):
    """
    Repository operations for vector-enabled entities.

    Provides vector-specific operations for entities that model
    directional change and trajectories.
    """

    async def create_vector_transition(
        self,
        from_state: Any,
        to_state: Any,
        vector_components: dict[str, float],
        metadata: dict[str, Any] | None = None,
    ) -> Result[str]:
        """
        Create a vectorized transition between states.

        Args:
            from_state: Origin state/entity,
            to_state: Target state/entity,
            vector_components: Vector components describing the transition,
            metadata: Additional transition metadata

        Returns:
            Result containing transition ID
        """
        ...

    async def find_aligned_entities(
        self, reference_vector: dict[str, float], threshold: float = 0.7, limit: int = 10
    ) -> Result[list[T]]:
        """
        Find entities aligned with a reference vector.

        Args:
            reference_vector: Reference vector components,
            threshold: Minimum alignment score (0-1),
            limit: Maximum results

        Returns:
            Result with aligned entities
        """
        ...

    async def compute_trajectory(
        self, entity_id: ID, timeframe: tuple | None = None
    ) -> Result[dict[str, Any]]:
        """
        Compute the trajectory of an entity over time.

        Args:
            entity_id: Entity to analyze,
            timeframe: Optional (start, end) dates

        Returns:
            Result with trajectory analysis
        """
        ...
