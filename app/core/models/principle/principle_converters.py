"""
Principle Converters
====================

Conversion functions between the three tiers of principle models:
- External (Pydantic) ↔ Transfer (DTO) ↔ Core (Domain)

Preserves principle alignment data, expressions, and cross-domain relationships
throughout all conversions.
"""

from typing import Any

from .principle import Principle
from .principle_dto import PrincipleDTO

# ============================================================================
# TRANSFER ↔ CORE (DTO ↔ Domain)
# ============================================================================


def principle_dto_to_pure(dto: PrincipleDTO) -> Principle:
    """
    Convert PrincipleDTO to Principle domain model.

    Args:
        dto: Transfer object with full principle data

    Returns:
        Immutable domain model with business logic and alignment data preserved
    """
    return Principle.from_dto(dto)


def principle_pure_to_dto(principle: Principle) -> PrincipleDTO:
    """
    Convert Principle domain model to PrincipleDTO.

    Args:
        principle: Domain model

    Returns:
        Mutable DTO for transfer operations with alignment data preserved
    """
    return principle.to_dto()


# Aliases for consistency with other domains
principle_dto_to_domain = principle_dto_to_pure
principle_domain_to_dto = principle_pure_to_dto


# ============================================================================
# DATABASE OPERATIONS (Dict ↔ DTO)
# ============================================================================


def principle_dict_to_dto(data: dict[str, Any]) -> PrincipleDTO:
    """
    Convert dictionary (from database) to PrincipleDTO.
    Preserves all principle alignment and expression fields.

    Args:
        data: Raw dictionary from database/Neo4j with principle data

    Returns:
        DTO with parsed and validated data
    """
    # Validate and normalize data before conversion
    validated_data = validate_principle_data(data)
    return PrincipleDTO.from_dict(validated_data)


def principle_dto_to_dict(dto: PrincipleDTO) -> dict[str, Any]:
    """
    Convert PrincipleDTO to dictionary for database storage.
    Includes all principle fields.

    Args:
        dto: Transfer object with principle data

    Returns:
        Dictionary ready for database operations
    """
    return dto.to_dict()


# ============================================================================
# BULK OPERATIONS
# ============================================================================


def principle_dtos_to_domains(dtos: list[PrincipleDTO]) -> list[Principle]:
    """
    Convert multiple DTOs to domain models.

    Args:
        dtos: List of transfer objects

    Returns:
        List of immutable domain models
    """
    return [principle_dto_to_pure(dto) for dto in dtos]


def principle_domains_to_dtos(principles: list[Principle]) -> list[PrincipleDTO]:
    """
    Convert multiple domain models to DTOs.

    Args:
        principles: List of domain models

    Returns:
        List of mutable DTOs
    """
    return [principle_pure_to_dto(principle) for principle in principles]


def principle_dicts_to_dtos(dicts: list[dict[str, Any]]) -> list[PrincipleDTO]:
    """
    Convert multiple dictionaries to DTOs.

    Args:
        dicts: List of raw dictionaries from database

    Returns:
        List of DTOs with parsed data
    """
    return [principle_dict_to_dto(d) for d in dicts]


def principle_dicts_to_domains(dicts: list[dict[str, Any]]) -> list[Principle]:
    """
    Convert multiple dictionaries directly to domain models.
    Useful for bulk database read operations.

    Args:
        dicts: List of raw dictionaries from database

    Returns:
        List of immutable domain models
    """
    dtos = [principle_dict_to_dto(data) for data in dicts]
    return principle_dtos_to_domains(dtos)


# ============================================================================
# VALIDATION HELPERS
# ============================================================================


def validate_principle_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and normalize principle data.

    Uses generic validation helpers from validation_helpers.py.
    Note: This validator is more permissive than others - uses defaults instead of raising errors.

    Args:
        data: Raw dictionary with potentially inconsistent data

    Returns:
        Validated dictionary with normalized data
    """
    from core.utils.validation_helpers import ensure_list_fields

    validated = data.copy()

    # Ensure list fields using generic helper
    ensure_list_fields(
        validated,
        [
            "expressions",
            "key_behaviors",
            "decision_criteria",
            "alignment_history",
            "potential_conflicts",
            "conflicting_principles",
            "resolution_strategies",
            "tags",
        ],
    )

    # Ensure numeric fields are correct type (with defaults)
    if "current_alignment" in validated and validated["current_alignment"] is not None:
        try:
            validated["current_alignment"] = float(validated["current_alignment"])
        except (ValueError, TypeError):
            validated["current_alignment"] = 0.0

    if "priority" in validated and validated["priority"] is not None:
        try:
            validated["priority"] = int(validated["priority"])
        except (ValueError, TypeError):
            validated["priority"] = 1

    # Ensure boolean fields
    if "is_active" in validated:
        validated["is_active"] = bool(validated["is_active"])

    # Ensure datetime fields (permissive - defaults to None on error)
    from datetime import date, datetime

    date_fields = ["last_review_date", "adopted_date"]
    for field in date_fields:
        if field in validated and isinstance(validated[field], str):
            try:
                validated[field] = date.fromisoformat(validated[field])
            except ValueError:
                validated[field] = None

    datetime_fields = ["created_at", "updated_at"]
    for field in datetime_fields:
        if field in validated and isinstance(validated[field], str):
            try:
                validated[field] = datetime.fromisoformat(validated[field])
            except ValueError:
                validated[field] = None

    return validated


# ============================================================================
# ALIGNMENT ANALYSIS HELPERS
# ============================================================================


def extract_alignment_summary(principle: Principle) -> dict[str, Any]:
    """
    Extract alignment summary from a principle.

    Args:
        principle: Domain model with alignment data

    Returns:
        Summary dictionary with alignment metrics
    """
    return {
        "uid": principle.uid,
        "title": principle.title,
        "category": principle.category.value,
        "strength": principle.strength.value,
        "current_alignment": principle.current_alignment,
        "alignment_trend": _calculate_alignment_trend(principle),
        "expression_count": len(principle.expressions),
        "behavior_count": len(principle.key_behaviors),
        "decision_criteria_count": len(principle.decision_criteria),
        "assessment_count": len(principle.alignment_history),
        "has_conflicts": len(principle.potential_conflicts) > 0,
        "conflict_count": len(principle.conflicting_principles),
        "is_active": principle.is_active,
        "priority": principle.priority,
    }


def _calculate_alignment_trend(principle: Principle) -> str:
    """
    Calculate alignment trend based on history.

    Args:
        principle: Domain model

    Returns:
        Trend: 'improving', 'stable', 'declining', 'unknown'
    """
    if len(principle.alignment_history) < 2:
        return "unknown"

    # Get last two assessments
    recent = principle.alignment_history[-2:]
    older_alignment = recent[0].alignment_level
    newer_alignment = recent[1].alignment_level

    if newer_alignment > older_alignment:
        return "improving"
    elif newer_alignment < older_alignment:
        return "declining"
    else:
        return "stable"


def extract_expression_summary(principle: Principle) -> dict[str, Any]:
    """
    Extract principle expression summary.

    Args:
        principle: Domain model

    Returns:
        Expression summary dictionary
    """
    return {
        "uid": principle.uid,
        "title": principle.title,
        "statement": principle.statement,
        "expressions": [
            {
                "context": expr.context,
                "behavior": expr.behavior,
                "example": expr.example,
            }
            for expr in principle.expressions
        ],
        "key_behaviors": list(principle.key_behaviors),
        "decision_criteria": list(principle.decision_criteria),
        "expression_count": len(principle.expressions),
    }
