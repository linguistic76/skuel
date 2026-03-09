"""
Askesis Domain Models Package
=============================

Complete three-tier architecture for Askesis - the AI assistant and domain integration orchestrator.

Tier 1 (External): Pydantic models for API validation
Tier 2 (Transfer): Mutable DTOs for data movement
Tier 3 (Core): Immutable domain models with business logic
"""

# GuidanceType doesn't exist - use GuidanceMode from shared_enums instead
from core.models.enums import GuidanceMode as GuidanceType

# Askesis enums (canonical location: core.models.enums.askesis_enums)
from core.models.enums.askesis_enums import (
    ConversationStyle,
    IntegrationSuccess,
    QueryComplexity,
)

# Import domain models that exist in other modules
from core.models.user.conversation import ConversationSession

from .askesis import (
    Askesis,
)
from .askesis_converters import (
    apply_askesis_update_to_dto,
    askesis_create_request_to_dto,
    askesis_domain_to_dto,
    askesis_dto_to_domain,
    askesis_dto_to_response,
    askesis_update_request_to_dto,
    conversation_session_create_request_to_dto,
    conversation_session_domain_to_dto,
    conversation_session_dto_to_domain,
    conversation_session_dto_to_response,
    create_askesis_dto_from_create_dto,
    domain_interaction_dto_to_domain,
    domain_interaction_request_to_dto,
    guidance_recommendation_create_request_to_dto,
    guidance_recommendation_domain_to_dto,
    guidance_recommendation_dto_to_domain,
    guidance_recommendation_dto_to_response,
)
from .askesis_dto import (
    AskesisConfigurationDTO,
    AskesisCreateDTO,
    AskesisDTO,
    AskesisUpdateDTO,
    ConversationAnalyticsDTO,
    ConversationSessionDTO,
    CrossDomainInsightDTO,
    DomainInteractionDTO,
    DomainSuggestionDTO,
    DomainSynergiesAnalyticsDTO,
    GuidanceRecommendationDTO,
    IntelligenceInsightsDTO,
)

# DomainInteraction and GuidanceRecommendation don't exist as frozen models yet
# They only exist as DTOs, so we'll import the DTOs and alias them for backward compatibility
from .askesis_dto import DomainInteractionDTO as DomainInteraction
from .askesis_dto import GuidanceRecommendationDTO as GuidanceRecommendation
from .askesis_request import (
    AskesisAnalyticsRequest,
    AskesisCreateRequest,
    AskesisResponse,
    AskesisUpdateRequest,
    ConversationSessionCreateRequest,
    ConversationSessionResponse,
    ConversationSessionUpdateRequest,
    DomainInteractionRequest,
    DomainSuggestionRequest,
    DomainSuggestionResponse,
    GuidanceRecommendationCreateRequest,
    GuidanceRecommendationResponse,
    GuidanceRecommendationResponseRequest,
    IntelligenceInsightsResponse,
    IntelligenceUpdateRequest,
)

__all__ = [
    # Core domain models
    "Askesis",
    "AskesisAnalyticsRequest",
    "AskesisConfigurationDTO",
    "AskesisCreateDTO",
    # Request/Response models
    "AskesisCreateRequest",
    # DTOs
    "AskesisDTO",
    "AskesisResponse",
    "AskesisUpdateDTO",
    "AskesisUpdateRequest",
    "ConversationAnalyticsDTO",
    "ConversationSession",
    "ConversationSessionCreateRequest",
    "ConversationSessionDTO",
    "ConversationSessionResponse",
    "ConversationSessionUpdateRequest",
    "ConversationStyle",
    "CrossDomainInsightDTO",
    "DomainInteraction",
    "DomainInteractionDTO",
    "DomainInteractionRequest",
    "DomainSuggestionDTO",
    "DomainSuggestionRequest",
    "DomainSuggestionResponse",
    "DomainSynergiesAnalyticsDTO",
    "GuidanceRecommendation",
    "GuidanceRecommendationCreateRequest",
    "GuidanceRecommendationDTO",
    "GuidanceRecommendationResponse",
    "GuidanceRecommendationResponseRequest",
    "GuidanceType",
    "IntegrationSuccess",
    "IntelligenceInsightsDTO",
    "IntelligenceInsightsResponse",
    "IntelligenceUpdateRequest",
    "QueryComplexity",
    "apply_askesis_update_to_dto",
    # Converters
    "askesis_create_request_to_dto",
    "askesis_domain_to_dto",
    "askesis_dto_to_domain",
    "askesis_dto_to_response",
    "askesis_update_request_to_dto",
    "conversation_session_create_request_to_dto",
    "conversation_session_domain_to_dto",
    "conversation_session_dto_to_domain",
    "conversation_session_dto_to_response",
    "create_askesis_dto_from_create_dto",
    "domain_interaction_dto_to_domain",
    "domain_interaction_request_to_dto",
    "guidance_recommendation_create_request_to_dto",
    "guidance_recommendation_domain_to_dto",
    "guidance_recommendation_dto_to_domain",
    "guidance_recommendation_dto_to_response",
]
