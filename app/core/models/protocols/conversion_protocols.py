"""
Conversion Protocols - Three-Tier Type System
==============================================

Explicit Protocol definitions for SKUEL's three-tier architecture.

Pattern 3A Fix (2025-10-19):
- Formalizes implicit DTO conversion pattern used in 16 DTOs
- Formalizes implicit domain model conversion pattern used in 13 models
- Enables type-safe generic helper functions in dto_helpers.py
- Uses structural typing - no changes needed to existing DTOs/models

Architecture:
    External → [Pydantic] → [DTOs] → [Domain Models] → Core Logic

    DTOConvertible: from_dict(dict) → DTO, to_dict() → dict,
    DomainModelConvertible: from_dto(DTO) → Model, to_dto() → DTO
"""

from typing import Any, Protocol, Self


class DTOConvertible(Protocol):
    """
    Protocol for Data Transfer Objects (Tier 2).

    DTOs are mutable dataclasses for transferring data between layers.
    This protocol defines the standard conversion methods all DTOs implement.

    Implementations:
        - ExpenseDTO (finance_dto.py)
        - BudgetDTO (finance_dto.py)
        - LearningStepDTO (ls_dto.py)
        - KnowledgeUnitDTO (ku_dto.py)
        - TaskDTO, GoalDTO, HabitDTO, EventDTO, etc.
        - Total: 16 DTOs across all domains

    Usage:
        # Type-safe generic conversion
        def to_domain_model[D: DTOConvertible, M: DomainModelConvertible](
            data: dict[str, Any],
            dto_class: type[D],
            model_class: type[M]
        ) -> M:
            dto = dto_class.from_dict(data)  # ✅ Type-safe
            return model_class.from_dto(dto)  # ✅ Type-safe
    """

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """
        Create DTO from dictionary (typically from database/API).

        Standard implementation pattern:
        - Parse date strings to date objects
        - Parse datetime strings to datetime objects
        - Convert string enum values to Enum instances
        - Handle nested objects/lists
        - Return typed DTO instance

        Args:
            data: Dictionary with DTO field data

        Returns:
            Typed DTO instance

        Example:
            # ExpenseDTO.from_dict()
            data = {"uid": "exp_123", "amount": 50.0, ...}
            expense_dto = ExpenseDTO.from_dict(data)
        """
        ...

    def to_dict(self) -> dict[str, Any]:
        """
        Convert DTO to dictionary for serialization.

        Standard implementation pattern:
        - Convert date objects to ISO format strings
        - Convert datetime objects to ISO format strings
        - Convert Enum instances to .value (string)
        - Recursively convert nested DTOs
        - Return plain dict suitable for JSON/database

        Returns:
            Dictionary representation of DTO,

        Example:
            # ExpenseDTO.to_dict()
            expense_dto.to_dict()
            # → {"uid": "exp_123", "amount": 50.0, "expense_date": "2025-10-19", ...}
        """
        ...


class DomainModelConvertible(Protocol):
    """
    Protocol for Domain Models (Tier 3).

    Domain models are immutable dataclasses with business logic.
    This protocol defines the standard conversion methods all models implement.

    Implementations:
        - LearningStep (ls.py) - from_dto(), to_dto()
        - KnowledgeUnit (ku.py) - from_dto(), to_dto()
        - Task, Goal, Habit, Event, etc.
        - Total: 13 domain models across all domains

    Note: Domain models are frozen dataclasses - immutable by design.
    Use to_dto() to get mutable version for updates.

    Usage:
        # Type-safe conversion
        step_dto = LearningStepDTO.from_dict(data)
        step = LearningStep.from_dto(step_dto)  # ✅ Immutable domain model

        # Update pattern
        updated_dto = step.to_dto()  # Get mutable DTO
        updated_dto.title = "New Title"  # Modify DTO
        updated_step = LearningStep.from_dto(updated_dto)  # New immutable model
    """

    @classmethod
    def from_dto(cls, dto: Any) -> Self:
        """
        Create immutable domain model from mutable DTO.

        Standard implementation pattern:
        - Convert lists to tuples (immutability)
        - Extract all DTO fields
        - Apply business logic defaults
        - Return frozen dataclass instance

        Args:
            dto: DTO instance (typically from database or API layer)

        Returns:
            Immutable domain model instance

        Example:
            # LearningStep.from_dto()
            step_dto = LearningStepDTO(uid="ls:...", title="...", ...)
            step = LearningStep.from_dto(step_dto)
            # → LearningStep(frozen=True, with business logic methods)
        """
        ...

    def to_dto(self) -> Any:
        """
        Convert immutable domain model to mutable DTO.

        Standard implementation pattern:
        - Convert tuples to lists (mutability)
        - Extract all model fields
        - Return mutable DTO instance

        Used for:
        - Database updates (need mutable object)
        - API serialization
        - Service layer operations

        Returns:
            Mutable DTO instance,

        Example:
            # LearningStep.to_dto()
            step = LearningStep(uid="ls:...", ...)
            dto = step.to_dto()  # Returns LearningStepDTO (mutable)
            dto.title = "Updated"  # ✅ Can modify
            # step.title = "Updated"  # ❌ FrozenInstanceError
        """
        ...
