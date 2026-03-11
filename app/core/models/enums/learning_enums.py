"""
Learning Enums - Education, Knowledge, and Mastery Tracking
============================================================

Enums for learning levels, knowledge types, mastery tracking, and SEL framework.
"""

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .entity_enums import EntityStatus


class KuComplexity(StrEnum):
    """
    Complexity level of a Knowledge Unit.

    Used to indicate difficulty/sophistication of curriculum content.
    """

    BASIC = "basic"
    MEDIUM = "medium"
    ADVANCED = "advanced"


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

    @classmethod
    def from_search_text(cls, text: str) -> list["LearningLevel"]:
        """Find matching learning levels from search text"""
        text_lower = text.lower()
        return [
            level
            for level in cls
            if any(synonym in text_lower for synonym in level.get_search_synonyms())
        ]


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


class PracticeLevel(StrEnum):
    """Difficulty/expertise levels"""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

    def to_learning_level(self) -> LearningLevel:
        """Convert to LearningLevel"""
        return LearningLevel(self.value)


class KnowledgeType(StrEnum):
    """Types of knowledge for classification"""

    DECLARATIVE = "declarative"  # What is...
    PROCEDURAL = "procedural"  # How to...
    CONCEPTUAL = "conceptual"  # Why...
    METACOGNITIVE = "metacognitive"  # When to...


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


# Domain to SEL mapping - Integrates existing SKUEL domains into SEL framework
DOMAIN_SEL_MAPPING = {
    "principles": SELCategory.SELF_AWARENESS,
    "habits": SELCategory.SELF_MANAGEMENT,
    "goals": SELCategory.SELF_MANAGEMENT,
    "choices": SELCategory.RESPONSIBLE_DECISION_MAKING,
}
