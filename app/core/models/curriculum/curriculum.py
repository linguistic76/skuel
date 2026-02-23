"""
Curriculum - Curriculum Domain Model (Intermediate Class)
============================================================

Frozen dataclass for curriculum-carrying entities. Intermediate class between
Entity and curriculum-specific subclasses (LearningStep, LearningPath).

Adds 21 fields to Entity:
- Learning metadata (9): complexity, learning_level, sel_category, quality_score,
  estimated_time_minutes, difficulty_rating, semantic_links, target_age_range,
  learning_objectives
- Substance tracking (10): 5 counters + 5 last-dates
- Cache (2): _cached_substance_score, _substance_cache_timestamp

Hierarchy:
    Entity (~29 fields)
    └── Curriculum(Entity) +21 fields, ~30 methods
        ├── LearningStep(Curriculum) +9 fields
        ├── LearningPath(Curriculum) +4 fields
        └── Resource(Entity) — NOT Curriculum (Tier A raw content)

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
See: /docs/architecture/knowledge_substance_philosophy.md
"""

from dataclasses import dataclass
from datetime import datetime
from math import exp, log
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.curriculum.curriculum_dto import CurriculumDTO
    from core.models.entity_dto import EntityDTO

from core.models.enums import Domain, KuComplexity, LearningLevel, SELCategory, SystemConstants
from core.models.enums.ku_enums import EntityType
from core.models.entity import Entity
from core.models.query import QueryIntent


@dataclass(frozen=True)
class Curriculum(Entity):
    """
    Immutable domain model for curriculum knowledge (EntityType.CURRICULUM).

    Intermediate class adding learning metadata, substance tracking, and
    curriculum-specific methods to Entity. LearningStep and LearningPath
    inherit from Curriculum.

    Zero extra fields beyond the 21 inherited additions — CURRICULUM is the
    base knowledge carrier. All curriculum-specific structure lives in Neo4j
    graph relationships (ORGANIZES, PRIMARY_KNOWLEDGE, SUPPORTING_KNOWLEDGE).

    Note: EntityType.RESOURCE uses Resource (Tier A raw content, inherits Entity directly).
    """

    def __post_init__(self) -> None:
        """Force ku_type=CURRICULUM if not already set, then delegate to Entity."""
        if self.ku_type != EntityType.CURRICULUM:
            object.__setattr__(self, "ku_type", EntityType.CURRICULUM)
        super().__post_init__()

    # =========================================================================
    # LEARNING METADATA (7 existing + 2 new = 9)
    # =========================================================================
    complexity: KuComplexity = KuComplexity.MEDIUM
    learning_level: LearningLevel = LearningLevel.BEGINNER
    sel_category: SELCategory | None = None
    quality_score: float = 0.0
    estimated_time_minutes: int = 15
    difficulty_rating: float = 0.5  # 0.0-1.0
    semantic_links: tuple[str, ...] = ()
    target_age_range: tuple[int, int] | None = None  # e.g. (8, 12) for ages 8-12
    learning_objectives: tuple[str, ...] = ()  # What the learner should gain

    # =========================================================================
    # SUBSTANCE TRACKING
    # "Applied knowledge, not pure theory"
    # Updated via event-driven architecture (TaskKnowledgeApplied, etc.)
    # =========================================================================
    times_applied_in_tasks: int = 0
    times_practiced_in_events: int = 0
    times_built_into_habits: int = 0
    journal_reflections_count: int = 0
    choices_informed_count: int = 0

    last_applied_date: datetime | None = None  # type: ignore[assignment]
    last_practiced_date: datetime | None = None  # type: ignore[assignment]
    last_built_into_habit_date: datetime | None = None  # type: ignore[assignment]
    last_reflected_date: datetime | None = None  # type: ignore[assignment]
    last_choice_informed_date: datetime | None = None  # type: ignore[assignment]

    # Substance cache (lazy calculation with 1-hour TTL)
    _cached_substance_score: float | None = None
    _substance_cache_timestamp: datetime | None = None  # type: ignore[assignment]

    # =========================================================================
    # CURRICULUM-SPECIFIC METHODS
    # =========================================================================

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the curriculum content."""
        text = self.description or self.content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def explain_existence(self) -> str:
        """Explain why this curriculum exists."""
        return self.description or self.summary or f"curriculum: {self.title}"

    # =========================================================================
    # LEARNING METHODS
    # =========================================================================

    def is_advanced(self) -> bool:
        return self.complexity == KuComplexity.ADVANCED

    def is_basic(self) -> bool:
        return self.complexity == KuComplexity.BASIC

    def requires_prerequisites(self) -> bool:
        """Advanced tech knowledge always requires prerequisites."""
        return self.domain == Domain.TECH and self.is_advanced()

    def is_high_quality(self) -> bool:
        return self.quality_score >= SystemConstants.MIN_QUALITY_THRESHOLD

    def is_semantic_analyzed(self) -> bool:
        return self.quality_score > 0 and len(self.semantic_links) > 0

    def is_connected(self) -> bool:
        """Check if connected to other Ku via semantic links."""
        return len(self.semantic_links) > 0

    def get_all_connections(self) -> set[str]:
        """Get semantic link connections. For full graph traversal, use services."""
        return set(self.semantic_links)

    def is_foundational(self) -> bool:
        """Basic complexity + high quality = trusted foundation."""
        return self.complexity == KuComplexity.BASIC and self.is_high_quality()

    def is_terminal(self) -> bool:
        return self.is_advanced()

    def complexity_score(self) -> int:
        """1 for basic, 2 for medium, 3 for advanced."""
        mapping = {KuComplexity.BASIC: 1, KuComplexity.MEDIUM: 2, KuComplexity.ADVANCED: 3}
        return mapping.get(self.complexity, 2)

    # =========================================================================
    # GRAPH INTELLIGENCE (Intent Suggestion)
    # =========================================================================

    def get_suggested_query_intent(self) -> QueryIntent:
        """Get suggested QueryIntent based on knowledge characteristics."""
        if self.is_foundational():
            return QueryIntent.HIERARCHICAL
        elif self.is_terminal():
            return QueryIntent.PREREQUISITE
        elif self.is_connected():
            return QueryIntent.RELATIONSHIP
        elif self.is_basic():
            return QueryIntent.PRACTICE
        else:
            return QueryIntent.EXPLORATORY

    # =========================================================================
    # SEL FRAMEWORK INTEGRATION
    # =========================================================================

    def is_beginner_level(self) -> bool:
        return self.learning_level == LearningLevel.BEGINNER

    def is_intermediate_level(self) -> bool:
        return self.learning_level == LearningLevel.INTERMEDIATE

    def is_advanced_level(self) -> bool:
        return self.learning_level == LearningLevel.ADVANCED

    def is_expert_level(self) -> bool:
        return self.learning_level == LearningLevel.EXPERT

    def is_appropriate_for_level(self, user_level: LearningLevel) -> bool:
        """Check if this KU is appropriate for a user's learning level."""
        level_hierarchy = {
            LearningLevel.BEGINNER: [LearningLevel.BEGINNER],
            LearningLevel.INTERMEDIATE: [LearningLevel.BEGINNER, LearningLevel.INTERMEDIATE],
            LearningLevel.ADVANCED: [
                LearningLevel.BEGINNER,
                LearningLevel.INTERMEDIATE,
                LearningLevel.ADVANCED,
            ],
            LearningLevel.EXPERT: [
                LearningLevel.BEGINNER,
                LearningLevel.INTERMEDIATE,
                LearningLevel.ADVANCED,
                LearningLevel.EXPERT,
            ],
        }
        return self.learning_level in level_hierarchy.get(user_level, [])

    def is_quick_win(self) -> bool:
        """Short duration + low difficulty = great for momentum."""
        return self.estimated_time_minutes <= 10 and self.difficulty_rating <= 0.4

    def is_challenging(self) -> bool:
        return self.difficulty_rating >= 0.7

    def matches_time_available(self, minutes_available: int) -> bool:
        return self.estimated_time_minutes <= minutes_available

    def get_sel_context(self) -> dict[str, Any]:
        """Get SEL-specific context for adaptive curriculum delivery."""
        base: dict[str, Any] = {
            "learning_level": self.learning_level.value,
            "estimated_time_minutes": self.estimated_time_minutes,
            "difficulty_rating": self.difficulty_rating,
            "is_beginner_friendly": self.is_beginner_level(),
            "is_quick_win": self.is_quick_win(),
            "is_challenging": self.is_challenging(),
        }
        if self.sel_category is None:
            base["sel_category"] = None
            base["sel_category_icon"] = ""
            base["sel_category_color"] = ""
            base["sel_category_description"] = ""
        else:
            base["sel_category"] = self.sel_category.value
            base["sel_category_icon"] = self.sel_category.get_icon()
            base["sel_category_color"] = self.sel_category.get_color()
            base["sel_category_description"] = self.sel_category.get_description()
        return base

    # =========================================================================
    # SUBSTANCE TRACKING
    # "Applied knowledge, not pure theory"
    # Overrides Entity stubs with real implementations.
    # =========================================================================

    def substance_score(self, force_recalculate: bool = False) -> float:
        """
        Calculate substance score with time decay (spaced repetition).

        Weighting:
            Habits  0.10/habit  (max 0.30) — lifestyle integration
            Journals 0.07/entry (max 0.20) — metacognition
            Events  0.05/event  (max 0.25) — dedicated practice
            Tasks   0.05/task   (max 0.25) — practical application
            Choices 0.07/choice (max 0.15) — decision wisdom

        Time decay: exponential with 30-day half-life, floor at 0.2.
        """
        if (
            not force_recalculate
            and self._cached_substance_score is not None
            and self._substance_cache_timestamp
        ):
            cache_age = datetime.now() - self._substance_cache_timestamp
            if cache_age.total_seconds() < 3600:
                return self._cached_substance_score

        score = self._calculate_substance_with_decay()
        object.__setattr__(self, "_cached_substance_score", score)
        object.__setattr__(self, "_substance_cache_timestamp", datetime.now())
        return score

    def _calculate_substance_with_decay(self) -> float:
        """Internal calculation with time-based decay."""
        now = datetime.now()
        half_life_days = 30.0
        score = 0.0

        if self.times_built_into_habits > 0:
            w = self._decay_weight(self.last_built_into_habit_date, now, half_life_days)
            score += min(0.30, self.times_built_into_habits * 0.10 * w)

        if self.journal_reflections_count > 0:
            w = self._decay_weight(self.last_reflected_date, now, half_life_days)
            score += min(0.20, self.journal_reflections_count * 0.07 * w)

        if self.times_practiced_in_events > 0:
            w = self._decay_weight(self.last_practiced_date, now, half_life_days)
            score += min(0.25, self.times_practiced_in_events * 0.05 * w)

        if self.times_applied_in_tasks > 0:
            w = self._decay_weight(self.last_applied_date, now, half_life_days)
            score += min(0.25, self.times_applied_in_tasks * 0.05 * w)

        if self.choices_informed_count > 0:
            w = self._decay_weight(self.last_choice_informed_date, now, half_life_days)
            score += min(0.15, self.choices_informed_count * 0.07 * w)

        return min(1.0, score)

    def _decay_weight(
        self, last_use_date: datetime | None, now: datetime, half_life_days: float
    ) -> float:
        """Exponential decay: e^(-days / half_life), floor at 0.2."""
        if not last_use_date:
            return 0.2
        days_since_use = (now - last_use_date).days
        return max(0.2, exp(-days_since_use / half_life_days))

    def is_theoretical_only(self) -> bool:
        """Substance < 0.2 = pure theory."""
        return self.substance_score() < 0.2

    def is_well_practiced(self) -> bool:
        """Substance >= 0.7 = deeply embedded."""
        return self.substance_score() >= 0.7

    def needs_more_practice(self) -> bool:
        return (
            self.times_applied_in_tasks < 3
            or self.times_practiced_in_events < 2
            or self.times_built_into_habits == 0
        )

    def get_substantiation_gaps(self) -> list[str]:
        """Identify missing substantiation types for UI recommendations."""
        gaps = []
        if self.times_applied_in_tasks == 0:
            gaps.append("No tasks apply this knowledge")
        if self.times_practiced_in_events == 0:
            gaps.append("No events practice this knowledge")
        if self.times_built_into_habits == 0:
            gaps.append("Not built into any habits")
        if self.journal_reflections_count == 0:
            gaps.append("No journal reflections")
        if self.choices_informed_count == 0:
            gaps.append("Has not informed any choices/decisions")
        return gaps

    def needs_review(self) -> bool:
        """Spaced repetition: once-substantiated knowledge decayed below 0.5."""
        return self.substance_score() < 0.5 and self._was_once_substantiated()

    def _was_once_substantiated(self) -> bool:
        return (
            self.times_applied_in_tasks > 2
            or self.times_practiced_in_events > 1
            or self.times_built_into_habits > 0
        )

    def days_until_review_needed(self) -> int | None:
        """Predict when substance drops below 0.5, or None if never substantiated."""
        if not self._was_once_substantiated():
            return None

        current_score = self.substance_score(force_recalculate=True)
        if current_score < 0.5:
            return 0

        activity_dates = [
            d
            for d in [
                self.last_applied_date,
                self.last_practiced_date,
                self.last_built_into_habit_date,
                self.last_reflected_date,
                self.last_choice_informed_date,
            ]
            if d is not None
        ]
        if not activity_dates:
            return 0

        most_recent_date = max(activity_dates)
        half_life_days = 30
        threshold_days = -half_life_days * log(0.5)  # ~21 days
        days_since_use = (datetime.now() - most_recent_date).days
        return max(0, int(threshold_days - days_since_use))

    def get_substantiation_summary(self) -> dict[str, Any]:
        """Comprehensive substantiation summary for UI display."""
        score = self.substance_score()
        gaps = self.get_substantiation_gaps()

        task_progress = min(1.0, (self.times_applied_in_tasks * 0.05) / 0.25)
        event_progress = min(1.0, (self.times_practiced_in_events * 0.05) / 0.25)
        habit_progress = min(1.0, (self.times_built_into_habits * 0.10) / 0.30)
        journal_progress = min(1.0, (self.journal_reflections_count * 0.07) / 0.20)
        choice_progress = min(1.0, (self.choices_informed_count * 0.07) / 0.15)

        recommendations = []
        if "No tasks apply this knowledge" in gaps:
            recommendations.append(
                {
                    "type": "task",
                    "message": f"Create a task that applies: {self.title}",
                    "impact": "+0.05 substance per task (max +0.25)",
                }
            )
        if "Not built into any habits" in gaps:
            recommendations.append(
                {
                    "type": "habit",
                    "message": f"Build a habit around: {self.title}",
                    "impact": "+0.10 substance per habit (max +0.30)",
                }
            )
        if "No journal reflections" in gaps:
            recommendations.append(
                {
                    "type": "journal",
                    "message": f"Reflect on your experience with: {self.title}",
                    "impact": "+0.07 substance per reflection (max +0.20)",
                }
            )

        if score >= 0.7:
            status = "Well practiced! Keep it up."
        elif score >= 0.5:
            status = "Solid foundation. Practice more to deepen mastery."
        elif score >= 0.3:
            status = "Applied but not yet integrated. Build habits."
        elif score > 0:
            status = "Theoretical knowledge. Apply in projects."
        else:
            status = "Pure theory. Create tasks and practice."

        return {
            "substance_score": round(score, 2),
            "breakdown": {
                "tasks": {
                    "count": self.times_applied_in_tasks,
                    "progress": round(task_progress, 2),
                    "max_score": 0.25,
                },
                "events": {
                    "count": self.times_practiced_in_events,
                    "progress": round(event_progress, 2),
                    "max_score": 0.25,
                },
                "habits": {
                    "count": self.times_built_into_habits,
                    "progress": round(habit_progress, 2),
                    "max_score": 0.30,
                },
                "journals": {
                    "count": self.journal_reflections_count,
                    "progress": round(journal_progress, 2),
                    "max_score": 0.20,
                },
                "choices": {
                    "count": self.choices_informed_count,
                    "progress": round(choice_progress, 2),
                    "max_score": 0.15,
                },
            },
            "gaps": gaps,
            "review_status": {
                "needs_review": self.needs_review(),
                "days_until_review": self.days_until_review_needed(),
            },
            "recommendations": recommendations,
            "status_message": status,
            "is_theoretical_only": self.is_theoretical_only(),
            "is_well_practiced": self.is_well_practiced(),
        }

    # =========================================================================
    # CONVERSION (generic -- uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | CurriculumDTO") -> "Curriculum":
        """Create Curriculum from an EntityDTO or CurriculumDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "CurriculumDTO":  # type: ignore[override]
        """Convert Curriculum to domain-specific CurriculumDTO."""
        import dataclasses

        from core.models.curriculum.curriculum_dto import CurriculumDTO

        dto_field_names = {f.name for f in dataclasses.fields(CurriculumDTO)}
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            if f.name.startswith("_"):
                continue
            if f.name not in dto_field_names:
                continue
            value = getattr(self, f.name)
            if isinstance(value, tuple):
                value = list(value)
            kwargs[f.name] = value
        return CurriculumDTO(**kwargs)

    def __str__(self) -> str:
        return f"Curriculum(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"Curriculum(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, domain={self.domain}, "
            f"complexity={self.complexity})"
        )
