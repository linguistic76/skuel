"""
Learning Enums - Education, Knowledge, and Mastery Tracking
============================================================

Enums for learning levels, knowledge types, mastery tracking, and SEL framework.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .entity_enums import EntityStatus


class MasteryImpact(StrEnum):
    """
    Impact on student mastery progression when completing an Exercise.

    Controls how aggressively PsMasteryService advances a user's
    MasteryLevel upon learning loop completion. Each Exercise declares its
    impact — a vocabulary quiz (MINOR) advances mastery less than a capstone
    project (CERTIFICATION).

    Two score methods reflect the two mastery paths:
    - get_ai_score(): Used when AI evaluates submission (no teacher review)
    - get_teacher_score(): Used when a teacher approves submission

    Values:
        MINOR: Quick check, vocabulary drill — small score bump
        MODERATE: Standard exercise — current default behavior
        MAJOR: Deep application exercise — significant advancement
        CERTIFICATION: Capstone / certification — highest confidence mastery
    """

    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CERTIFICATION = "certification"

    def get_ai_score(self) -> float:
        """Mastery score when AI evaluates the submission (no teacher review)."""
        scores = {
            MasteryImpact.MINOR: 0.4,
            MasteryImpact.MODERATE: 0.6,
            MasteryImpact.MAJOR: 0.7,
            MasteryImpact.CERTIFICATION: 0.8,
        }
        return scores.get(self, 0.6)

    def get_teacher_score(self) -> float:
        """Mastery score when a teacher approves the submission."""
        scores = {
            MasteryImpact.MINOR: 0.6,
            MasteryImpact.MODERATE: 0.8,
            MasteryImpact.MAJOR: 0.85,
            MasteryImpact.CERTIFICATION: 0.95,
        }
        return scores.get(self, 0.8)

    def get_label(self) -> str:
        """Human-readable label for UI display."""
        labels = {
            MasteryImpact.MINOR: "Minor",
            MasteryImpact.MODERATE: "Moderate",
            MasteryImpact.MAJOR: "Major",
            MasteryImpact.CERTIFICATION: "Certification",
        }
        return labels.get(self, self.value.title())

    def get_description(self) -> str:
        """Description for tooltips and help text."""
        descriptions = {
            MasteryImpact.MINOR: "Quick check or vocabulary drill — small mastery bump",
            MasteryImpact.MODERATE: "Standard exercise — typical mastery advancement",
            MasteryImpact.MAJOR: "Deep application exercise — significant mastery gain",
            MasteryImpact.CERTIFICATION: "Capstone or certification — highest mastery confidence",
        }
        return descriptions.get(self, "")

    def sort_order(self) -> int:
        """Sort position for lists (MINOR first = 0, CERTIFICATION last = 3)."""
        return _MASTERY_IMPACT_SORT_ORDERS[self]

    @classmethod
    def from_value(cls, value: object) -> MasteryImpact:
        """Normalize enum/string inputs to a mastery impact, defaulting to MODERATE."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            value_lower = value.lower()
            for impact in cls:
                if impact.value == value_lower or impact.name.lower() == value_lower:
                    return impact
        return cls.MODERATE


_MASTERY_IMPACT_SORT_ORDERS: dict[MasteryImpact, int] = {
    MasteryImpact.MINOR: 0,
    MasteryImpact.MODERATE: 1,
    MasteryImpact.MAJOR: 2,
    MasteryImpact.CERTIFICATION: 3,
}


class AssessmentOutcome(StrEnum):
    """
    Outcome of an EntryReport assessment.

    Makes each ENTRY_REPORT self-describing — the report records
    what decision was made, not just the feedback text.

    Values:
        APPROVED: Teacher approved the submission (mastery via MasteryImpact.get_teacher_score())
        NEEDS_REVISION: Teacher requested revision (submission → REVISION_REQUESTED)
        AI_EVALUATED: LLM-generated feedback (mastery via MasteryImpact.get_ai_score(), awaiting teacher review)
    """

    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    AI_EVALUATED = "ai_evaluated"


class FeedbackCategory(StrEnum):
    """
    Category of learning gap identified in an EntryReport.

    FeedbackCategory classifies what kind of gap the teacher observed
    in the student's work.
    Used on RevisedExercise.feedback_points to enable pattern tracking
    across submissions and over time.

    Values:
        ACCURACY: Factual errors, wrong information, incorrect conclusions
        COMPLETENESS: Missing required elements, incomplete coverage
        DEPTH: Surface-level treatment, lacks analysis or critical thinking
        CLARITY: Poorly expressed, hard to follow, structural issues
        APPLICATION: Knows theory but fails to apply it to the problem
        METHODOLOGY: Wrong approach, flawed process, inappropriate method
    """

    ACCURACY = "accuracy"
    COMPLETENESS = "completeness"
    DEPTH = "depth"
    CLARITY = "clarity"
    APPLICATION = "application"
    METHODOLOGY = "methodology"

    def get_label(self) -> str:
        """Human-readable label for UI display."""
        labels = {
            FeedbackCategory.ACCURACY: "Accuracy",
            FeedbackCategory.COMPLETENESS: "Completeness",
            FeedbackCategory.DEPTH: "Depth",
            FeedbackCategory.CLARITY: "Clarity",
            FeedbackCategory.APPLICATION: "Application",
            FeedbackCategory.METHODOLOGY: "Methodology",
        }
        return labels.get(self, self.value.title())

    def get_color(self) -> str:
        """Hex color for UI rendering."""
        colors = {
            FeedbackCategory.ACCURACY: "#EF4444",  # Red — factual errors are critical
            FeedbackCategory.COMPLETENESS: "#F59E0B",  # Amber — something is missing
            FeedbackCategory.DEPTH: "#8B5CF6",  # Purple — analytical gap
            FeedbackCategory.CLARITY: "#3B82F6",  # Blue — communication issue
            FeedbackCategory.APPLICATION: "#10B981",  # Green — transfer gap
            FeedbackCategory.METHODOLOGY: "#06B6D4",  # Cyan — process issue
        }
        return colors.get(self, "#6B7280")

    def get_description(self) -> str:
        """Description for tooltips and help text."""
        descriptions = {
            FeedbackCategory.ACCURACY: "Factual errors, wrong information, incorrect conclusions",
            FeedbackCategory.COMPLETENESS: "Missing required elements, incomplete coverage",
            FeedbackCategory.DEPTH: "Surface-level treatment, lacks analysis or critical thinking",
            FeedbackCategory.CLARITY: "Poorly expressed, hard to follow, structural issues",
            FeedbackCategory.APPLICATION: "Knows theory but fails to apply it to the problem",
            FeedbackCategory.METHODOLOGY: "Wrong approach, flawed process, inappropriate method",
        }
        return descriptions.get(self, "")


class KuComplexity(StrEnum):
    """
    Complexity level of a Knowledge Unit.

    Used to indicate difficulty/sophistication of curriculum content.
    """

    BASIC = "basic"
    MEDIUM = "medium"
    ADVANCED = "advanced"

    def sort_order(self) -> int:
        """Sort position for lists (BASIC first = 0, ADVANCED last = 2)."""
        return _KU_COMPLEXITY_SORT_ORDERS[self]

    @classmethod
    def from_value(cls, value: object) -> KuComplexity:
        """Normalize enum/string inputs to a Ku complexity, defaulting to MEDIUM."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            value_lower = value.lower()
            for complexity in cls:
                if complexity.value == value_lower or complexity.name.lower() == value_lower:
                    return complexity
        return cls.MEDIUM


_KU_COMPLEXITY_SORT_ORDERS: dict[KuComplexity, int] = {
    KuComplexity.BASIC: 0,
    KuComplexity.MEDIUM: 1,
    KuComplexity.ADVANCED: 2,
}


class LearningLevel(StrEnum):
    """
    Learning proficiency levels for users and content.

    Used to match users with appropriate content difficulty.
    """

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

    def to_numeric(self) -> int:
        """Convert to numeric value for comparisons (1-4)"""
        mapping = {
            LearningLevel.BEGINNER: 1,
            LearningLevel.INTERMEDIATE: 2,
            LearningLevel.ADVANCED: 3,
            LearningLevel.EXPERT: 4,
        }
        return mapping.get(self, 2)

    def can_handle(self, content_level: "LearningLevel") -> bool:
        """Check if user at this level can handle content at given level"""
        return self.to_numeric() >= content_level.to_numeric()

    def get_search_synonyms(self) -> tuple[str, ...]:
        """Return search terms that match this learning level"""
        synonyms = {
            LearningLevel.BEGINNER: (
                "beginner",
                "novice",
                "starter",
                "new",
                "basic",
                "intro",
                "introductory",
            ),
            LearningLevel.INTERMEDIATE: ("intermediate", "moderate", "mid-level", "developing"),
            LearningLevel.ADVANCED: ("advanced", "experienced", "proficient", "skilled"),
            LearningLevel.EXPERT: ("expert", "master", "professional", "advanced"),
        }
        return synonyms.get(self, ())

    def get_search_description(self) -> str:
        """Human-readable description for search UI"""
        descriptions = {
            LearningLevel.BEGINNER: "Beginner - just starting out",
            LearningLevel.INTERMEDIATE: "Intermediate - building on basics",
            LearningLevel.ADVANCED: "Advanced - experienced learners",
            LearningLevel.EXPERT: "Expert - mastery level",
        }
        return descriptions.get(self, "")

    def sort_order(self) -> int:
        """Sort position for lists (BEGINNER first = 0, EXPERT last = 3)."""
        return _LEARNING_LEVEL_SORT_ORDERS[self]

    @classmethod
    def from_value(cls, value: object) -> LearningLevel:
        """Normalize enum/string inputs to a learning level, defaulting to INTERMEDIATE."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            value_lower = value.lower()
            for level in cls:
                if level.value == value_lower or level.name.lower() == value_lower:
                    return level
        return cls.INTERMEDIATE

    @classmethod
    def from_search_text(cls, text: str) -> list[LearningLevel]:
        """Find matching learning levels from search text"""
        text_lower = text.lower()
        return [
            level
            for level in cls
            if any(synonym in text_lower for synonym in level.get_search_synonyms())
        ]


_LEARNING_LEVEL_SORT_ORDERS: dict[LearningLevel, int] = {
    LearningLevel.BEGINNER: 0,
    LearningLevel.INTERMEDIATE: 1,
    LearningLevel.ADVANCED: 2,
    LearningLevel.EXPERT: 3,
}


class EducationalLevel(StrEnum):
    """
    Educational levels for content targeting and user classification.

    Used for age-appropriate content filtering and personalization.
    """

    ELEMENTARY = "elementary"  # Ages 5-10
    MIDDLE_SCHOOL = "middle_school"  # Ages 11-13
    HIGH_SCHOOL = "high_school"  # Ages 14-17
    COLLEGE = "college"  # Ages 18-22
    PROFESSIONAL = "professional"  # Ages 23+
    LIFELONG = "lifelong"  # Any age, continuous learning

    def get_age_range(self) -> tuple[int, int]:
        """Get approximate age range for this educational level"""
        ranges = {
            EducationalLevel.ELEMENTARY: (5, 10),
            EducationalLevel.MIDDLE_SCHOOL: (11, 13),
            EducationalLevel.HIGH_SCHOOL: (14, 17),
            EducationalLevel.COLLEGE: (18, 22),
            EducationalLevel.PROFESSIONAL: (23, 65),
            EducationalLevel.LIFELONG: (5, 100),
        }
        return ranges.get(self, (18, 65))

    def get_icon(self) -> str:
        """Get emoji icon for this educational level"""
        icons = {
            EducationalLevel.ELEMENTARY: "🎒",
            EducationalLevel.MIDDLE_SCHOOL: "📐",
            EducationalLevel.HIGH_SCHOOL: "🎓",
            EducationalLevel.COLLEGE: "🏛️",
            EducationalLevel.PROFESSIONAL: "💼",
            EducationalLevel.LIFELONG: "🌱",
        }
        return icons.get(self, "📚")

    def get_color(self) -> str:
        """Get suggested color for UI rendering"""
        colors = {
            EducationalLevel.ELEMENTARY: "#F59E0B",  # Amber
            EducationalLevel.MIDDLE_SCHOOL: "#3B82F6",  # Blue
            EducationalLevel.HIGH_SCHOOL: "#8B5CF6",  # Purple
            EducationalLevel.COLLEGE: "#10B981",  # Green
            EducationalLevel.PROFESSIONAL: "#EF4444",  # Red
            EducationalLevel.LIFELONG: "#06B6D4",  # Cyan
        }
        return colors.get(self, "#6B7280")

    def to_numeric(self) -> int:
        """Convert to numeric value for sorting (1-6)"""
        mapping = {
            EducationalLevel.ELEMENTARY: 1,
            EducationalLevel.MIDDLE_SCHOOL: 2,
            EducationalLevel.HIGH_SCHOOL: 3,
            EducationalLevel.COLLEGE: 4,
            EducationalLevel.PROFESSIONAL: 5,
            EducationalLevel.LIFELONG: 6,
        }
        return mapping.get(self, 4)


class MasteryStatus(StrEnum):
    """Mastery status for knowledge/skills"""

    NOT_STARTED = "not_started"
    INTRODUCED = "introduced"
    PRACTICING = "practicing"
    COMPETENT = "competent"
    PROFICIENT = "proficient"
    MASTERED = "mastered"
    REVIEWING = "reviewing"

    def rank(self) -> int:
        """Numeric rank for comparisons (NOT_STARTED=1 ... MASTERED=7).

        REVIEWING ranks 6 — knowledge is already mastered but temporarily back in
        active reinforcement, so it sits one step below MASTERED in working strength.
        """
        return _MASTERY_STATUS_RANKS[self]

    def sort_order(self) -> int:
        """Sort position for lists (NOT_STARTED first = 0, MASTERED last = 6)."""
        return _MASTERY_STATUS_SORT_ORDERS[self]

    @classmethod
    def from_value(cls, value: object) -> MasteryStatus:
        """Normalize enum/string inputs to a mastery status, defaulting to NOT_STARTED."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            value_lower = value.lower()
            for status in cls:
                if status.value == value_lower or status.name.lower() == value_lower:
                    return status
        return cls.NOT_STARTED


_MASTERY_STATUS_RANKS: dict[MasteryStatus, int] = {
    MasteryStatus.NOT_STARTED: 1,
    MasteryStatus.INTRODUCED: 2,
    MasteryStatus.PRACTICING: 3,
    MasteryStatus.COMPETENT: 4,
    MasteryStatus.PROFICIENT: 5,
    MasteryStatus.REVIEWING: 6,  # mastered, temporarily back in reinforcement
    MasteryStatus.MASTERED: 7,
}

_MASTERY_STATUS_SORT_ORDERS: dict[MasteryStatus, int] = {
    MasteryStatus.NOT_STARTED: 0,
    MasteryStatus.INTRODUCED: 1,
    MasteryStatus.PRACTICING: 2,
    MasteryStatus.COMPETENT: 3,
    MasteryStatus.PROFICIENT: 4,
    MasteryStatus.REVIEWING: 5,
    MasteryStatus.MASTERED: 6,
}


class KnowledgeStatus(StrEnum):
    """
    Domain-specific status for knowledge units.
    Maps to EntityStatus where applicable for consistency.
    """

    DRAFT = "draft"  # Maps to EntityStatus.DRAFT
    PUBLISHED = "published"  # Knowledge-specific (maps to COMPLETED)
    ARCHIVED = "archived"  # Maps to EntityStatus.ARCHIVED
    UNDER_REVIEW = "under_review"  # Knowledge-specific (maps to IN_PROGRESS)

    def to_activity_status(self) -> "EntityStatus":
        """Convert to base activity status when needed for cross-domain operations"""
        # Import here to avoid circular dependency
        from .entity_enums import EntityStatus

        mapping = {
            KnowledgeStatus.DRAFT: EntityStatus.DRAFT,
            KnowledgeStatus.PUBLISHED: EntityStatus.COMPLETED,
            KnowledgeStatus.ARCHIVED: EntityStatus.ARCHIVED,
            KnowledgeStatus.UNDER_REVIEW: EntityStatus.ACTIVE,
        }
        return mapping.get(self, EntityStatus.DRAFT)


class ContentType(StrEnum):
    """
    Types of knowledge content for faceted search.

    Used for content classification and filtering in search.
    """

    CONCEPT = "concept"
    PRACTICE = "practice"
    PRINCIPLE = "principle"
    THEORY = "theory"
    EXAMPLE = "example"
    EXPLANATION = "explanation"
    REFERENCE = "reference"
    EXERCISE = "exercise"  # Hands-on exercises
    ASSESSMENT = "assessment"  # Tests/quizzes
    RESOURCE = "resource"  # External resources
    SUMMARY = "summary"  # Quick reference
    TUTORIAL = "tutorial"  # Step-by-step guide

    def get_icon(self) -> str:
        """Get emoji icon for this content type"""
        icons = {
            ContentType.CONCEPT: "💡",
            ContentType.PRACTICE: "🎯",
            ContentType.PRINCIPLE: "⚖️",
            ContentType.THEORY: "🔬",
            ContentType.EXAMPLE: "📖",
            ContentType.EXPLANATION: "💬",
            ContentType.REFERENCE: "📚",
            ContentType.EXERCISE: "✏️",
            ContentType.ASSESSMENT: "📊",
            ContentType.RESOURCE: "🔗",
            ContentType.SUMMARY: "📝",
            ContentType.TUTORIAL: "🎓",
        }
        return icons.get(self, "📄")

    def get_color(self) -> str:
        """Get suggested color for UI rendering"""
        colors = {
            ContentType.CONCEPT: "#3B82F6",  # Blue
            ContentType.PRACTICE: "#10B981",  # Green
            ContentType.PRINCIPLE: "#8B5CF6",  # Purple
            ContentType.THEORY: "#06B6D4",  # Cyan
            ContentType.EXAMPLE: "#F59E0B",  # Amber
            ContentType.EXPLANATION: "#EC4899",  # Pink
            ContentType.REFERENCE: "#14B8A6",  # Teal
            ContentType.EXERCISE: "#F59E0B",  # Amber
            ContentType.ASSESSMENT: "#EF4444",  # Red
            ContentType.RESOURCE: "#06B6D4",  # Cyan
            ContentType.SUMMARY: "#6B7280",  # Gray
            ContentType.TUTORIAL: "#EC4899",  # Pink
        }
        return colors.get(self, "#6B7280")

    def get_search_synonyms(self) -> tuple[str, ...]:
        """Return search terms that match this content type"""
        synonyms = {
            ContentType.CONCEPT: ("concept", "idea", "understanding", "theory"),
            ContentType.PRACTICE: ("practice", "drill", "exercise", "apply", "hands-on"),
            ContentType.PRINCIPLE: ("principle", "rule", "law", "guideline", "tenet"),
            ContentType.THEORY: ("theory", "hypothesis", "framework", "model"),
            ContentType.EXAMPLE: ("example", "sample", "illustration", "demo", "case"),
            ContentType.EXPLANATION: ("explanation", "description", "clarification", "breakdown"),
            ContentType.REFERENCE: ("reference", "documentation", "guide", "manual"),
            ContentType.EXERCISE: ("exercise", "workout", "problem", "activity"),
            ContentType.ASSESSMENT: ("assessment", "test", "quiz", "exam", "evaluation"),
            ContentType.RESOURCE: ("resource", "tool", "material", "link"),
            ContentType.SUMMARY: ("summary", "overview", "recap", "outline", "brief"),
            ContentType.TUTORIAL: ("tutorial", "walkthrough", "lesson", "guide", "how-to"),
        }
        return synonyms.get(self, ())

    def get_search_description(self) -> str:
        """Human-readable description for search UI"""
        descriptions = {
            ContentType.CONCEPT: "Core concepts and ideas",
            ContentType.PRACTICE: "Practice exercises and drills",
            ContentType.PRINCIPLE: "Fundamental principles and rules",
            ContentType.THEORY: "Theoretical frameworks",
            ContentType.EXAMPLE: "Examples and illustrations",
            ContentType.EXPLANATION: "Detailed explanations",
            ContentType.REFERENCE: "Reference materials",
            ContentType.EXERCISE: "Hands-on exercises",
            ContentType.ASSESSMENT: "Tests and assessments",
            ContentType.RESOURCE: "External resources",
            ContentType.SUMMARY: "Summaries and overviews",
            ContentType.TUTORIAL: "Step-by-step tutorials",
        }
        return descriptions.get(self, "")

    @classmethod
    def from_search_text(cls, text: str) -> list["ContentType"]:
        """Find matching content types from search text"""
        text_lower = text.lower()
        return [
            content_type
            for content_type in cls
            if any(synonym in text_lower for synonym in content_type.get_search_synonyms())
        ]


class SELCategory(StrEnum):
    """
    Social Emotional Learning (SEL) framework categories.

    NOUS is built on the SEL framework, providing personalized
    learning journeys through five core competencies.
    """

    SELF_AWARENESS = "self_awareness"
    SELF_MANAGEMENT = "self_management"
    SOCIAL_AWARENESS = "social_awareness"
    RELATIONSHIP_SKILLS = "relationship_skills"
    RESPONSIBLE_DECISION_MAKING = "responsible_decision_making"

    def get_icon(self) -> str:
        """Get emoji icon for this SEL category"""
        icons = {
            SELCategory.SELF_AWARENESS: "🧘",
            SELCategory.SELF_MANAGEMENT: "🎯",
            SELCategory.SOCIAL_AWARENESS: "👥",
            SELCategory.RELATIONSHIP_SKILLS: "🤝",
            SELCategory.RESPONSIBLE_DECISION_MAKING: "⚖️",
        }
        return icons.get(self, "📚")

    def get_color(self) -> str:
        """Get hex color for UI rendering"""
        colors = {
            SELCategory.SELF_AWARENESS: "#8B5CF6",  # Purple
            SELCategory.SELF_MANAGEMENT: "#3B82F6",  # Blue
            SELCategory.SOCIAL_AWARENESS: "#10B981",  # Green
            SELCategory.RELATIONSHIP_SKILLS: "#F59E0B",  # Amber
            SELCategory.RESPONSIBLE_DECISION_MAKING: "#DC2626",  # Red
        }
        return colors.get(self, "#6B7280")

    def get_description(self) -> str:
        """Get human-readable description of this SEL competency"""
        descriptions = {
            SELCategory.SELF_AWARENESS: "Understanding your emotions, values, and strengths",
            SELCategory.SELF_MANAGEMENT: "Managing emotions, behaviors, and achieving goals",
            SELCategory.SOCIAL_AWARENESS: "Understanding and empathizing with others",
            SELCategory.RELATIONSHIP_SKILLS: "Building and maintaining healthy relationships",
            SELCategory.RESPONSIBLE_DECISION_MAKING: "Making ethical, constructive choices",
        }
        return descriptions.get(self, "")
