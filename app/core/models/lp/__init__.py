"""
Learning Models - Three-Tier Architecture
=========================================

This module implements the three-tier model architecture for learning paths:

1. **Domain Models** (lp.py) - Frozen, immutable models with business logic
2. **DTOs** (lp_dto.py) - Mutable data transfer objects
3. **Request Models** (lp_request.py) - Pydantic models for API validation

Usage:
    - Domain models for business logic and calculations
    - DTOs for data transfer between layers
    - Request models for API input/output validation
"""

# Ls is imported from ls module (authoritative source)
# Use abbreviated form (Ls) following SKUEL curriculum convention
from core.models.ls import LearningStep, Ls, MasteryLevel

from .lp import LearningPath, Lp, LpType
from .lp_dto import LearningStepDTO, LpDTO
from .lp_request import (
    LearningStepCreateRequest,
    LearningStepUpdateRequest,
    LpCreateRequest,
    LpProgressRequest,
    LpResponse,
    LpUpdateRequest,
)

__all__ = [
    # Backward compatibility - long form aliases
    "LearningPath",
    "LearningStep",
    "LearningStepCreateRequest",
    "LearningStepDTO",
    "LearningStepUpdateRequest",
    # Domain Models - Preferred abbreviated forms
    "Lp",
    # Request Models
    "LpCreateRequest",
    # DTOs
    "LpDTO",
    "LpProgressRequest",
    "LpResponse",
    "LpType",
    "LpUpdateRequest",
    # Re-exported from ls module
    "Ls",
    "MasteryLevel",
]
