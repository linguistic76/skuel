"""
LearningStep Converters
=======================

Conversion functions between three-tier LearningStep models.

Flow:
1. Request (Pydantic) → DTO (mutable)
2. DTO → Pure (immutable)
3. Pure → DTO (for updates)
4. Pure → Response (for API)
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from .ls import LearningStep
from .ls_dto import LearningStepDTO
from .ls_request import LearningStepCreateRequest, LearningStepResponse, LearningStepUpdateRequest

if TYPE_CHECKING:
    from .ls_relationships import LsRelationships

# =============================================================================
# TIER 1 → TIER 2: Request → DTO
# =============================================================================


def ls_create_request_to_dto(request: LearningStepCreateRequest) -> LearningStepDTO:
    """
    Convert create request to DTO.

    Generates UID if not provided.

    Phase 3 Graph-Native: Relationship fields (prerequisite_step_uids, principle_uids,
    habit_uids, etc.) are NOT copied to DTO. Create relationships via
    UnifiedRelationshipService after entity creation.
    """
    uid = request.uid or f"ls:{uuid.uuid4().hex[:12]}"

    return LearningStepDTO(
        uid=uid,
        title=request.title,
        intent=request.intent,
        description=request.description,
        primary_knowledge_uids=request.primary_knowledge_uids.copy(),
        supporting_knowledge_uids=request.supporting_knowledge_uids.copy(),
        learning_path_uid=request.learning_path_uid,
        sequence=request.sequence,
        # Phase 3: Relationship fields removed from DTO - create via relationship service
        mastery_threshold=request.mastery_threshold,
        estimated_hours=request.estimated_hours,
        difficulty=request.difficulty,
        domain=request.domain,
        priority=request.priority,
        notes=request.notes,
        tags=request.tags.copy(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def ls_update_request_to_dto(
    existing_dto: LearningStepDTO, request: LearningStepUpdateRequest
) -> LearningStepDTO:
    """
    Apply update request to existing DTO.

    Only updates fields that are provided in the request.

    Phase 3 Graph-Native: Relationship fields (prerequisite_step_uids, principle_uids,
    habit_uids, etc.) are NOT in DTO. Update relationships via
    UnifiedRelationshipService separately.
    """
    # Create a copy of the existing DTO
    updated = LearningStepDTO(
        uid=existing_dto.uid,
        title=request.title if request.title is not None else existing_dto.title,
        intent=request.intent if request.intent is not None else existing_dto.intent,
        description=request.description
        if request.description is not None
        else existing_dto.description,
        primary_knowledge_uids=(
            request.primary_knowledge_uids.copy()
            if request.primary_knowledge_uids is not None
            else existing_dto.primary_knowledge_uids.copy()
        ),
        supporting_knowledge_uids=(
            request.supporting_knowledge_uids.copy()
            if request.supporting_knowledge_uids is not None
            else existing_dto.supporting_knowledge_uids.copy()
        ),
        learning_path_uid=(
            request.learning_path_uid
            if request.learning_path_uid is not None
            else existing_dto.learning_path_uid
        ),
        sequence=request.sequence if request.sequence is not None else existing_dto.sequence,
        # Phase 3: Relationship fields removed from DTO - update via relationship service
        mastery_threshold=(
            request.mastery_threshold
            if request.mastery_threshold is not None
            else existing_dto.mastery_threshold
        ),
        current_mastery=(
            request.current_mastery
            if request.current_mastery is not None
            else existing_dto.current_mastery
        ),
        estimated_hours=(
            request.estimated_hours
            if request.estimated_hours is not None
            else existing_dto.estimated_hours
        ),
        difficulty=request.difficulty
        if request.difficulty is not None
        else existing_dto.difficulty,
        status=request.status if request.status is not None else existing_dto.status,
        completed=request.completed if request.completed is not None else existing_dto.completed,
        completed_at=existing_dto.completed_at,  # Managed separately
        domain=request.domain if request.domain is not None else existing_dto.domain,
        priority=request.priority if request.priority is not None else existing_dto.priority,
        created_at=existing_dto.created_at,
        updated_at=datetime.now(),
        notes=request.notes if request.notes is not None else existing_dto.notes,
        tags=request.tags.copy() if request.tags is not None else existing_dto.tags.copy(),
    )

    # Handle completion timestamp
    if request.completed and not existing_dto.completed:
        updated.completed_at = datetime.now()

    return updated


# =============================================================================
# TIER 2 → TIER 3: DTO → Pure
# =============================================================================


def ls_dto_to_pure(dto: LearningStepDTO) -> LearningStep:
    """
    Convert DTO to immutable pure domain model.

    Converts lists to tuples for immutability.
    """
    return LearningStep.from_dto(dto)


# =============================================================================
# TIER 3 → TIER 2: Pure → DTO
# =============================================================================


def ls_pure_to_dto(pure: LearningStep) -> LearningStepDTO:
    """
    Convert pure domain model back to DTO.

    Used for updates or further processing.
    """
    return pure.to_dto()


# =============================================================================
# TIER 3 → RESPONSE: Pure → API Response
# =============================================================================


def ls_pure_to_response(
    pure: LearningStep,
    rels: "LsRelationships | None" = None,
    completed_step_uids: set[str] | None = None,
) -> LearningStepResponse:
    """
    Convert pure domain model to API response.

    Includes computed fields for client convenience.

    Args:
        pure: Pure LearningStep model
        rels: Relationship data (required for relationship fields)
        completed_step_uids: Set of completed step UIDs for readiness check

    Returns:
        LearningStepResponse for API
    """
    if completed_step_uids is None:
        completed_step_uids = set()

    return LearningStepResponse(
        uid=pure.uid,
        title=pure.title,
        intent=pure.intent,
        description=pure.description,
        primary_knowledge_uids=list(pure.primary_knowledge_uids),
        supporting_knowledge_uids=list(pure.supporting_knowledge_uids),
        learning_path_uid=pure.learning_path_uid,
        sequence=pure.sequence,
        prerequisite_step_uids=list(rels.prerequisite_step_uids) if rels else [],
        prerequisite_knowledge_uids=list(rels.prerequisite_knowledge_uids) if rels else [],
        principle_uids=list(rels.principle_uids) if rels else [],
        choice_uids=list(rels.choice_uids) if rels else [],
        habit_uids=list(rels.habit_uids) if rels else [],
        task_uids=list(rels.task_uids) if rels else [],
        event_template_uids=list(rels.event_template_uids) if rels else [],
        mastery_threshold=pure.mastery_threshold,
        current_mastery=pure.current_mastery,
        estimated_hours=pure.estimated_hours,
        difficulty=pure.difficulty,
        status=pure.status,
        completed=pure.completed,
        completed_at=pure.completed_at,
        domain=pure.domain,
        priority=pure.priority,
        created_at=pure.created_at,
        updated_at=pure.updated_at,
        notes=pure.notes,
        tags=list(pure.tags),
        # Computed fields
        progress_percentage=pure.progress_percentage(),
        is_ready=True,  # Placeholder - readiness requires graph query via LsRelationshipService.is_ready()
        is_mastered=pure.is_mastered(),
    )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def ls_request_to_pure(request: LearningStepCreateRequest) -> LearningStep:
    """
    Direct conversion from request to pure model.

    Flow: Request → DTO → Pure
    """
    dto = ls_create_request_to_dto(request)
    return ls_dto_to_pure(dto)


def ls_pure_to_dict(pure: LearningStep, rels: "LsRelationships | None" = None) -> dict:
    """
    Convert pure model to dictionary.

    Args:
        pure: Pure LearningStep model
        rels: Relationship data (required for relationship fields)

    Useful for serialization and logging.
    """
    return {
        "uid": pure.uid,
        "title": pure.title,
        "intent": pure.intent,
        "description": pure.description,
        "primary_knowledge_uids": list(pure.primary_knowledge_uids),
        "supporting_knowledge_uids": list(pure.supporting_knowledge_uids),
        "learning_path_uid": pure.learning_path_uid,
        "sequence": pure.sequence,
        "prerequisite_step_uids": list(rels.prerequisite_step_uids) if rels else [],
        "prerequisite_knowledge_uids": list(rels.prerequisite_knowledge_uids) if rels else [],
        "principle_uids": list(rels.principle_uids) if rels else [],
        "choice_uids": list(rels.choice_uids) if rels else [],
        "habit_uids": list(rels.habit_uids) if rels else [],
        "task_uids": list(rels.task_uids) if rels else [],
        "event_template_uids": list(rels.event_template_uids) if rels else [],
        "mastery_threshold": pure.mastery_threshold,
        "current_mastery": pure.current_mastery,
        "estimated_hours": pure.estimated_hours,
        "difficulty": pure.difficulty.value,
        "status": pure.status.value,
        "completed": pure.completed,
        "completed_at": pure.completed_at.isoformat() if pure.completed_at else None,
        "domain": pure.domain.value,
        "priority": pure.priority.value,
        "created_at": pure.created_at.isoformat() if pure.created_at else None,
        "updated_at": pure.updated_at.isoformat() if pure.updated_at else None,
        "notes": pure.notes,
        "tags": list(pure.tags),
    }
