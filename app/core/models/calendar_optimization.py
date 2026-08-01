"""
Calendar Optimization Models
============================

Domain models for knowledge-aware calendar scheduling: the capacity/strategy
enums and the analysis/recommendation dataclasses consumed by
CalendarOptimizationService and its scheduling-strategies mixin.

Note: ``EnergyLevel`` here is the *hourly capacity* scale (PEAK..DEPLETED)
used for time-slot analysis — deliberately distinct from
``core.models.enums.scheduling_enums.EnergyLevel``, the task
energy-requirement scale (LOW/MEDIUM/HIGH/VARIABLE) on user preferences.
Do not merge them.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from core.models.curriculum_dto import CurriculumDTO
from core.models.enums import Domain

# Type alias for clarity
KnowledgeUnitDTO = CurriculumDTO


class EnergyLevel(Enum):
    """User energy levels throughout the day."""

    PEAK = "peak"  # 90-100% capacity
    HIGH = "high"  # 70-89% capacity
    MEDIUM = "medium"  # 50-69% capacity
    LOW = "low"  # 30-49% capacity
    DEPLETED = "depleted"  # 0-29% capacity


class SchedulingStrategy(Enum):
    """Calendar optimization strategies."""

    KNOWLEDGE_FOCUSED = "knowledge_focused"  # Optimize for learning outcomes
    DEADLINE_DRIVEN = "deadline_driven"  # Prioritize urgent deadlines
    ENERGY_ALIGNED = "energy_aligned"  # Match tasks to energy levels
    COGNITIVE_BALANCED = "cognitive_balanced"  # Balance cognitive load
    SPACED_REPETITION = "spaced_repetition"  # Optimize knowledge retention


@dataclass
class CognitiveLoadAnalysis:
    """Analysis of cognitive load for a task or learning session."""

    intrinsic_load: float  # 0.0-1.0: Content complexity
    extraneous_load: float  # 0.0-1.0: Environmental/design factors
    germane_load: float  # 0.0-1.0: Schema building requirement
    total_load: float  # Combined cognitive load
    domain_complexity: float  # Domain-specific complexity
    prerequisite_load: float  # Load from missing prerequisites

    def is_overload_risk(self) -> bool:
        """Check if cognitive load risks overload."""
        return self.total_load > 0.8

    def get_load_category(self) -> str:
        """Categorize cognitive load level."""
        if self.total_load <= 0.3:
            return "light"
        elif self.total_load <= 0.6:
            return "moderate"
        elif self.total_load <= 0.8:
            return "heavy"
        else:
            return "overload"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization, including derived fields."""
        return {
            "intrinsic_load": self.intrinsic_load,
            "extraneous_load": self.extraneous_load,
            "germane_load": self.germane_load,
            "total_load": self.total_load,
            "domain_complexity": self.domain_complexity,
            "prerequisite_load": self.prerequisite_load,
            "is_overload_risk": self.is_overload_risk(),
            "load_category": self.get_load_category(),
        }


@dataclass
class EnergyProfile:
    """User's energy patterns throughout the day."""

    peak_hours: list[int]  # Hours when energy is highest (0-23)
    high_hours: list[int]  # Hours with high energy
    medium_hours: list[int]  # Hours with medium energy
    low_hours: list[int]  # Hours with low energy
    depleted_hours: list[int]  # Hours when energy is depleted
    chronotype: str  # "morning", "evening", "neutral"
    focus_duration_minutes: int  # Maximum sustained focus time


@dataclass
class OptimizedTimeSlot:
    """An optimized time slot for scheduling."""

    start_time: datetime
    end_time: datetime
    energy_level: EnergyLevel
    cognitive_capacity: float  # Available cognitive capacity (0.0-1.0)
    domain_affinity: Domain | None  # Best domain for this slot
    interruption_risk: float  # Risk of interruptions (0.0-1.0)
    learning_effectiveness: float  # Effectiveness for learning (0.0-1.0)
    productivity_score: float  # Overall productivity potential

    def duration_minutes(self) -> int:
        """Get slot duration in minutes."""
        return int((self.end_time - self.start_time).total_seconds() / 60)


@dataclass
class LearningSession:
    """Optimized learning session with multiple knowledge units."""

    session_id: str
    start_time: datetime
    end_time: datetime
    knowledge_units: list[str]  # UIDs of knowledge units
    primary_domain: Domain
    session_type: str  # "deep_focus", "review", "practice", "exploration"
    cognitive_load: CognitiveLoadAnalysis
    prerequisites_covered: list[str]
    learning_objectives: list[str]
    recommended_breaks: list[int]  # Minutes into session for breaks
    spaced_repetition_items: list[str]  # Items for spaced repetition

    def duration_minutes(self) -> int:
        """Get session duration in minutes."""
        return int((self.end_time - self.start_time).total_seconds() / 60)


@dataclass
class KnowledgeSchedulingRecommendation:
    """Recommendation for scheduling knowledge-related activities."""

    activity_type: str  # "learning", "application", "review", "practice"
    recommended_time: datetime
    duration_minutes: int
    energy_requirement: EnergyLevel
    cognitive_load: CognitiveLoadAnalysis
    knowledge_units: list[str]
    reasoning: str  # Why this timing is recommended
    prerequisites: list[str]  # Required prior knowledge
    follow_up_activities: list[str]
    confidence_score: float  # 0.0-1.0: Confidence in recommendation


@dataclass
class CalendarOptimization:
    """Complete calendar optimization with scheduling recommendations."""

    optimization_date: date
    strategy: SchedulingStrategy
    total_cognitive_load: float
    load_distribution: dict[int, float]  # Hour -> cognitive load
    optimized_slots: list[OptimizedTimeSlot]
    learning_sessions: list[LearningSession]
    scheduling_recommendations: list[KnowledgeSchedulingRecommendation]
    energy_alignment_score: float  # How well tasks align with energy
    knowledge_progression_score: float  # Learning progression quality
    cognitive_balance_score: float  # How well cognitive load is balanced
