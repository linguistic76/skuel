"""
LearningStep Domain Models
===========================

Three-tier model system for learning steps.

LearningStep (ls) is one of SKUEL's three core curriculum entities:
- ku: Knowledge Unit
- ls: Learning Step
- lp: Learning Path

This module provides the complete three-tier implementation with all conversions.
"""

from .ls import LearningStep, Ls, MasteryLevel, StepDifficulty, StepStatus
from .ls_converters import (
    ls_create_request_to_dto,
    ls_dto_to_pure,
    ls_pure_to_dict,
    ls_pure_to_dto,
    ls_pure_to_response,
    ls_request_to_pure,
    ls_update_request_to_dto,
)
from .ls_dto import LearningStepDTO
from .ls_request import LearningStepCreateRequest, LearningStepResponse, LearningStepUpdateRequest

__all__ = [
    # Backward compatibility - long form alias
    "LearningStep",
    # Request/Response (Tier 1)
    "LearningStepCreateRequest",
    # DTO (Tier 2)
    "LearningStepDTO",
    "LearningStepResponse",
    "LearningStepUpdateRequest",
    # Pure model (Tier 3) - Preferred abbreviated form
    "Ls",
    "MasteryLevel",
    "StepDifficulty",
    "StepStatus",
    # Converters
    "ls_create_request_to_dto",
    "ls_dto_to_pure",
    "ls_pure_to_dict",
    "ls_pure_to_dto",
    "ls_pure_to_response",
    "ls_request_to_pure",
    "ls_update_request_to_dto",
]
