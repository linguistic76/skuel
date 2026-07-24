"""
Generated Insight Models
========================

Transient value objects for task-derived knowledge generation: patterns
detected in completed tasks, insights synthesized from those patterns, and
the quality metrics used to curate the resulting knowledge units.

Consumed by InsightGenerationService (`core/services/insight/`). Distinct
from PersistedInsight — these models never touch Neo4j; high-quality
results are converted to CurriculumDTO knowledge units instead.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class PatternType(StrEnum):
    """Types of patterns that can be extracted from task completion."""

    BEST_PRACTICE = "best_practice"
    ANTI_PATTERN = "anti_pattern"
    WORKFLOW_OPTIMIZATION = "workflow_optimization"
    TIME_MANAGEMENT = "time_management"
    SKILL_PROGRESSION = "skill_progression"
    KNOWLEDGE_APPLICATION = "knowledge_application"
    PROBLEM_SOLVING = "problem_solving"


class InsightCategory(StrEnum):
    """Categories of insights generated from task patterns."""

    EFFICIENCY = "efficiency"
    QUALITY = "quality"
    LEARNING = "learning"
    PROCESS = "process"
    STRATEGIC = "strategic"


@dataclass
class TaskPattern:
    """A detected pattern from task completion analysis."""

    pattern_id: str
    pattern_type: PatternType
    confidence_score: float
    supporting_tasks: list[str]
    description: str
    evidence: list[str]
    frequency: int
    success_rate: float
    time_saved_minutes: int | None = None
    quality_impact: float | None = None
    knowledge_uids_involved: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GeneratedInsight:
    """An insight generated from task completion patterns."""

    insight_id: str
    category: InsightCategory
    title: str
    description: str
    actionable_recommendation: str
    supporting_patterns: list[str]
    confidence_score: float
    impact_score: float
    generated_at: datetime
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KuQualityMetrics:
    """Quality metrics for generated knowledge."""

    completeness_score: float  # 0-1
    accuracy_score: float  # 0-1
    relevance_score: float  # 0-1
    timeliness_score: float  # 0-1
    actionability_score: float  # 0-1
    evidence_strength: float  # 0-1
    overall_quality: float  # computed weighted average

    def compute_overall_quality(self) -> float:
        """Compute weighted overall quality score."""
        weights = {
            "completeness": 0.2,
            "accuracy": 0.25,
            "relevance": 0.2,
            "timeliness": 0.1,
            "actionability": 0.15,
            "evidence_strength": 0.1,
        }

        self.overall_quality = (
            self.completeness_score * weights["completeness"]
            + self.accuracy_score * weights["accuracy"]
            + self.relevance_score * weights["relevance"]
            + self.timeliness_score * weights["timeliness"]
            + self.actionability_score * weights["actionability"]
            + self.evidence_strength * weights["evidence_strength"]
        )
        return self.overall_quality
