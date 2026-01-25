"""
LifePath Request Models (Tier 1 - External)
============================================

Pydantic models for API validation and serialization.
These are the entry points for external data.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class VisionCaptureRequest(BaseModel):
    """
    Request to capture user's vision statement.

    User provides their vision in their own words,
    system extracts themes and recommends LPs.
    """

    vision_statement: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="User's vision expressed in their own words",
        json_schema_extra={
            "example": "I want to become a mindful technical leader who builds products that matter"
        },
    )


class DesignateLifePathRequest(BaseModel):
    """
    Request to designate a Learning Path as the user's life path.

    This creates the ULTIMATE_PATH relationship.
    """

    life_path_uid: str = Field(
        ...,
        description="UID of the Learning Path to designate as life path",
        json_schema_extra={"example": "lp:mindful-software-engineer"},
    )
    confirm_vision_match: bool = Field(
        default=True,
        description="User confirms the LP matches their expressed vision",
    )


class UpdateVisionRequest(BaseModel):
    """
    Request to update user's vision statement.

    Vision can evolve - this allows refinement while
    maintaining history.
    """

    vision_statement: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Updated vision statement",
    )
    reason_for_change: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for vision update",
    )


class AlignmentCheckRequest(BaseModel):
    """
    Request to check word-action alignment.

    Compares user's stated vision with their actual behavior.
    """

    include_recommendations: bool = Field(
        default=True,
        description="Include recommendations for improving alignment",
    )
    detailed_analysis: bool = Field(
        default=False,
        description="Include detailed per-dimension analysis",
    )


# Response models for API serialization


class VisionThemeResponse(BaseModel):
    """A single extracted theme from vision statement."""

    theme: str
    category: str
    confidence: float
    context: str | None = None


class VisionCaptureResponse(BaseModel):
    """Response after capturing user's vision."""

    user_uid: str
    vision_statement: str
    themes: list[VisionThemeResponse]
    captured_at: datetime
    llm_model: str | None = None


class LpRecommendationResponse(BaseModel):
    """A recommended Learning Path based on vision."""

    lp_uid: str
    lp_name: str
    match_score: float
    matching_themes: list[str]
    lp_domain: str | None = None


class LifePathDesignationResponse(BaseModel):
    """Full life path designation status."""

    user_uid: str
    vision_statement: str
    vision_themes: list[str]
    life_path_uid: str | None
    alignment_score: float
    alignment_level: str
    word_action_gap: float

    # Dimension scores
    knowledge_alignment: float
    activity_alignment: float
    goal_alignment: float
    principle_alignment: float
    momentum: float

    has_designation: bool
    is_aligned: bool
    weakest_dimension: str | None = None
    insights: list[str] = Field(default_factory=list)


class WordActionAlignmentResponse(BaseModel):
    """Response showing word-action alignment analysis."""

    user_uid: str
    alignment_score: float
    vision_themes: list[str]
    action_themes: list[str]
    matched_themes: list[str]
    missing_in_actions: list[str]
    unexpected_actions: list[str]
    gap_summary: str
    insights: list[str]
    recommendations: list[str]
