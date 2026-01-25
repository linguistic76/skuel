"""
Task Converters
===============

Conversion functions between the three tiers of task models:
- External (Pydantic) ↔ Transfer (DTO) ↔ Core (Domain)

Enhanced to preserve knowledge integration data throughout all conversions.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from .task import Task
from .task_dto import TaskDTO
from .task_request import TaskCreateRequest

if TYPE_CHECKING:
    from .task_relationships import TaskRelationships

# ============================================================================
# EXTERNAL → TRANSFER (Request → DTO)
# ============================================================================


def task_create_request_to_dto(request: TaskCreateRequest, user_uid: str) -> TaskDTO:
    """
    Convert TaskCreateRequest to TaskDTO.

    Args:
        request: Validated external request
        user_uid: User UID (from authentication context)

    Returns:
        DTO ready for service operations with knowledge fields preserved
    """
    return TaskDTO.create(
        user_uid=user_uid,
        title=request.title,
        priority=request.priority,
        due_date=request.due_date,
        duration_minutes=request.duration_minutes,
        project=request.project,
        tags=request.tags or [],
    )


# NOTE: task_update_request_to_dto_updates() removed - use generic helper directly:
#   - from core.utils.converter_helpers import update_request_to_dict
#   - updates = update_request_to_dict(request)
#
# This eliminates domain-specific wrappers in favor of the generic pattern.
# The helper works for ANY domain's update request (Pydantic BaseModel).


# ============================================================================
# TRANSFER ↔ CORE (DTO ↔ Domain)
# ============================================================================
# NOTE: Wrapper functions removed - use model methods directly:
#   - Task.from_dto(dto) instead of task_dto_to_domain(dto)
#   - task.to_dto() instead of task_domain_to_dto(task)


# ============================================================================
# EXTERNAL → CORE (Direct conversion for read operations)
# ============================================================================


def task_create_request_to_domain(request: TaskCreateRequest, user_uid: str) -> Task:
    """
    Direct conversion from create request to domain model.
    Useful for operations that don't need intermediate DTO manipulation.

    Args:
        request: Validated external request
        user_uid: User UID (from authentication context)

    Returns:
        Immutable domain model with knowledge integration
    """
    dto = task_create_request_to_dto(request, user_uid)
    return Task.from_dto(dto)


# ============================================================================
# DATABASE OPERATIONS (Dict ↔ DTO) - Knowledge Enhanced
# ============================================================================


def task_dict_to_dto(data: dict[str, Any]) -> TaskDTO:
    """
    Convert dictionary (from database) to TaskDTO.
    Enhanced to preserve all knowledge tracking fields.

    Args:
        data: Raw dictionary from database/Neo4j with knowledge data,

    Returns:
        DTO with parsed and validated data including knowledge enhancements
    """
    # Validate and clean knowledge data before conversion
    validated_data = validate_task_knowledge_data(data)
    return TaskDTO.from_dict(validated_data)


# NOTE: task_dto_to_dict() removed - use dto.to_dict() directly


# ============================================================================
# KNOWLEDGE ENHANCEMENT OPERATIONS
# ============================================================================


def enrich_task_dto_with_knowledge_inference(
    dto: TaskDTO, inference_data: dict[str, Any]
) -> TaskDTO:
    """
    Add inferred knowledge data to a task DTO.

    Args:
        dto: Task DTO to enhance,
        inference_data: Knowledge inference results

    Returns:
        DTO with enriched knowledge data
    """
    # NOTE: inferred_knowledge_uids removed from TaskDTO (graph-native)
    # This is now a graph relationship: (task)-[:INFERS_KNOWLEDGE]->(ku)
    # Query via: service.relationships.get_task_inferred_knowledge()
    # if 'inferred_knowledge_uids' in inference_data:
    #     dto.inferred_knowledge_uids = inference_data['inferred_knowledge_uids']

    # Add confidence scores
    if "knowledge_confidence_scores" in inference_data:
        dto.knowledge_confidence_scores.update(inference_data["knowledge_confidence_scores"])

    # Add detected patterns
    if "knowledge_patterns_detected" in inference_data:
        dto.knowledge_patterns_detected = inference_data["knowledge_patterns_detected"]

    # Add learning opportunities count
    if "learning_opportunities_count" in inference_data:
        dto.learning_opportunities_count = inference_data["learning_opportunities_count"]

    # Add inference metadata
    if "inference_metadata" in inference_data:
        dto.knowledge_inference_metadata.update(inference_data["inference_metadata"])

    # Update timestamp
    dto.updated_at = datetime.now()

    return dto


def extract_knowledge_summary_from_task(
    task: Task, rels: "TaskRelationships | None" = None
) -> dict[str, Any]:
    """
    Extract knowledge integration summary from a task.

    Args:
        task: Domain model with knowledge data
        rels: Optional task relationships (required for graph-aware calculations)

    Returns:
        Summary dictionary with knowledge metrics
    """
    # GRAPH-NATIVE: Knowledge UIDs come from rels, not task fields
    summary = {
        "uid": task.uid,
        "title": task.title,
        "explicit_knowledge_count": len(rels.applies_knowledge_uids) if rels else 0,
        "prerequisite_knowledge_count": len(rels.prerequisite_knowledge_uids) if rels else 0,
        "goal_progress_contribution": task.goal_progress_contribution,
        "knowledge_mastery_check": task.knowledge_mastery_check,
        "knowledge_integration_level": _calculate_knowledge_integration_level(task, rels),
    }

    # Add relationship-dependent fields only if rels provided
    if rels is not None:
        summary["knowledge_complexity_score"] = task.calculate_knowledge_complexity(rels)
        summary["learning_impact_score"] = task.calculate_learning_impact(rels)
        summary["knowledge_bridge_status"] = task.is_knowledge_bridge(rels)
        summary["mastery_validation_task"] = task.validates_knowledge_mastery()

    return summary


def _calculate_knowledge_integration_level(
    task: Task, rels: "TaskRelationships | None" = None
) -> str:
    """
    Calculate the level of knowledge integration for a task.

    Args:
        task: Domain model
        rels: Optional task relationships (for enhanced analysis)

    Returns:
        Integration level: 'basic', 'moderate', 'advanced', 'expert'
    """
    # GRAPH-NATIVE: Count explicit knowledge connections from rels
    if rels:
        explicit_count = len(rels.applies_knowledge_uids) + len(rels.prerequisite_knowledge_uids)
    else:
        explicit_count = 0  # No relationship data available

    # Factor in progress contribution and mastery checking
    has_goal_impact = task.goal_progress_contribution > 0.3
    has_mastery_check = task.knowledge_mastery_check
    # Note: Line removed - was dead code (task.is_knowledge_bridge() call with no assignment)

    if explicit_count == 0:
        return "basic"
    elif explicit_count <= 2 and not (has_goal_impact or has_mastery_check):
        return "moderate"
    elif explicit_count <= 4 or (explicit_count <= 2 and (has_goal_impact or has_mastery_check)):
        return "advanced"
    else:
        return "expert"


# ============================================================================
# BULK OPERATIONS - Knowledge Enhanced
# ============================================================================


def task_create_requests_to_dtos(requests: list[TaskCreateRequest], user_uid: str) -> list[TaskDTO]:
    """
    Convert multiple create requests to DTOs.

    Args:
        requests: List of validated external requests
        user_uid: User UID (from authentication context)

    Returns:
        List of DTOs ready for bulk operations
    """
    return [task_create_request_to_dto(request, user_uid) for request in requests]


def task_dtos_to_domains(dtos: list[TaskDTO]) -> list[Task]:
    """
    Convert multiple DTOs to domain models.

    Args:
        dtos: List of transfer objects with knowledge data,

    Returns:
        List of immutable domain models with preserved knowledge
    """
    return [Task.from_dto(dto) for dto in dtos]


def task_dicts_to_domains(dicts: list[dict[str, Any]]) -> list[Task]:
    """
    Convert multiple dictionaries directly to domain models.
    Useful for bulk database read operations.

    Args:
        dicts: List of raw dictionaries from database with knowledge data,

    Returns:
        List of immutable domain models with knowledge preservation
    """
    dtos = [task_dict_to_dto(data) for data in dicts]
    return task_dtos_to_domains(dtos)


# ============================================================================
# VALIDATION AND ERROR HANDLING - Knowledge Enhanced
# ============================================================================


def validate_task_knowledge_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and clean task data with knowledge enhancements before conversion.

    Uses generic validation helpers from validation_helpers.py.

    Args:
        data: Raw data dictionary with potential knowledge fields,

    Returns:
        Cleaned and validated data with knowledge preservation

    Raises:
        ValueError: If data is invalid
    """
    from core.utils.validation_helpers import (
        ensure_list_fields,
        ensure_metadata_dicts,
        parse_date_fields,
        parse_datetime_fields,
        validate_confidence_scores,
        validate_numeric_range,
        validate_required_fields,
    )

    # Validate required fields
    validate_required_fields(data, ["uid", "title"])

    # Validate knowledge UID lists
    ensure_list_fields(
        data,
        [
            "applies_knowledge_uids",
            "prerequisite_knowledge_uids",
            "aligned_principle_uids",
            "enables_task_uids",
            "completion_triggers_tasks",
            "completion_unlocks_knowledge",
            "inferred_knowledge_uids",
            "knowledge_patterns_detected",
        ],
    )

    # Validate knowledge confidence scores (0-1 range)
    validate_confidence_scores(data)

    # Validate progress contribution (0-1 range)
    validate_numeric_range(data, "goal_progress_contribution", 0.0, 1.0)

    # Validate learning opportunities count (non-negative)
    if "learning_opportunities_count" in data and data["learning_opportunities_count"] is not None:
        count = data["learning_opportunities_count"]
        if not isinstance(count, int) or count < 0:
            raise ValueError("learning_opportunities_count must be a non-negative integer")

    # Ensure metadata fields are dictionaries
    ensure_metadata_dicts(data, ["knowledge_inference_metadata", "metadata"])

    # Parse date and datetime fields
    parse_date_fields(
        data, ["due_date", "scheduled_date", "completion_date", "recurrence_end_date"]
    )
    parse_datetime_fields(data, ["created_at", "updated_at"])

    return data


# ============================================================================
# ENHANCED METADATA OPERATIONS
# ============================================================================


def enrich_task_dto_with_metadata(dto: TaskDTO, metadata: dict[str, Any]) -> TaskDTO:
    """
    Add metadata to a task DTO while preserving knowledge data.

    Args:
        dto: Task DTO to enrich,
        metadata: Additional metadata to add

    Returns:
        DTO with enriched metadata and preserved knowledge
    """
    dto.metadata.update(metadata)
    dto.updated_at = datetime.now()
    return dto


def merge_knowledge_confidence_scores(dto: TaskDTO, new_scores: dict[str, float]) -> TaskDTO:
    """
    Merge new confidence scores with existing ones.

    Args:
        dto: Task DTO to update,
        new_scores: New confidence scores to merge

    Returns:
        DTO with updated confidence scores
    """
    # Merge with higher confidence scores taking precedence
    for uid, new_score in new_scores.items():
        existing_score = dto.knowledge_confidence_scores.get(uid, 0.0)
        dto.knowledge_confidence_scores[uid] = max(existing_score, new_score)

    dto.updated_at = datetime.now()
    return dto
