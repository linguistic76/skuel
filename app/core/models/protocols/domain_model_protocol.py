"""
Domain Model Protocol - Generic Backend Type Safety
===================================================

Protocol defining the structural contract for all domain models (Tier 3).

Purpose:
- Enables type-safe generic operations in UniversalNeo4jBackend
- Defines minimum requirements for all domain models
- Allows MyPy to verify domain model operations without concrete types

Design Philosophy (from CLAUDE.md):
"Type errors as teachers, showing us where components don't flow together properly.
By listening to them, we strengthen the core."

This protocol emerged from 700+ MyPy errors in UniversalNeo4jBackend where the
unconstrained generic type T had no guaranteed attributes. Rather than suppressing
errors with type: ignore, we define the actual contract all domain models follow.

Architecture:
    All domain models must:
    1. Have a unique identifier (uid)
    2. Track creation/update timestamps
    3. Provide Neo4j node label via entity_label()
    4. Support DTO conversion (from_dto, to_dto)

Usage:
    # Before (unconstrained generic)
    class UniversalNeo4jBackend(Generic[T]):
        async def create(self, entity: T) -> Result[T]:
            entity_uid = entity.uid  # ❌ Error: "T" has no attribute "uid"

    # After (protocol-constrained generic)
    class UniversalNeo4jBackend(Generic[T: DomainModelProtocol]):
        async def create(self, entity: T) -> Result[T]:
            entity_uid = entity.uid  # ✅ Type-safe!

Implementation Note:
- This is a structural protocol (duck typing)
- Existing domain models automatically satisfy it
- No changes needed to existing models
- Protocol only makes implicit contract explicit

See Also:
- conversion_protocols.py - DTO/Model conversion protocols
- CLAUDE.md §2.4 - Three-Tier Type System
"""

from datetime import datetime
from typing import Any, Protocol, Self


class DomainModelProtocol(Protocol):
    """
    Structural protocol for all domain models (Tier 3).

    Domain models are immutable frozen dataclasses with business logic.
    This protocol defines the minimum contract for generic backend operations.

    Required Attributes:
        uid: Unique identifier (e.g., "task.123", "ku.python.basics")
        created_at: Entity creation timestamp (Optional statically, guaranteed non-None at runtime)
        updated_at: Last modification timestamp (Optional statically, guaranteed non-None at runtime)

    Required Class Methods:
        from_dto: Creates domain model from DTO

    Required Instance Methods:
        to_dto: Converts domain model to DTO

    Implementations:
        ALL domain models in core/models/*/
        - Task (task.py)
        - Event (event.py)
        - Habit (habit.py)
        - Goal (goal.py)
        - KnowledgeUnit (ku.py)
        - LearningStep (ls.py)
        - LearningPath (lp.py)
        - Expense, Budget, JournalEntry, Choice, Principle, etc.
        Total: ~20 domain models

    Frozen Dataclass Pattern (from CLAUDE.md):
        SKUEL uses the frozen dataclass + dynamic default pattern:

        @dataclass(frozen=True)
        class TaskPure:
            uid: str
            created_at: datetime = None  # type: ignore[assignment]
            updated_at: datetime = None  # type: ignore[assignment]

            def __post_init__(self) -> None:
                if self.created_at is None:
                    object.__setattr__(self, 'created_at', datetime.now())
                if self.updated_at is None:
                    object.__setattr__(self, 'updated_at', datetime.now())

        This pattern is architecturally correct and works perfectly at runtime,
        but MyPy sees the static type as `datetime | None` due to the None default.

        Therefore, this protocol accepts Optional types statically while
        documenting the runtime guarantee of non-None values.

    Example:
        # Type-safe generic backend operation
        def process_entity[T: DomainModelProtocol](entity: T) -> str:
            # All these are guaranteed at RUNTIME (not statically):
            uid = entity.uid                    # ✅ Always present
            timestamp = entity.created_at       # ✅ Non-None at runtime
            dto = entity.to_dto()               # ✅ Type-safe
            return uid
    """

    # Required attributes (all domain models have these)
    uid: str
    # Optional statically (due to None default), but guaranteed non-None at runtime via __post_init__
    created_at: datetime | None
    updated_at: datetime | None

    # Optional but common attributes
    # Note: Not all models have user_uid (e.g., User itself doesn't)
    # user_uid: str | None

    @classmethod
    def from_dto(cls, dto: Any) -> Self:
        """
        Create immutable domain model from mutable DTO.

        Args:
            dto: DTO instance (any type - typically {EntityName}DTO)

        Returns:
            Immutable domain model instance

        Example:
            task_dto = TaskDTO(uid="task.123", title="Deploy", ...)
            task = Task.from_dto(task_dto)
            # → Task(frozen=True, with business logic)

        See Also:
            DomainModelConvertible protocol in conversion_protocols.py
        """
        ...

    def to_dto(self) -> Any:
        """
        Convert immutable domain model to mutable DTO.

        Returns:
            Mutable DTO instance

        Example:
            task = Task(uid="task.123", ...)
            dto = task.to_dto()  # Returns TaskDTO (mutable)
            dto.title = "Updated"  # ✅ Can modify

        See Also:
            DomainModelConvertible protocol in conversion_protocols.py
        """
        ...


class DTOProtocol(Protocol):
    """
    Structural protocol for Data Transfer Objects (Tier 2).

    DTOs are mutable dataclasses for data transfer between layers.

    Required Attributes:
        metadata: Optional dict for graph context and enrichment data

    Required Class Methods:
        from_dict: Creates DTO from dictionary (database/API data)

    Required Instance Methods:
        to_dict: Converts DTO to dictionary (serialization)

    Note: This duplicates DTOConvertible in conversion_protocols.py,
    but keeps domain_model_protocol.py self-contained for backend usage.

    See Also:
        DTOConvertible in conversion_protocols.py (same contract)
    """

    metadata: dict[str, Any] | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create DTO from dictionary (database/API)."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Convert DTO to dictionary (serialization)."""
        ...


class DomainModelClassProtocol(Protocol):
    """
    Protocol for domain model CLASS operations (not instances).

    Used in BaseService._to_domain_model where we pass the class itself,
    not an instance. MyPy needs to know the class has certain class methods.

    Usage:
        def convert_to_model[T: DomainModelProtocol](
            data: dict[str, Any],
            dto_class: type[DTOProtocol],
            model_class: DomainModelClassProtocol
        ) -> DomainModelProtocol:
            dto = dto_class.from_dict(data)
            return model_class.from_dto(dto)  # ✅ Type-safe class method call

    This solves the base_service.py:911 error:
        Error: "type" has no attribute "from_dto"

    Note: entity_label() is NOT included because domain models don't actually
    implement it. The label is passed to UniversalNeo4jBackend constructor instead.
    """

    @classmethod
    def from_dto(cls, dto: Any) -> DomainModelProtocol:
        """Create domain model from DTO (class method)."""
        ...
