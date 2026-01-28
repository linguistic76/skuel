"""
Unified Learning Models
=======================

Consolidated learning models that replace the legacy learning folder.
These models represent the STRUCTURE of learning, not state or progress.

Key Principles:
1. Structure only - no embedded state or progress
2. All progress tracked via UnifiedProgress
3. All relationships managed via unified_relationships
4. Clean, immutable data models

This replaces:
- core.models.learning.curriculum
- core.models.learning.scheduled
- core.models.learning.insights
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any
from uuid import uuid4

from core.models.shared_enums import Domain

# ============================================================================
# LEARNING PATH MODELS (Structure Only)
# ============================================================================


@dataclass(frozen=True)
class LpStep:
    """
    A single step in a learning path curriculum.

    Represents the STRUCTURE of a learning step, not its state.
    Progress is tracked via UnifiedProgress with entity_uid = step.uid
    """

    # Identity
    uid: str
    title: str
    description: str = ""

    # Domain classification
    domain: Domain = Domain.KNOWLEDGE

    # Learning metadata (structure only, not state)
    estimated_time_minutes: int = 30
    difficulty_level: str = "intermediate"
    content_type: str = "concept"  # concept, practice, assessment, project

    # Resources (just references, not embedded)
    resource_uids: list[str] = (field(default_factory=list),)
    exercise_uids: list[str] = field(default_factory=list)

    # Prerequisites (managed via relationships, not embedded)
    prerequisite_uids: list[str] = field(default_factory=list)

    # Content reference (for knowledge units)
    knowledge_unit_uid: str | None = None

    # Learning objectives
    learning_objectives: list[str] = field(default_factory=list)

    # Tags for categorization
    tags: list[str] = field(default_factory=list)

    # =========================================================================
    # NEO4J GENAI PLUGIN INTEGRATION (January 2026)
    # Vector embeddings for semantic search and similarity matching
    # =========================================================================
    embedding: tuple[float, ...] | None = None  # 1536-dimensional vector for semantic search
    embedding_model: str | None = None  # Model used (e.g., "text-embedding-3-small")
    embedding_updated_at: datetime | None = None  # When embedding was generated

    @classmethod
    def create(
        cls, title: str, description: str = "", domain: Domain = Domain.KNOWLEDGE, **kwargs: Any
    ) -> LpStep:
        """Factory method to create a new step with generated UID"""
        return cls(
            uid=f"step_{uuid4().hex[:8]}",
            title=title,
            description=description,
            domain=domain,
            **kwargs,
        )


@dataclass(frozen=True)
class LearningPath:
    """
    A complete learning path with ordered steps.

    Represents the STRUCTURE of a learning journey, not its state.
    All progress/state is tracked in UnifiedProgress with entity_uid = path.uid
    """

    # Identity
    uid: str
    name: str
    description: str
    goal: str

    # Path structure (not state)
    steps: list[LpStep] = field(default_factory=list)

    # Path characteristics (structure, not progress)
    total_estimated_hours: float = 0.0
    difficulty_level: str = "intermediate"

    # Path type and behavior
    is_adaptive: bool = False  # Can adapt based on performance,
    is_sequential: bool = True  # Must complete steps in order

    # Domain classification
    domain: Domain = Domain.KNOWLEDGE

    # Tags and categorization
    tags: list[str] = (field(default_factory=list),)
    category: str = "general"

    # Target audience
    target_audience: str = "general"
    prerequisites_description: str = ""

    # Alternative paths (for adaptive learning)
    alternative_path_uids: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        name: str,
        goal: str,
        description: str = "",
        steps: list[LpStep] | None = None,
        **kwargs: Any,
    ) -> LearningPath:
        """Factory method to create a new path with generated UID"""
        path_steps = steps or []
        total_hours = sum(step.estimated_time_minutes for step in path_steps) / 60.0

        return cls(
            uid=f"path_{uuid4().hex[:8]}",
            name=name,
            goal=goal,
            description=description,
            steps=path_steps,
            total_estimated_hours=total_hours,
            **kwargs,
        )

    def add_step(self, step: LpStep) -> LearningPath:
        """Add a step to the path (returns new instance due to immutability)"""
        new_steps = [*list(self.steps), step]
        total_hours = sum(s.estimated_time_minutes for s in new_steps) / 60.0

        return self.__class__(
            uid=self.uid,
            name=self.name,
            description=self.description,
            goal=self.goal,
            steps=new_steps,
            total_estimated_hours=total_hours,
            difficulty_level=self.difficulty_level,
            is_adaptive=self.is_adaptive,
            is_sequential=self.is_sequential,
            domain=self.domain,
            tags=self.tags,
            category=self.category,
            target_audience=self.target_audience,
            prerequisites_description=self.prerequisites_description,
            alternative_path_uids=self.alternative_path_uids,
        )

    def get_step_by_index(self, index: int) -> LpStep | None:
        """Get step by index (0-based)"""
        if 0 <= index < len(self.steps):
            return self.steps[index]
        return None

    def get_step_by_uid(self, uid: str) -> LpStep | None:
        """Get step by UID"""
        for step in self.steps:
            if step.uid == uid:
                return step
        return None


# ============================================================================
# SCHEDULED LEARNING MODELS (Structure Only)
# ============================================================================


@dataclass(frozen=True)
class ScheduledLearningSession:
    """
    A scheduled learning session.

    Represents the PLAN for a learning session, not its execution.
    Actual progress tracked via UnifiedProgress.
    """

    # Identity
    uid: str
    user_uid: str

    # What to learn
    path_uid: str | None = (None,)
    step_uid: str | None = (None,)
    knowledge_unit_uid: str | None = None

    # When to learn
    scheduled_date: date = (field(default_factory=date.today),)
    scheduled_time: time | None = None  # type: ignore[assignment]
    estimated_duration_minutes: int = 30

    # Session metadata
    title: str = "Learning Session"
    description: str = ""
    session_type: str = "study"  # study, practice, review, assessment

    # Recurrence (if any)
    is_recurring: bool = False
    recurrence_pattern: str | None = None  # daily, weekly, etc.

    @classmethod
    def create(
        cls, user_uid: str, scheduled_date: date, title: str = "Learning Session", **kwargs: Any
    ) -> ScheduledLearningSession:
        """Factory method to create a new scheduled session"""
        return cls(
            uid=f"session_{uuid4().hex[:8]}",
            user_uid=user_uid,
            scheduled_date=scheduled_date,
            title=title,
            **kwargs,
        )


# ============================================================================
# LEARNING INSIGHTS (Analysis Results, Not State)
# ============================================================================


@dataclass(frozen=True)
class LpInsight:
    """
    An insight about learning performance or patterns.

    This is an ANALYSIS RESULT, not state. Generated from progress data.
    """

    # Identity
    uid: str
    user_uid: str
    generated_at: datetime

    # Insight details
    insight_type: str  # strength, weakness, pattern, recommendation
    category: str  # pace, mastery, engagement, retention

    # The insight itself
    title: str
    description: str

    # Supporting data
    evidence: dict[str, Any] = (field(default_factory=dict),)
    confidence: float = 0.8  # 0.0 to 1.0

    # Recommendations based on insight
    recommendations: list[str] = field(default_factory=list)

    # Related entities
    related_path_uids: list[str] = (field(default_factory=list),)
    related_step_uids: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls, user_uid: str, insight_type: str, title: str, description: str, **kwargs: Any
    ) -> LpInsight:
        """Factory method to create a new insight"""
        return cls(
            uid=f"insight_{uuid4().hex[:8]}",
            user_uid=user_uid,
            generated_at=datetime.now(),
            insight_type=insight_type,
            title=title,
            description=description,
            category=kwargs.get("category", "general"),
            **kwargs,
        )


# ============================================================================
# HELPER FUNCTIONS (Work with UnifiedProgress)
# ============================================================================


def get_current_step(path: LearningPath, progress_metadata: dict[str, Any]) -> LpStep | None:
    """
    Get current step using progress metadata.

    Args:
        path: The learning path structure,
        progress_metadata: The metadata from UnifiedProgress record

    Returns:
        Current step or None if not found
    """
    if not progress_metadata:
        return path.steps[0] if path.steps else None

    current_index = progress_metadata.get("current_step_index", 0)
    return path.get_step_by_index(current_index)


def calculate_path_completion(path: LearningPath, step_progress: dict[str, float]) -> float:
    """
    Calculate overall path completion from step progress.

    Args:
        path: The learning path,
        step_progress: Map of step_uid to completion percentage

    Returns:
        Overall completion percentage (0-100)
    """
    if not path.steps:
        return 0.0

    total_completion = sum(step_progress.get(step.uid, 0.0) for step in path.steps)

    return total_completion / len(path.steps)


def get_next_step(path: LearningPath, current_step_uid: str) -> LpStep | None:
    """
    Get the next step in a path after the current one.

    Args:
        path: The learning path,
        current_step_uid: UID of current step

    Returns:
        Next step or None if at end
    """
    for i, step in enumerate(path.steps):
        if step.uid == current_step_uid:
            if i + 1 < len(path.steps):
                return path.steps[i + 1]
            break
    return None


def estimate_time_remaining(path: LearningPath, current_step_index: int) -> int:
    """
    Estimate minutes remaining in path from current position.

    Args:
        path: The learning path,
        current_step_index: Current step index (0-based)

    Returns:
        Estimated minutes remaining
    """
    if current_step_index >= len(path.steps):
        return 0

    remaining_steps = path.steps[current_step_index:]
    return sum(step.estimated_time_minutes for step in remaining_steps)


# ============================================================================
# PROGRESS BRIDGE FUNCTIONS (Work with UnifiedProgress)
# ============================================================================


def get_progress_for_step(
    step: LpStep,
    progress_records: dict[str, Any],  # UnifiedProgress records
) -> Any | None:
    """
    Get the UnifiedProgress record for a learning step.

    Args:
        step: The learning step,
        progress_records: Map of entity_uid to UnifiedProgress

    Returns:
        The progress record if found, None otherwise
    """
    # Look up by step uid
    return progress_records.get(step.uid)


def get_completion_percentage(step: LpStep, progress_records: dict[str, Any]) -> float:
    """
    Get the completion percentage for a learning step.

    Args:
        step: The learning step,
        progress_records: Map of entity_uid to UnifiedProgress

    Returns:
        Completion percentage (0.0-100.0)
    """
    progress = get_progress_for_step(step, progress_records)
    if not progress:
        return 0.0

    return float(progress.metrics.completion_percentage)


def get_time_invested(step: LpStep, progress_records: dict[str, Any]) -> int:
    """
    Get the time invested in a learning step.

    Args:
        step: The learning step,
        progress_records: Map of entity_uid to UnifiedProgress

    Returns:
        Time invested in minutes
    """
    progress = get_progress_for_step(step, progress_records)
    if not progress:
        return 0

    return progress.metrics.time_spent_minutes


def calculate_path_progress(path: LearningPath, progress_records: dict[str, Any]) -> float:
    """
    Calculate overall path progress from step progress records.

    Args:
        path: The learning path,
        progress_records: Map of entity_uid to UnifiedProgress

    Returns:
        Overall completion percentage (0-100)
    """
    if not path.steps:
        return 0.0

    total_completion = sum(get_completion_percentage(step, progress_records) for step in path.steps)

    return total_completion / len(path.steps)


# ============================================================================
