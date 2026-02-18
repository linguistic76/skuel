"""
KuBase - Common Fields and Methods for All Knowledge Types
==========================================================

Base frozen dataclass shared by all 15 KuType domain subclasses.
Contains ~48 fields genuinely common to every manifestation of knowledge.

This is Phase 0 of the Ku decomposition: extracting the common base without
breaking any existing code. Ku inherits from KuBase and adds domain-specific fields.

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
See: /.claude/plans/ku-decomposition-domain-types.md
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from math import exp, log
from typing import TYPE_CHECKING, Any, ClassVar, Self

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO

from core.models.enums import Domain, KuComplexity, LearningLevel, SELCategory, SystemConstants
from core.models.enums.ku_enums import KuStatus, KuType
from core.models.enums.metadata_enums import Visibility
from core.models.query import QueryIntent


@dataclass(frozen=True)
class KuBase:
    """
    Base frozen dataclass for all knowledge types.

    Contains ~48 fields shared by every KuType manifestation:
    Identity (7), Content (4), Status (2), Learning (7), Sharing (1),
    Substance (10), Meta (6), Embedding (3), Cache (2).

    Domain-specific subclasses (TaskKu, GoalKu, HabitKu, etc.) inherit
    from KuBase and add their own fields and methods.
    """

    # Neo4j node label — all KuType subclasses share the :Ku label
    _neo4j_label: ClassVar[str] = "Ku"

    # =========================================================================
    # IDENTITY
    # =========================================================================
    uid: str
    title: str
    ku_type: KuType = KuType.CURRICULUM
    user_uid: str | None = None  # None for shared types (CURRICULUM, LS, LP)
    parent_ku_uid: str | None = None  # Derivation chain — what Ku this was based on
    domain: Domain = Domain.KNOWLEDGE
    created_by: str | None = None

    # =========================================================================
    # CONTENT
    # =========================================================================
    content: str | None = None  # Body text (submissions, AI output, feedback)
    summary: str = ""  # Brief description
    description: str | None = None  # Extended description (used by all activity domains)
    word_count: int = 0

    # =========================================================================
    # STATUS
    # =========================================================================
    status: KuStatus = None  # type: ignore[assignment]  # Set in __post_init__
    priority: str | None = None  # Priority enum value (LOW/MEDIUM/HIGH/CRITICAL)

    # =========================================================================
    # LEARNING METADATA
    # =========================================================================
    complexity: KuComplexity = KuComplexity.MEDIUM
    learning_level: LearningLevel = LearningLevel.BEGINNER
    sel_category: SELCategory | None = None
    quality_score: float = 0.0
    estimated_time_minutes: int = 15
    difficulty_rating: float = 0.5  # 0.0-1.0
    semantic_links: tuple[str, ...] = ()

    # =========================================================================
    # SHARING
    # =========================================================================
    visibility: Visibility = None  # type: ignore[assignment]  # Set in __post_init__

    # =========================================================================
    # SUBSTANCE TRACKING
    # "Applied knowledge, not pure theory"
    # Updated via event-driven architecture (TaskKnowledgeApplied, etc.)
    # Defaults to 0 on non-curriculum types (zero cost).
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

    # =========================================================================
    # META
    # =========================================================================
    tags: tuple[str, ...] = ()
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    # Embedding fields for Neo4j GenAI vector search
    embedding: tuple[float, ...] | None = None
    embedding_model: str | None = None
    embedding_updated_at: datetime | None = None  # type: ignore[assignment]

    # Substance cache (lazy calculation with 1-hour TTL)
    _cached_substance_score: float | None = None
    _substance_cache_timestamp: datetime | None = None  # type: ignore[assignment]

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    def __post_init__(self) -> None:
        """Set conditional defaults based on ku_type."""
        now = datetime.now()

        if self.created_at is None:
            object.__setattr__(self, "created_at", now)
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", now)
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

        # Default status from KuType (type-aware)
        if self.status is None:
            object.__setattr__(self, "status", self.ku_type.default_status())

        # Default visibility: shared types are PUBLIC, others are PRIVATE
        if self.visibility is None:
            if self.ku_type in {
                KuType.CURRICULUM,
                KuType.LEARNING_STEP,
                KuType.LEARNING_PATH,
            }:
                object.__setattr__(self, "visibility", Visibility.PUBLIC)
            else:
                object.__setattr__(self, "visibility", Visibility.PRIVATE)

        # Compute word_count from content if not set
        if self.word_count == 0 and self.content:
            object.__setattr__(self, "word_count", len(self.content.split()))

    # =========================================================================
    # KU TYPE CHECKS
    # =========================================================================

    @property
    def is_curriculum(self) -> bool:
        return self.ku_type == KuType.CURRICULUM

    @property
    def is_submission(self) -> bool:
        return self.ku_type == KuType.SUBMISSION

    @property
    def is_ai_report(self) -> bool:
        return self.ku_type == KuType.AI_REPORT

    @property
    def is_feedback_report(self) -> bool:
        return self.ku_type == KuType.FEEDBACK_REPORT

    @property
    def is_task(self) -> bool:
        return self.ku_type == KuType.TASK

    @property
    def is_goal(self) -> bool:
        return self.ku_type == KuType.GOAL

    @property
    def is_habit(self) -> bool:
        return self.ku_type == KuType.HABIT

    @property
    def is_event(self) -> bool:
        return self.ku_type == KuType.EVENT

    @property
    def is_choice(self) -> bool:
        return self.ku_type == KuType.CHOICE

    @property
    def is_principle(self) -> bool:
        return self.ku_type == KuType.PRINCIPLE

    @property
    def is_life_path(self) -> bool:
        return self.ku_type == KuType.LIFE_PATH

    @property
    def is_user_owned(self) -> bool:
        """Check if this Ku has an owner (non-shared type)."""
        return self.user_uid is not None

    @property
    def is_derived(self) -> bool:
        """Check if this Ku was derived from another Ku."""
        return self.parent_ku_uid is not None

    # =========================================================================
    # STATUS / PROCESSING
    # =========================================================================

    @property
    def is_completed(self) -> bool:
        return self.status == KuStatus.COMPLETED

    @property
    def is_processing(self) -> bool:
        return self.status == KuStatus.PROCESSING

    @property
    def is_failed(self) -> bool:
        return self.status == KuStatus.FAILED

    @property
    def is_draft(self) -> bool:
        return self.status == KuStatus.DRAFT

    @property
    def is_archived(self) -> bool:
        return self.status == KuStatus.ARCHIVED

    # =========================================================================
    # SHARING
    # =========================================================================

    def is_shareable(self) -> bool:
        """Only completed Ku can be shared (quality control)."""
        return self.status == KuStatus.COMPLETED

    def can_view(self, viewer_uid: str, shared_user_uids: set[str] | None = None) -> bool:
        """
        Check if a user can view this Ku.

        Access granted if:
        - Ku is PUBLIC (all curriculum)
        - Viewer is the owner
        - Ku is SHARED and viewer is in shared_user_uids
        """
        if self.visibility == Visibility.PUBLIC:
            return True
        if self.user_uid and viewer_uid == self.user_uid:
            return True
        if self.visibility == Visibility.SHARED and shared_user_uids:
            return viewer_uid in shared_user_uids
        return False

    # =========================================================================
    # KNOWLEDGE CARRIER PROTOCOL
    # =========================================================================

    def knowledge_relevance(self) -> float:
        """KU IS knowledge — always returns 1.0."""
        return 1.0

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """KU IS knowledge — returns its own UID."""
        return (self.uid,)

    # =========================================================================
    # BUSINESS LOGIC
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

    def has_tag(self, tag: str) -> bool:
        return tag.lower() in [t.lower() for t in self.tags]

    def is_connected(self) -> bool:
        """Check if connected to other Ku via semantic links."""
        return len(self.semantic_links) > 0

    def get_all_connections(self) -> set[str]:
        """Get semantic link connections. For full graph traversal, use services."""
        return set(self.semantic_links)

    def matches_domain(self, domain: Domain) -> bool:
        return self.domain == domain

    def is_foundational(self) -> bool:
        """Basic complexity + high quality = trusted foundation."""
        return self.complexity == KuComplexity.BASIC and self.is_high_quality()

    def is_terminal(self) -> bool:
        return self.is_advanced()

    def complexity_score(self) -> int:
        """1 for basic, 2 for medium, 3 for advanced."""
        mapping = {KuComplexity.BASIC: 1, KuComplexity.MEDIUM: 2, KuComplexity.ADVANCED: 3}
        return mapping.get(self.complexity, 2)

    def is_recent(self, days: int = 7) -> bool:
        if not self.created_at:
            return False
        return (datetime.now() - self.created_at).days <= days

    def is_updated(self) -> bool:
        if not self.created_at or not self.updated_at:
            return False
        return self.updated_at > self.created_at

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
    # DISPLAY
    # =========================================================================

    @property
    def name(self) -> str:
        """Alias for title — backward compat for code referencing old domain models."""
        return self.title

    @property
    def key_topics(self) -> tuple[str, ...]:
        """Key topics — alias for tags."""
        return self.tags

    # =========================================================================
    # GENERIC CONVERSION (used by domain subclasses — TaskKu, GoalKu, etc.)
    # =========================================================================

    @classmethod
    def _from_dto(cls, dto: "KuDTO") -> Self:
        """
        Generic: extract only fields defined on THIS class from the unified DTO.

        Uses dataclasses.fields(cls) to determine which fields to extract,
        ensuring each subclass only gets its own fields + inherited KuBase fields.
        Converts lists to tuples for frozen dataclass compatibility.
        """
        field_names = {f.name for f in dataclasses.fields(cls) if not f.name.startswith("_")}
        kwargs: dict[str, Any] = {}
        for name in field_names:
            value = getattr(dto, name, None)
            if isinstance(value, list):
                value = tuple(value)
            kwargs[name] = value
        return cls(**kwargs)

    def to_dto(self) -> "KuDTO":
        """
        Generic: convert any KuBase subclass to unified KuDTO.

        Creates KuDTO with fields from this instance. Fields not present on
        the subclass get KuDTO defaults (None, 0, empty list, etc.).
        Converts tuples back to lists for DTO mutability.

        Skips infrastructure fields (embedding, cache) that don't exist on KuDTO
        per ADR-037 (embedding infrastructure separation).
        """
        from core.models.ku.ku_dto import KuDTO

        dto_field_names = {f.name for f in dataclasses.fields(KuDTO)}
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
        return KuDTO(**kwargs)

    # =========================================================================
    # DISPLAY
    # =========================================================================

    def __str__(self) -> str:
        return f"Ku(uid={self.uid}, type={self.ku_type.value}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"Ku(uid='{self.uid}', ku_type={self.ku_type}, "
            f"title='{self.title}', domain={self.domain}, "
            f"status={self.status}, user_uid={self.user_uid})"
        )
