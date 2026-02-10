"""
Ku Nested Types — Frozen Dataclass Components for Unified Ku Model
===================================================================

"Ku is the heartbeat of SKUEL."

Nested types used within specific KuType sections:

    Milestone           → GOAL progress tracking (milestones field)
    ChoiceOption        → CHOICE decision options (options field)
    PrincipleExpression → PRINCIPLE behavioral expressions (expressions field)
    AlignmentAssessment → PRINCIPLE alignment history (alignment_history field)

These are value objects — identity is by content, not UID (except Milestone
and ChoiceOption which have UIDs for indexing within their parent Ku).

All are frozen dataclasses matching the Ku model's immutability contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core.models.enums.ku_enums import AlignmentLevel


# =============================================================================
# GOAL: Milestone
# =============================================================================


@dataclass(frozen=True)
class Milestone:
    """
    A progress checkpoint within a GOAL Ku.

    Milestones divide a goal into measurable sub-targets with dates.
    Stored as a tuple on the Ku: `milestones: tuple[Milestone, ...]`.

    Fields:
        uid: Unique identifier within the goal
        title: Short milestone description
        description: Detailed description (optional)
        target_date: When this milestone should be achieved
        target_value: Numeric target (optional, for measurable milestones)
        achieved_date: When actually achieved (None if not yet)
        is_completed: Whether this milestone is done
        required_knowledge_uids: KU UIDs needed to reach this milestone
        unlocked_knowledge_uids: KU UIDs unlocked by achieving this milestone
    """

    uid: str
    title: str
    description: str | None = None
    target_date: date | None = None
    target_value: float | None = None
    achieved_date: date | None = None  # type: ignore[assignment]
    is_completed: bool = False
    required_knowledge_uids: tuple[str, ...] = ()
    unlocked_knowledge_uids: tuple[str, ...] = ()


# =============================================================================
# CHOICE: ChoiceOption
# =============================================================================


@dataclass(frozen=True)
class ChoiceOption:
    """
    A single option in a CHOICE Ku.

    Options are evaluated on multiple dimensions for decision-making.
    Stored as a tuple on the Ku: `options: tuple[ChoiceOption, ...]`.

    Fields:
        uid: Unique identifier within the choice
        title: Short option name
        description: Detailed description
        feasibility_score: How feasible (0.0-1.0)
        risk_level: Risk level (0.0-1.0)
        potential_impact: Expected impact (0.0-1.0)
        resource_requirement: Resources needed (0.0-1.0)
        estimated_duration: Expected duration in minutes (optional)
        dependencies: UIDs of entities this option depends on
        tags: Classification tags
    """

    uid: str
    title: str
    description: str = ""
    feasibility_score: float = 0.5
    risk_level: float = 0.5
    potential_impact: float = 0.5
    resource_requirement: float = 0.5
    estimated_duration: int | None = None
    dependencies: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


# =============================================================================
# PRINCIPLE: PrincipleExpression
# =============================================================================


@dataclass(frozen=True)
class PrincipleExpression:
    """
    How a PRINCIPLE Ku manifests in a specific life context.

    Connects abstract principles to concrete behaviors.
    Stored as a tuple on the Ku: `expressions: tuple[PrincipleExpression, ...]`.

    Fields:
        context: Life situation (e.g., "When facing a difficult conversation")
        behavior: Expected behavior (e.g., "Speak honestly but with compassion")
        example: Concrete example (optional)
    """

    context: str
    behavior: str
    example: str | None = None


# =============================================================================
# PRINCIPLE: AlignmentAssessment
# =============================================================================


@dataclass(frozen=True)
class AlignmentAssessment:
    """
    A point-in-time assessment of how well one is living a PRINCIPLE Ku.

    Forms the alignment_history timeline for tracking principle adherence.
    Stored as a tuple on the Ku: `alignment_history: tuple[AlignmentAssessment, ...]`.

    Fields:
        assessed_date: When the assessment was made
        alignment_level: How aligned (FLOURISHING -> MISALIGNED)
        evidence: What evidence supports this assessment
        reflection: Personal reflection on the assessment (optional)
    """

    assessed_date: date
    alignment_level: AlignmentLevel
    evidence: str
    reflection: str | None = None
