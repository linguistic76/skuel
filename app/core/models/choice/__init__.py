"""
Choice Domain Models Package
============================

Complete three-tier architecture for choice and decision-making domain.

Tier 1 (External): Pydantic models for API validation
Tier 2 (Transfer): Mutable DTOs for data movement
Tier 3 (Core): Immutable domain models with business logic
"""

from .choice import Choice, ChoiceOption, ChoiceStatus, ChoiceType
from .choice_converters import (
    apply_choice_decision_to_dto,
    apply_choice_evaluation_to_dto,
    apply_choice_update_to_dto,
    choice_create_request_to_dto,
    choice_decision_request_to_dto,
    choice_domain_to_dto,
    choice_dto_to_domain,
    choice_dto_to_response,
    choice_evaluation_request_to_dto,
    choice_option_create_request_to_dto,
    choice_option_domain_to_dto,
    choice_option_dto_to_domain,
    choice_option_dto_to_response,
    choice_update_request_to_dto,
)
from .choice_dto import (
    ChoiceAnalyticsDTO,
    ChoiceCreateDTO,
    ChoiceDecisionDTO,
    ChoiceDTO,
    ChoiceEvaluationDTO,
    ChoiceFilterDTO,
    ChoiceOptionDTO,
    ChoiceUpdateDTO,
)
from .choice_intelligence import (
    ChoiceApplicationIntelligence,
    ChoiceComplexity,
    ChoiceContext,
    ChoiceIntelligence,
    ChoiceQuality,
    DecisionStyle,
    create_choice_application_intelligence,
    create_choice_intelligence,
)
from .choice_request import (
    ChoiceAnalyticsRequest,
    ChoiceAnalyticsResponse,
    ChoiceCreateRequest,
    ChoiceDecisionRequest,
    ChoiceEvaluationRequest,
    ChoiceFilterRequest,
    ChoiceInsightsRequest,
    ChoiceOptionCreateRequest,
    ChoiceOptionRankingRequest,
    ChoiceOptionResponse,
    ChoiceOptionUpdateRequest,
    ChoiceResponse,
    ChoiceUpdateRequest,
)
from .choice_template import ChoiceOptionTemplate, ChoiceTemplate, ChoiceTemplateLibrary

__all__ = [
    # Core domain models
    "Choice",
    "ChoiceAnalyticsDTO",
    "ChoiceAnalyticsRequest",
    "ChoiceAnalyticsResponse",
    "ChoiceApplicationIntelligence",
    "ChoiceComplexity",
    "ChoiceContext",
    "ChoiceCreateDTO",
    # Request/Response models
    "ChoiceCreateRequest",
    # DTOs
    "ChoiceDTO",
    "ChoiceDecisionDTO",
    "ChoiceDecisionRequest",
    "ChoiceEvaluationDTO",
    "ChoiceEvaluationRequest",
    "ChoiceFilterDTO",
    "ChoiceFilterRequest",
    "ChoiceInsightsRequest",
    # Intelligence models
    "ChoiceIntelligence",
    "ChoiceOption",
    "ChoiceOptionCreateRequest",
    "ChoiceOptionDTO",
    "ChoiceOptionRankingRequest",
    "ChoiceOptionResponse",
    "ChoiceOptionTemplate",
    "ChoiceOptionUpdateRequest",
    "ChoiceQuality",
    "ChoiceResponse",
    "ChoiceStatus",
    # Template system (SKUEL differentiation)
    "ChoiceTemplate",
    "ChoiceTemplateLibrary",
    "ChoiceType",
    "ChoiceUpdateDTO",
    "ChoiceUpdateRequest",
    "DecisionStyle",
    "apply_choice_decision_to_dto",
    "apply_choice_evaluation_to_dto",
    "apply_choice_update_to_dto",
    # Converters
    "choice_create_request_to_dto",
    "choice_decision_request_to_dto",
    "choice_domain_to_dto",
    "choice_dto_to_domain",
    "choice_dto_to_response",
    "choice_evaluation_request_to_dto",
    "choice_option_create_request_to_dto",
    "choice_option_domain_to_dto",
    "choice_option_dto_to_domain",
    "choice_option_dto_to_response",
    "choice_update_request_to_dto",
    "create_choice_application_intelligence",
    "create_choice_intelligence",
]
