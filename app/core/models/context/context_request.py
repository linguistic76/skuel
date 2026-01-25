"""
Context API Request Models (Pydantic)
======================================

Pydantic models for Context-Aware API boundaries (Tier 1 of three-tier architecture).
Handles validation and serialization at the API layer.

These models validate JSON bodies for POST routes in the context-aware API.
Created: 2026-01-24
"""

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

# Type literals for strict validation
QualityLiteral = Literal["poor", "fair", "good", "excellent"]


# ============================================================================
# TASK COMPLETION REQUEST
# ============================================================================


class TaskCompletionRequest(BaseModel):
    """
    Request model for completing a task with context awareness.

    Used by: POST /api/context/task/complete

    Fields:
        context: Context data about the completion (knowledge applied, time, quality)
        reflection: Optional reflection notes on the completion experience
    """

    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Context data (knowledge_applied, time_invested_minutes, quality)",
    )
    reflection: str = Field(
        default="",
        max_length=2000,
        description="Reflection notes on task completion",
    )

    class Config:
        json_schema_extra: ClassVar[dict[str, Any]] = {
            "example": {
                "context": {
                    "knowledge_applied": ["ku.python", "ku.async-patterns"],
                    "time_invested_minutes": 120,
                    "quality": "good",
                },
                "reflection": "Learned about async context managers while implementing this feature.",
            }
        }


# ============================================================================
# GOAL TASK GENERATION REQUEST
# ============================================================================


class GoalTaskGenerationRequest(BaseModel):
    """
    Request model for generating tasks from a goal with context awareness.

    Used by: POST /api/context/goal/tasks

    Fields:
        context_preferences: Preferences for task generation (e.g., time_available, difficulty)
        auto_create: Whether to create tasks immediately (True) or return templates (False)
    """

    context_preferences: dict[str, Any] = Field(
        default_factory=dict,
        description="Preferences for task generation (time_available, difficulty_preference, etc.)",
    )
    auto_create: bool = Field(
        default=True,
        description="If True, create tasks immediately; if False, return task templates",
    )

    class Config:
        json_schema_extra: ClassVar[dict[str, Any]] = {
            "example": {
                "context_preferences": {
                    "time_available_minutes": 180,
                    "difficulty_preference": "moderate",
                    "focus_area": "learning",
                },
                "auto_create": True,
            }
        }


# ============================================================================
# HABIT COMPLETION REQUEST
# ============================================================================


class HabitCompletionRequest(BaseModel):
    """
    Request model for completing a habit with context tracking.

    Used by: POST /api/context/habit/complete

    Fields:
        quality: Quality rating of the habit completion (poor/fair/good/excellent)
        environmental_factors: Optional environmental context (location, time, mood, etc.)
    """

    quality: QualityLiteral = Field(
        default="good",
        description="Quality rating of the habit completion",
    )
    environmental_factors: dict[str, Any] = Field(
        default_factory=dict,
        description="Environmental context (location, time_of_day, mood, obstacles, etc.)",
    )

    class Config:
        json_schema_extra: ClassVar[dict[str, Any]] = {
            "example": {
                "quality": "excellent",
                "environmental_factors": {
                    "location": "home",
                    "time_of_day": "morning",
                    "mood": "energized",
                    "obstacles": [],
                },
            }
        }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "TaskCompletionRequest",
    "GoalTaskGenerationRequest",
    "HabitCompletionRequest",
]
