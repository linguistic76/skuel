"""
DTO Converters - Generic Data Transfer Object Conversion
========================================================

This module provides generic conversion functions between:
- Backend data (dicts, objects) → DTOs → Domain models
- Domain models → DTOs

Extracted from base_service.py to promote reusability in:
- Services (via BaseService wrapper methods)
- Adapters (backend data conversion)
- Tests (mock data conversion)
- Utilities (data transformation pipelines)

Three-Tier Type System (CLAUDE.md):
    External (Pydantic) → Transfer (DTO) → Core (Domain Models)

Philosophy:
- Protocol-based type safety (DTOProtocol, DomainModelProtocol)
- Handle multiple input formats gracefully
- Single source of truth for conversion logic
"""

from __future__ import annotations

from typing import Any

from core.models.protocols import DomainModelProtocol, DTOProtocol


def to_domain_model[D: DTOProtocol, T: DomainModelProtocol](
    data: Any, dto_class: type[D], model_class: type[T]
) -> T:
    """
    Convert backend data to domain model through DTO layer.

    Eliminates repetitive DTO conversion boilerplate across all services.
    Handles three common data formats:
    1. Dict from database/backend
    2. DTO object already created
    3. Unknown object with __dict__ attribute

    This pattern appears 100+ times in the codebase. Single implementation
    ensures consistency and reduces maintenance burden.

    Args:
        data: Backend data (dict, DTO, or object)
        dto_class: DTO class (e.g., TaskDTO, GoalDTO) - must implement DTOProtocol
        model_class: Domain model class (e.g., Task, Goal) - must implement DomainModelProtocol

    Returns:
        Domain model instance (type-safe with protocol constraints)

    Example:
        # Before (repeated everywhere):
        if isinstance(result.value, dict):
            dto = GoalDTO.from_dict(result.value)
        else:
            dto = result.value if isinstance(result.value, GoalDTO) else GoalDTO.from_dict(result.value.__dict__)
        goal = Goal.from_dto(dto)

        # After (single line):
        from core.utils.dto_converters import to_domain_model
        goal = to_domain_model(result.value, GoalDTO, Goal)

    Type Safety:
        Using protocols ensures MyPy can verify:
        - dto_class has from_dict() class method (DTOProtocol)
        - model_class has from_dto() class method (DomainModelProtocol)
        - Return type matches T (domain model type)
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

    # Convert DTO to domain model (type-safe!)
    return model_class.from_dto(dto)


def to_domain_models[D: DTOProtocol, T: DomainModelProtocol](
    data_list: list[Any], dto_class: type[D], model_class: type[T]
) -> list[T]:
    """
    Convert list of backend data to domain models.

    Batch version of to_domain_model for collections.

    Args:
        data_list: List of backend data
        dto_class: DTO class (must implement DTOProtocol)
        model_class: Domain model class (must implement DomainModelProtocol)

    Returns:
        List of domain model instances (type-safe)

    Example:
        # Before:
        goals = []
        for goal_data in result.value:
            if isinstance(goal_data, dict):
                dto = GoalDTO.from_dict(goal_data)
            else:
                dto = goal_data if isinstance(goal_data, GoalDTO) else GoalDTO.from_dict(goal_data.__dict__)
            goals.append(Goal.from_dto(dto))

        # After:
        from core.utils.dto_converters import to_domain_models
        goals = to_domain_models(result.value, GoalDTO, Goal)

    Type Safety:
        Leverages to_domain_model's type safety for each element.
    """
    return [to_domain_model(data, dto_class, model_class) for data in data_list]


def from_domain_model[D: DTOProtocol, T: DomainModelProtocol](model: T, dto_class: type[D]) -> D:
    """
    Convert domain model to DTO for backend operations.

    Reverse conversion for create/update operations.

    Args:
        model: Domain model instance (must implement DomainModelProtocol)
        dto_class: DTO class (must implement DTOProtocol)

    Returns:
        DTO instance

    Example:
        # Before:
        dto = GoalDTO(
            uid=goal.uid,
            title=goal.title,
            ...  # 20+ fields manually mapped
        )

        # After:
        from core.utils.dto_converters import from_domain_model
        dto = from_domain_model(goal, GoalDTO)

    Conversion Strategy:
        1. If model has .to_dto() method, use it (preferred)
        2. Otherwise, construct DTO from model.__dict__ (fallback)
    """
    # Most domain models have .to_dto() method
    to_dto_method = getattr(model, "to_dto", None)
    if to_dto_method:
        return to_dto_method()

    # Fallback: use DTO constructor with model attributes
    model_dict = {k: v for k, v in model.__dict__.items() if not k.startswith("_")}
    return dto_class(**model_dict)
