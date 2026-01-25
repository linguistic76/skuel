"""
LifePath Three-Tier Model Package
=================================

Domain #14: The Destination - "Everything flows toward the life path"

This package provides models for:
1. Vision capture (user's words)
2. Life path designation (LP selection)
3. Word-action alignment (vision vs. behavior measurement)

Philosophy:
    "The user's vision is understood via the words user uses to communicate,
    the UserContext is determined via user's actions."

Three-tier architecture:
- External (Tier 1): lifepath_request.py - Pydantic validation
- Transfer (Tier 2): lifepath_dto.py - Mutable DTOs
- Core (Tier 3): lifepath.py, vision.py - Frozen domain models
"""

# Core domain models (Tier 3 - Frozen)
from .lifepath import AlignmentLevel, LifePathDesignation

# DTOs (Tier 2 - Mutable)
from .lifepath_dto import (
    LifePathDesignationDTO,
    VisionCaptureDTO,
    WordActionAlignmentDTO,
)

# Request/Response models (Tier 1 - Pydantic)
from .lifepath_request import (
    AlignmentCheckRequest,
    DesignateLifePathRequest,
    LifePathDesignationResponse,
    LpRecommendationResponse,
    UpdateVisionRequest,
    VisionCaptureRequest,
    VisionCaptureResponse,
    VisionThemeResponse,
    WordActionAlignmentResponse,
)
from .vision import (
    LpRecommendation,
    ThemeCategory,
    VisionCapture,
    VisionHistory,
    VisionTheme,
    WordActionAlignment,
)

__all__ = [
    # Enums
    "AlignmentLevel",
    "ThemeCategory",
    # Core domain models
    "LifePathDesignation",
    "VisionCapture",
    "VisionTheme",
    "VisionHistory",
    "WordActionAlignment",
    "LpRecommendation",
    # DTOs
    "LifePathDesignationDTO",
    "VisionCaptureDTO",
    "WordActionAlignmentDTO",
    # Request models
    "VisionCaptureRequest",
    "DesignateLifePathRequest",
    "UpdateVisionRequest",
    "AlignmentCheckRequest",
    # Response models
    "VisionThemeResponse",
    "VisionCaptureResponse",
    "LpRecommendationResponse",
    "LifePathDesignationResponse",
    "WordActionAlignmentResponse",
]
