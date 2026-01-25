"""
DTO Conversion Helpers
======================

Standalone utility functions for converting between backend data, DTOs, and domain models.

These helpers eliminate repetitive DTO conversion boilerplate across all services.
Services can use these helpers whether or not they inherit from BaseService.

Pattern 3A Fix (2025-10-19):
Uses explicit protocols (DTOConvertible, DomainModelConvertible) for type-safe
generic conversion. This formalizes SKUEL's three-tier type system.

Usage:
    from core.utils.dto_helpers import to_domain_model, to_domain_models

    # Convert single object
    goal = to_domain_model(goal_result.value, GoalDTO, Goal)

    # Convert list
    goals = to_domain_models(goals_result.value, GoalDTO, Goal)
"""

from typing import Any, TypeVar

from core.models.protocols import DomainModelConvertible, DTOConvertible

# Type variables bound to conversion protocols
D = TypeVar("D", bound=DTOConvertible)
M = TypeVar("M", bound=DomainModelConvertible)
T = TypeVar("T")


def to_domain_model[D: DTOConvertible, M: DomainModelConvertible](
    data: Any, dto_class: type[D], model_class: type[M]
) -> M:
    """
    Convert backend data to domain model through DTO layer.

    Type-safe conversion using protocol-bounded generics (Pattern 3A fix).

    Eliminates repetitive DTO conversion boilerplate across all services.
    Handles three common data formats:
    1. Dict from database/backend
    2. DTO object already created
    3. Unknown object with __dict__ attribute

    This pattern appeared 100+ times in the codebase before consolidation.

    Args:
        data: Backend data (dict, DTO, or object),
        dto_class: DTO class implementing DTOConvertible (e.g., TaskDTO, GoalDTO)
        model_class: Domain model class implementing DomainModelConvertible (e.g., Task, Goal)

    Returns:
        Immutable domain model instance,

    Example:
        # Before (repeated everywhere):
        if isinstance(result.value, dict):
            dto = GoalDTO.from_dict(result.value)
        else:
            dto = result.value if isinstance(result.value, GoalDTO) else GoalDTO.from_dict(result.value.__dict__)
        goal = Goal.from_dto(dto)

        # After (single line, type-safe):
        goal = to_domain_model(result.value, GoalDTO, Goal)  # ✅ MyPy validates protocols
    """
    # Handle dict (most common from database)
    if isinstance(data, dict):
        dto = dto_class.from_dict(data)
    # Handle DTO instance
    elif isinstance(data, dto_class):
        dto = data
    # Handle object with __dict__ (fallback)
    else:
        dto = dto_class.from_dict(data.__dict__)

    # Convert DTO to domain model
    return model_class.from_dto(dto)


def to_domain_models[D: DTOConvertible, M: DomainModelConvertible](
    data_list: list[Any], dto_class: type[D], model_class: type[M]
) -> list[M]:
    """
    Convert list of backend data to domain models.

    Type-safe batch conversion using protocol-bounded generics (Pattern 3A fix).

    Batch version of to_domain_model for collections.

    Args:
        data_list: List of backend data,
        dto_class: DTO class implementing DTOConvertible
        model_class: Domain model class implementing DomainModelConvertible

    Returns:
        List of immutable domain model instances,

    Example:
        # Before:
        goals = []
        for goal_data in result.value:
            if isinstance(goal_data, dict):
                dto = GoalDTO.from_dict(goal_data)
            else:
                dto = goal_data if isinstance(goal_data, GoalDTO) else GoalDTO.from_dict(goal_data.__dict__)
            goals.append(Goal.from_dto(dto))

        # After (type-safe):
        goals = to_domain_models(result.value, GoalDTO, Goal)  # ✅ MyPy validates protocols
    """
    return [to_domain_model(data, dto_class, model_class) for data in data_list]


def from_domain_model[T](model: T, dto_class: type) -> Any:
    """
    Convert domain model to DTO for backend operations.

    Reverse conversion for create/update operations.

    Args:
        model: Domain model instance,
        dto_class: DTO class

    Returns:
        DTO instance,

    Example:
        # Before:
        dto = GoalDTO(
            uid=goal.uid,
            title=goal.title,
            ...  # 20+ fields manually mapped
        )

        # After:
        dto = from_domain_model(goal, GoalDTO)
    """
    # Most domain models have .to_dto() method
    to_dto_method = getattr(model, "to_dto", None)
    if to_dto_method:
        return to_dto_method()

    # Fallback: use DTO constructor with model attributes
    model_dict = {k: v for k, v in model.__dict__.items() if not k.startswith("_")}
    return dto_class(**model_dict)


__all__ = [
    "from_domain_model",
    "to_domain_model",
    "to_domain_models",
]
