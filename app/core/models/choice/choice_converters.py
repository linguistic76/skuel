"""
Choice Converter Functions
==========================

Conversion functions between the three tiers of the choice domain.
Handles transformation between Pydantic models, DTOs, and domain models.
"""

import uuid
from datetime import datetime

from core.models.choice.choice import Choice, ChoiceOption, ChoiceStatus, ChoiceType
from core.models.choice.choice_dto import (
    ChoiceCreateDTO,
    ChoiceDecisionDTO,
    ChoiceDTO,
    ChoiceEvaluationDTO,
    ChoiceOptionDTO,
    ChoiceUpdateDTO,
)
from core.models.choice.choice_request import (
    ChoiceCreateRequest,
    ChoiceDecisionRequest,
    ChoiceEvaluationRequest,
    ChoiceOptionCreateRequest,
    ChoiceOptionResponse,
    ChoiceResponse,
    ChoiceUpdateRequest,
)
from core.models.enums import Domain, Priority

# =============================================================================
# Choice Option Converters
# =============================================================================


def choice_option_create_request_to_dto(
    request: ChoiceOptionCreateRequest, _choice_uid: str
) -> ChoiceOptionDTO:
    """Convert ChoiceOptionCreateRequest to ChoiceOptionDTO."""
    return ChoiceOptionDTO(
        uid=f"opt_{uuid.uuid4().hex[:12]}",
        title=request.title,
        description=request.description,
        feasibility_score=request.feasibility_score,
        risk_level=request.risk_level,
        potential_impact=request.potential_impact,
        resource_requirement=request.resource_requirement,
        estimated_duration=request.estimated_duration,
        dependencies=request.dependencies.copy(),
        tags=request.tags.copy(),
    )


def choice_option_dto_to_domain(dto: ChoiceOptionDTO) -> ChoiceOption:
    """Convert ChoiceOptionDTO to ChoiceOption domain model."""
    return ChoiceOption(
        uid=dto.uid,
        title=dto.title,
        description=dto.description,
        feasibility_score=dto.feasibility_score,
        risk_level=dto.risk_level,
        potential_impact=dto.potential_impact,
        resource_requirement=dto.resource_requirement,
        estimated_duration=dto.estimated_duration,
        dependencies=tuple(dto.dependencies),
        tags=tuple(dto.tags),
    )


def choice_option_domain_to_dto(domain: ChoiceOption) -> ChoiceOptionDTO:
    """Convert ChoiceOption domain model to ChoiceOptionDTO."""
    return ChoiceOptionDTO(
        uid=domain.uid,
        title=domain.title,
        description=domain.description,
        feasibility_score=domain.feasibility_score,
        risk_level=domain.risk_level,
        potential_impact=domain.potential_impact,
        resource_requirement=domain.resource_requirement,
        estimated_duration=domain.estimated_duration,
        dependencies=list(domain.dependencies),
        tags=list(domain.tags),
    )


def choice_option_dto_to_response(dto: ChoiceOptionDTO) -> ChoiceOptionResponse:
    """Convert ChoiceOptionDTO to ChoiceOptionResponse."""
    return ChoiceOptionResponse(
        uid=dto.uid,
        title=dto.title,
        description=dto.description,
        feasibility_score=dto.feasibility_score,
        risk_level=dto.risk_level,
        potential_impact=dto.potential_impact,
        resource_requirement=dto.resource_requirement,
        estimated_duration=dto.estimated_duration,
        dependencies=dto.dependencies,
        tags=dto.tags,
    )


# =============================================================================
# Choice Converters
# =============================================================================


def choice_create_request_to_dto(request: ChoiceCreateRequest, user_uid: str) -> ChoiceCreateDTO:
    """Convert ChoiceCreateRequest to ChoiceCreateDTO."""
    return ChoiceCreateDTO(
        title=request.title,
        description=request.description,
        user_uid=user_uid,
        choice_type=request.choice_type.value,
        priority=request.priority.value,
        domain=request.domain.value,
        decision_deadline=request.decision_deadline,
        decision_criteria=request.decision_criteria.copy(),
        constraints=request.constraints.copy(),
        stakeholders=request.stakeholders.copy(),
    )


def choice_create_dto_to_dto(create_dto: ChoiceCreateDTO) -> ChoiceDTO:
    """Convert ChoiceCreateDTO to full ChoiceDTO."""
    return ChoiceDTO(
        uid=f"choice_{uuid.uuid4().hex[:12]}",
        title=create_dto.title,
        description=create_dto.description,
        user_uid=create_dto.user_uid,
        choice_type=create_dto.choice_type,
        priority=create_dto.priority,
        domain=create_dto.domain,
        decision_deadline=create_dto.decision_deadline,
        decision_criteria=create_dto.decision_criteria.copy(),
        constraints=create_dto.constraints.copy(),
        stakeholders=create_dto.stakeholders.copy(),
        created_at=datetime.now(),
    )


def choice_dto_to_domain(dto: ChoiceDTO) -> Choice:
    """Convert ChoiceDTO to Choice domain model."""
    # Convert options
    options = tuple(choice_option_dto_to_domain(opt) for opt in dto.options)

    return Choice(
        uid=dto.uid,
        title=dto.title,
        description=dto.description,
        user_uid=dto.user_uid,
        choice_type=ChoiceType(dto.choice_type),
        status=ChoiceStatus(dto.status),
        priority=Priority(dto.priority),
        domain=Domain(dto.domain),
        options=options,
        selected_option_uid=dto.selected_option_uid,
        decision_rationale=dto.decision_rationale,
        decision_criteria=tuple(dto.decision_criteria),
        constraints=tuple(dto.constraints),
        stakeholders=tuple(dto.stakeholders),
        decision_deadline=dto.decision_deadline,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
        decided_at=dto.decided_at,
        satisfaction_score=dto.satisfaction_score,
        actual_outcome=dto.actual_outcome,
        lessons_learned=tuple(dto.lessons_learned),
        # Curriculum Integration - REMOVED: These are Neo4j graph relationships, not dataclass fields
        # informed_by_knowledge_uids, opens_learning_paths, requires_knowledge_for_decision, aligned_with_principles
        # are stored as graph edges, not Choice model fields
        # Inspiration
        inspiration_type=dto.inspiration_type,
        expands_possibilities=dto.expands_possibilities,
        vision_statement=dto.vision_statement,
        metadata=getattr(dto, "metadata", {})
        or {},  # Copy metadata from DTO (rich context storage)
    )


def choice_domain_to_dto(domain: Choice) -> ChoiceDTO:
    """Convert Choice domain model to ChoiceDTO."""
    # Convert options
    options = [choice_option_domain_to_dto(opt) for opt in domain.options]

    # Calculate computed fields
    complexity_score = domain.calculate_decision_complexity()
    time_until_deadline = domain.time_until_deadline()
    is_overdue = domain.is_overdue()
    inspiration_strength = domain.calculate_inspiration_strength()

    return ChoiceDTO(
        uid=domain.uid,
        title=domain.title,
        description=domain.description,
        user_uid=domain.user_uid,
        choice_type=domain.choice_type.value,
        status=domain.status.value,
        priority=domain.priority.value,
        domain=domain.domain.value,
        options=options,
        selected_option_uid=domain.selected_option_uid,
        decision_rationale=domain.decision_rationale,
        decision_criteria=list(domain.decision_criteria),
        constraints=list(domain.constraints),
        stakeholders=list(domain.stakeholders),
        decision_deadline=domain.decision_deadline,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
        decided_at=domain.decided_at,
        satisfaction_score=domain.satisfaction_score,
        actual_outcome=domain.actual_outcome,
        lessons_learned=list(domain.lessons_learned),
        # Inspiration
        inspiration_type=domain.inspiration_type,
        expands_possibilities=domain.expands_possibilities,
        vision_statement=domain.vision_statement,
        # Computed fields
        complexity_score=complexity_score,
        time_until_deadline_minutes=time_until_deadline,
        is_overdue=is_overdue,
        inspiration_strength=inspiration_strength,
        metadata=domain.metadata,  # Copy metadata to DTO (rich context storage)
    )


def choice_dto_to_response(dto: ChoiceDTO) -> ChoiceResponse:
    """Convert ChoiceDTO to ChoiceResponse."""
    return ChoiceResponse(
        uid=dto.uid,
        title=dto.title,
        description=dto.description,
        user_uid=dto.user_uid,
        choice_type=dto.choice_type,
        status=dto.status,
        priority=dto.priority,
        domain=dto.domain,
        selected_option_uid=dto.selected_option_uid,
        decision_rationale=dto.decision_rationale,
        decision_criteria=dto.decision_criteria,
        constraints=dto.constraints,
        stakeholders=dto.stakeholders,
        decision_deadline=dto.decision_deadline,
        created_at=dto.created_at,
        decided_at=dto.decided_at,
        satisfaction_score=dto.satisfaction_score,
        actual_outcome=dto.actual_outcome,
        lessons_learned=dto.lessons_learned,
        complexity_score=dto.complexity_score,
        time_until_deadline_minutes=dto.time_until_deadline_minutes,
        is_overdue=dto.is_overdue,
    )


# =============================================================================
# Update and Action Converters
# =============================================================================


def choice_update_request_to_dto(request: ChoiceUpdateRequest, choice_uid: str) -> ChoiceUpdateDTO:
    """Convert ChoiceUpdateRequest to ChoiceUpdateDTO."""
    return ChoiceUpdateDTO(
        uid=choice_uid,
        title=request.title,
        description=request.description,
        choice_type=request.choice_type.value if request.choice_type else None,
        priority=request.priority.value if request.priority else None,
        domain=request.domain.value if request.domain else None,
        status=request.status.value if request.status else None,
        decision_deadline=request.decision_deadline,
        # Note: decision_criteria, constraints, stakeholders are not in ChoiceUpdateDTO
    )


def choice_decision_request_to_dto(
    request: ChoiceDecisionRequest, choice_uid: str
) -> ChoiceDecisionDTO:
    """Convert ChoiceDecisionRequest to ChoiceDecisionDTO."""
    return ChoiceDecisionDTO(
        choice_uid=choice_uid,
        selected_option_uid=request.selected_option_uid,
        decision_rationale=request.decision_rationale,
        decided_at=request.decided_at or datetime.now(),
    )


def choice_evaluation_request_to_dto(
    request: ChoiceEvaluationRequest, choice_uid: str
) -> ChoiceEvaluationDTO:
    """Convert ChoiceEvaluationRequest to ChoiceEvaluationDTO."""
    return ChoiceEvaluationDTO(
        choice_uid=choice_uid,
        satisfaction_score=request.satisfaction_score,
        actual_outcome=request.actual_outcome,
        lessons_learned=request.lessons_learned.copy(),
    )


# =============================================================================
# Batch Converters
# =============================================================================


def choice_domains_to_responses(domains: list[Choice]) -> list[ChoiceResponse]:
    """Convert list of Choice domain models to ChoiceResponse list."""
    return [choice_dto_to_response(choice_domain_to_dto(domain)) for domain in domains]


def choice_dtos_to_responses(dtos: list[ChoiceDTO]) -> list[ChoiceResponse]:
    """Convert list of ChoiceDTOs to ChoiceResponse list."""
    return [choice_dto_to_response(dto) for dto in dtos]


# =============================================================================
# Helper Functions
# =============================================================================


def apply_choice_update_to_dto(dto: ChoiceDTO, update_dto: ChoiceUpdateDTO) -> ChoiceDTO:
    """Apply ChoiceUpdateDTO changes to existing ChoiceDTO."""
    if update_dto.title is not None:
        dto.title = update_dto.title
    if update_dto.description is not None:
        dto.description = update_dto.description
    if update_dto.choice_type is not None:
        dto.choice_type = update_dto.choice_type
    if update_dto.priority is not None:
        dto.priority = update_dto.priority
    if update_dto.domain is not None:
        dto.domain = update_dto.domain
    if update_dto.status is not None:
        dto.status = update_dto.status
    if update_dto.decision_deadline is not None:
        dto.decision_deadline = update_dto.decision_deadline
    # Note: decision_criteria, constraints, stakeholders are not in ChoiceUpdateDTO
    # These are set at creation time only, not during updates
    if update_dto.satisfaction_score is not None:
        dto.satisfaction_score = update_dto.satisfaction_score
    if update_dto.actual_outcome is not None:
        dto.actual_outcome = update_dto.actual_outcome
    if update_dto.lessons_learned is not None:
        dto.lessons_learned = update_dto.lessons_learned

    return dto


def apply_choice_decision_to_dto(dto: ChoiceDTO, decision_dto: ChoiceDecisionDTO) -> ChoiceDTO:
    """Apply ChoiceDecisionDTO changes to existing ChoiceDTO."""
    dto.selected_option_uid = decision_dto.selected_option_uid
    dto.decision_rationale = decision_dto.decision_rationale
    dto.decided_at = decision_dto.decided_at
    dto.status = ChoiceStatus.DECIDED.value
    return dto


def apply_choice_evaluation_to_dto(
    dto: ChoiceDTO, evaluation_dto: ChoiceEvaluationDTO
) -> ChoiceDTO:
    """Apply ChoiceEvaluationDTO changes to existing ChoiceDTO."""
    dto.satisfaction_score = evaluation_dto.satisfaction_score
    dto.actual_outcome = evaluation_dto.actual_outcome
    dto.lessons_learned = evaluation_dto.lessons_learned
    dto.status = ChoiceStatus.EVALUATED.value
    return dto
