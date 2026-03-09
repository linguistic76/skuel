"""
Askesis Converters
==================

Conversion functions between the three tiers of Askesis models.
Handles transformation between External → Transfer → Core layers.
"""

from datetime import datetime

# Direct imports to avoid circular dependency with __init__.py
from core.models.askesis.askesis import Askesis
from core.models.askesis.askesis_dto import (
    AskesisCreateDTO,
    AskesisDTO,
    AskesisUpdateDTO,
    ConversationSessionDTO,
    DomainInteractionDTO,
    GuidanceRecommendationDTO,
)
from core.models.enums.askesis_enums import ConversationStyle, QueryComplexity
from core.models.askesis.askesis_request import (
    AskesisCreateRequest,
    AskesisResponse,
    AskesisUpdateRequest,
    ConversationSessionCreateRequest,
    ConversationSessionResponse,
    DomainInteractionRequest,
    GuidanceRecommendationCreateRequest,
    GuidanceRecommendationResponse,
)
from core.models.user.conversation import ConversationSession

# ==========================================================================
# Request → DTO Conversions
# ==========================================================================


def askesis_create_request_to_dto(request: AskesisCreateRequest, user_uid: str) -> AskesisCreateDTO:
    """Convert create request to DTO."""
    return AskesisCreateDTO(
        user_uid=user_uid,
        name=request.name,
        version=request.version,
        preferred_conversation_style=request.preferred_conversation_style.value,
        preferred_complexity_level=request.preferred_complexity_level.value,
    )


def askesis_update_request_to_dto(
    request: AskesisUpdateRequest, askesis_uid: str
) -> AskesisUpdateDTO:
    """Convert update request to DTO."""
    return AskesisUpdateDTO(
        uid=askesis_uid,
        name=request.name,
        version=request.version,
        preferred_conversation_style=request.preferred_conversation_style.value
        if request.preferred_conversation_style
        else None,
        preferred_complexity_level=request.preferred_complexity_level.value
        if request.preferred_complexity_level
        else None,
        last_intelligence_update=datetime.now(),
    )


def conversation_session_create_request_to_dto(
    request: ConversationSessionCreateRequest, user_uid: str
) -> ConversationSessionDTO:
    """Convert conversation session create request to DTO."""
    return ConversationSessionDTO(
        uid=f"cs_{user_uid}_{int(datetime.now().timestamp())}",
        user_uid=user_uid,
        started_at=datetime.now(),
        primary_intent=request.primary_intent,
        complexity_level=request.expected_complexity.value,
        conversation_style=request.preferred_style.value,
    )


def domain_interaction_request_to_dto(
    request: DomainInteractionRequest, user_uid: str
) -> DomainInteractionDTO:
    """Convert domain interaction request to DTO."""
    return DomainInteractionDTO(
        uid=f"di_{user_uid}_{request.domain_a}_{request.domain_b}_{int(datetime.now().timestamp())}",
        domain_a=request.domain_a,
        domain_b=request.domain_b,
        interaction_type=request.interaction_type,
        synergy_score=request.synergy_score,
        user_uid=user_uid,
        context=request.context,
        observed_at=datetime.now(),
    )


def guidance_recommendation_create_request_to_dto(
    request: GuidanceRecommendationCreateRequest, user_uid: str
) -> GuidanceRecommendationDTO:
    """Convert guidance recommendation create request to DTO."""
    return GuidanceRecommendationDTO(
        uid=f"gr_{user_uid}_{request.guidance_type}_{int(datetime.now().timestamp())}",
        user_uid=user_uid,
        guidance_type=request.guidance_type,
        title=request.title,
        description=request.description,
        trigger_context=request.trigger_context,
        relevant_domains=request.relevant_domains,
        confidence_score=request.confidence_score,
        actionable_steps=request.actionable_steps,
        expected_impact=request.expected_impact,
        estimated_effort=request.estimated_effort.value,
        created_at=datetime.now(),
    )


# ==========================================================================
# DTO → Domain Conversions
# ==========================================================================


def askesis_dto_to_domain(dto: AskesisDTO) -> Askesis:
    """Convert DTO to domain model."""
    return Askesis(
        uid=dto.uid,
        user_uid=dto.user_uid,
        name=dto.name,
        version=dto.version,
        intelligence_confidence=dto.intelligence_confidence,
        total_conversations=dto.total_conversations,
        total_domain_integrations=dto.total_domain_integrations,
        integration_success_rate=dto.integration_success_rate,
        pattern_recognition_accuracy=dto.pattern_recognition_accuracy,
        proactive_guidance_success_rate=dto.proactive_guidance_success_rate,
        preferred_conversation_style=ConversationStyle(dto.preferred_conversation_style),
        preferred_complexity_level=QueryComplexity(dto.preferred_complexity_level),
        response_preferences=dto.response_preferences,
        domain_expertise_levels=dto.domain_expertise_levels,
        domain_usage_patterns=dto.domain_usage_patterns,
        cross_domain_synergies=dto.cross_domain_synergies,
        active_learning_areas=tuple(dto.active_learning_areas),
        knowledge_gaps=tuple(dto.knowledge_gaps),
        optimization_opportunities=tuple(dto.optimization_opportunities),
        created_at=dto.created_at,
        last_interaction=dto.last_interaction,
        last_intelligence_update=dto.last_intelligence_update,
    )


def conversation_session_dto_to_domain(dto: ConversationSessionDTO) -> ConversationSession:
    """
    Convert DTO to domain model.

    Note: ConversationSessionDTO represents a completed session summary,
    while ConversationSession is an active session. Map available fields.
    """
    return ConversationSession(
        session_id=dto.uid,  # DTO's uid maps to session_id
        user_uid=dto.user_uid,
        started_at=dto.started_at,
        last_activity=dto.ended_at or dto.started_at,  # Use ended_at as last_activity
        topics_discussed=dto.domains_discussed.copy() if dto.domains_discussed else [],
        # Active session fields use defaults from dataclass
        # DTO metrics like user_satisfaction, goals_achieved are not part of active session
    )


def domain_interaction_dto_to_domain(dto: DomainInteractionDTO) -> DomainInteractionDTO:
    """Convert DTO to domain model (currently using DTO as domain model)."""
    # NOTE: DomainInteractionDTO serves as both DTO and domain model
    return dto


def guidance_recommendation_dto_to_domain(
    dto: GuidanceRecommendationDTO,
) -> GuidanceRecommendationDTO:
    """Convert DTO to domain model (currently using DTO as domain model)."""
    # NOTE: GuidanceRecommendationDTO serves as both DTO and domain model
    return dto


# ==========================================================================
# Domain → DTO Conversions
# ==========================================================================


def askesis_domain_to_dto(domain: Askesis) -> AskesisDTO:
    """Convert domain model to DTO."""
    return AskesisDTO(
        uid=domain.uid,
        user_uid=domain.user_uid,
        name=domain.name,
        version=domain.version,
        intelligence_confidence=domain.intelligence_confidence,
        total_conversations=domain.total_conversations,
        total_domain_integrations=domain.total_domain_integrations,
        integration_success_rate=domain.integration_success_rate,
        pattern_recognition_accuracy=domain.pattern_recognition_accuracy,
        proactive_guidance_success_rate=domain.proactive_guidance_success_rate,
        preferred_conversation_style=domain.preferred_conversation_style.value,
        preferred_complexity_level=domain.preferred_complexity_level.value,
        response_preferences=dict(domain.response_preferences),
        domain_expertise_levels=dict(domain.domain_expertise_levels),
        domain_usage_patterns=dict(domain.domain_usage_patterns),
        cross_domain_synergies=dict(domain.cross_domain_synergies),
        active_learning_areas=list(domain.active_learning_areas),
        knowledge_gaps=list(domain.knowledge_gaps),
        optimization_opportunities=list(domain.optimization_opportunities),
        created_at=domain.created_at,
        last_interaction=domain.last_interaction,
        last_intelligence_update=domain.last_intelligence_update,
    )


def conversation_session_domain_to_dto(domain: ConversationSession) -> ConversationSessionDTO:
    """
    Convert ConversationSession domain model to DTO.

    Maps active session fields to completed session summary.
    """
    return ConversationSessionDTO(
        uid=domain.session_id,
        user_uid=domain.user_uid,
        started_at=domain.started_at,
        ended_at=None,  # Active session - not yet ended
        primary_intent=None,  # Not tracked in ConversationSession
        domains_discussed=domain.topics_discussed.copy() if domain.topics_discussed else [],
        complexity_level=QueryComplexity.SIMPLE.value,  # Default - not tracked in ConversationSession
        conversation_style=ConversationStyle.DIRECT.value,  # Default - GuidanceMode is different concept
        user_satisfaction=None,  # Not tracked in active session
        goals_achieved=False,  # Not determined until session ends
        integration_success=None,  # Not determined until session ends
        new_insights_generated=0,  # Would need analysis
        cross_domain_connections_made=0,  # Would need analysis
        actionable_recommendations=0,  # Would need analysis
    )


def guidance_recommendation_domain_to_dto(
    domain: GuidanceRecommendationDTO,
) -> GuidanceRecommendationDTO:
    """Convert domain model to DTO (currently using DTO as domain model)."""
    # NOTE: GuidanceRecommendationDTO serves as both DTO and domain model
    return domain


# ==========================================================================
# DTO → Response Conversions
# ==========================================================================


def askesis_dto_to_response(dto: AskesisDTO) -> AskesisResponse:
    """Convert DTO to response model."""
    return AskesisResponse(
        uid=dto.uid,
        user_uid=dto.user_uid,
        name=dto.name,
        version=dto.version,
        intelligence_confidence=dto.intelligence_confidence,
        total_conversations=dto.total_conversations,
        total_domain_integrations=dto.total_domain_integrations,
        integration_success_rate=dto.integration_success_rate,
        pattern_recognition_accuracy=dto.pattern_recognition_accuracy,
        proactive_guidance_success_rate=dto.proactive_guidance_success_rate,
        preferred_conversation_style=dto.preferred_conversation_style,
        preferred_complexity_level=dto.preferred_complexity_level,
        active_learning_areas=dto.active_learning_areas,
        knowledge_gaps=dto.knowledge_gaps,
        optimization_opportunities=dto.optimization_opportunities,
        domain_expertise_levels=dto.domain_expertise_levels,
        # NOTE: These fields use defaults - domain methods not yet implemented
        top_domains=[],
        created_at=dto.created_at,
        last_interaction=dto.last_interaction,
        last_intelligence_update=dto.last_intelligence_update,
        is_conversation_ready=False,
        needs_learning=True,
        learning_progress_score=0.0,
    )


def conversation_session_dto_to_response(
    dto: ConversationSessionDTO,
) -> ConversationSessionResponse:
    """Convert DTO to response model."""
    # Calculate duration
    duration_minutes = None
    if dto.ended_at and dto.started_at:
        duration_minutes = (dto.ended_at - dto.started_at).total_seconds() / 60

    return ConversationSessionResponse(
        uid=dto.uid,
        user_uid=dto.user_uid,
        started_at=dto.started_at,
        ended_at=dto.ended_at,
        primary_intent=dto.primary_intent,
        domains_discussed=dto.domains_discussed,
        complexity_level=dto.complexity_level,
        conversation_style=dto.conversation_style,
        user_satisfaction=dto.user_satisfaction,
        goals_achieved=dto.goals_achieved,
        integration_success=dto.integration_success,
        new_insights_generated=dto.new_insights_generated,
        cross_domain_connections_made=dto.cross_domain_connections_made,
        actionable_recommendations=dto.actionable_recommendations,
        duration_minutes=duration_minutes,
        is_active=dto.ended_at is None,
    )


def guidance_recommendation_dto_to_response(
    dto: GuidanceRecommendationDTO,
) -> GuidanceRecommendationResponse:
    """Convert DTO to response model."""
    # Calculate computed fields inline (no domain model methods yet)
    is_delivered = dto.delivered_at is not None
    is_responded_to = dto.user_response is not None
    was_effective = (
        (dto.effectiveness_rating is not None and dto.effectiveness_rating >= 4)
        if dto.effectiveness_rating
        else False
    )

    return GuidanceRecommendationResponse(
        uid=dto.uid,
        user_uid=dto.user_uid,
        guidance_type=dto.guidance_type,
        title=dto.title,
        description=dto.description,
        relevant_domains=dto.relevant_domains,
        confidence_score=dto.confidence_score,
        actionable_steps=dto.actionable_steps,
        expected_impact=dto.expected_impact,
        estimated_effort=dto.estimated_effort,
        created_at=dto.created_at,
        delivered_at=dto.delivered_at,
        user_response=dto.user_response,
        effectiveness_rating=dto.effectiveness_rating,
        is_delivered=is_delivered,
        is_responded_to=is_responded_to,
        was_effective=was_effective,
    )


# ==========================================================================
# Update Application Functions
# ==========================================================================


def apply_askesis_update_to_dto(dto: AskesisDTO, update_dto: AskesisUpdateDTO) -> AskesisDTO:
    """Apply update DTO to existing Askesis DTO."""
    # Update only non-None fields
    if update_dto.name is not None:
        dto.name = update_dto.name
    if update_dto.version is not None:
        dto.version = update_dto.version
    if update_dto.intelligence_confidence is not None:
        dto.intelligence_confidence = update_dto.intelligence_confidence
    if update_dto.preferred_conversation_style is not None:
        dto.preferred_conversation_style = update_dto.preferred_conversation_style
    if update_dto.preferred_complexity_level is not None:
        dto.preferred_complexity_level = update_dto.preferred_complexity_level
    if update_dto.total_conversations is not None:
        dto.total_conversations = update_dto.total_conversations
    if update_dto.total_domain_integrations is not None:
        dto.total_domain_integrations = update_dto.total_domain_integrations
    if update_dto.integration_success_rate is not None:
        dto.integration_success_rate = update_dto.integration_success_rate
    if update_dto.pattern_recognition_accuracy is not None:
        dto.pattern_recognition_accuracy = update_dto.pattern_recognition_accuracy
    if update_dto.proactive_guidance_success_rate is not None:
        dto.proactive_guidance_success_rate = update_dto.proactive_guidance_success_rate
    if update_dto.active_learning_areas is not None:
        dto.active_learning_areas = update_dto.active_learning_areas
    if update_dto.knowledge_gaps is not None:
        dto.knowledge_gaps = update_dto.knowledge_gaps
    if update_dto.optimization_opportunities is not None:
        dto.optimization_opportunities = update_dto.optimization_opportunities
    if update_dto.last_interaction is not None:
        dto.last_interaction = update_dto.last_interaction
    if update_dto.last_intelligence_update is not None:
        dto.last_intelligence_update = update_dto.last_intelligence_update

    return dto


# ==========================================================================
# Helper Functions
# ==========================================================================


def create_askesis_dto_from_create_dto(create_dto: AskesisCreateDTO) -> AskesisDTO:
    """Create a new Askesis DTO from create DTO."""
    return AskesisDTO(
        uid=f"askesis_{create_dto.user_uid}_{int(datetime.now().timestamp())}",
        user_uid=create_dto.user_uid,
        name=create_dto.name,
        version=create_dto.version,
        preferred_conversation_style=create_dto.preferred_conversation_style,
        preferred_complexity_level=create_dto.preferred_complexity_level,
        created_at=datetime.now(),
    )
