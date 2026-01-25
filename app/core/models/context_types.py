"""
Context-First Types - User-Aware Entity Representations
========================================================

These types represent entities enriched with user context, enabling
personalized filtering, ranking, and insights in relationship queries.

**Core Philosophy:** "Filter by readiness, rank by relevance, enrich with insights"

**Pattern Overview:**
- Standard relationship queries return raw entities
- Context-first queries return ContextualEntity types
- Each type includes readiness, relevance, and actionable insights

**Naming Convention:**
- Standard: get_task_dependencies(uid) -> list[Task]
- Context-First: get_task_dependencies_for_user(uid, context) -> ContextualDependencies

**Entity Type Discriminator (November 28, 2025):**

All ContextualEntity subclasses have an `entity_type` property for unified dispatch:

| Class               | entity_type   |
|---------------------|---------------|
| ContextualEntity    | "entity"      |
| ContextualTask      | "task"        |
| ContextualKnowledge | "knowledge"   |
| ContextualHabit     | "habit"       |
| ContextualGoal      | "goal"        |
| ContextualEvent     | "event"       |
| ContextualPrinciple | "principle"   |
| ContextualChoice    | "choice"      |

This enables dictionary dispatch and match statements:

```python
# Dictionary dispatch
categorizers = {"task": task_list, "knowledge": ku_list}
for entity in entities:
    if entity.entity_type in categorizers:
        categorizers[entity.entity_type].append(entity)

# Match statement (Python 3.10+)
match entity.entity_type:
    case "task":
        handle_task(entity)
    case "knowledge":
        handle_knowledge(entity)
```

**Integration Points:**
- UserContext: Provides ~240 fields for personalization
- Relationship Services: Consume context to enrich results
- UserContextIntelligence: Combines context-first queries for flagship methods

Version: 1.1.0
Date: November 28, 2025
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# =============================================================================
# BASE CONTEXTUAL TYPES
# =============================================================================


@dataclass(frozen=True)
class ContextualEntity:
    """
    Base class for entities enriched with user context.

    All contextual types derive from this, ensuring consistent
    scoring and insight patterns across domains.

    **Scores (0.0-1.0):**
    - readiness_score: How ready is user for this? (prerequisites met)
    - relevance_score: How relevant to user's goals/priorities?
    - priority_score: Combined priority for ranking

    **Insights:**
    - blocking_reasons: What prevents user from engaging?
    - unlocks: What completing/mastering this enables
    - learning_gaps: Knowledge needed but not mastered
    """

    uid: str
    title: str

    # Context-derived scores (0.0-1.0)
    readiness_score: float = 0.0
    relevance_score: float = 0.0
    priority_score: float = 0.0

    # Context-derived insights
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    unlocks: tuple[str, ...] = field(default_factory=tuple)
    learning_gaps: tuple[str, ...] = field(default_factory=tuple)

    # Metadata
    enriched_at: datetime = field(default_factory=datetime.now)

    def is_ready(self, threshold: float = 0.7) -> bool:
        """Check if entity is ready for user engagement."""
        return self.readiness_score >= threshold

    def is_relevant(self, threshold: float = 0.5) -> bool:
        """Check if entity is relevant to user's goals."""
        return self.relevance_score >= threshold

    def is_high_priority(self, threshold: float = 0.7) -> bool:
        """Check if entity should be prioritized."""
        return self.priority_score >= threshold

    def has_blockers(self) -> bool:
        """Check if there are blocking reasons."""
        return len(self.blocking_reasons) > 0

    @property
    def entity_type(self) -> str:
        """
        Return entity type for categorization and dispatch.

        Subclasses override to return their specific type:
        - "task", "knowledge", "habit", "goal", "event"

        This enables unified dispatch patterns:
        - match entity.entity_type: case "task": ...
        - categorizers[entity.entity_type].append(entity)
        """
        return "entity"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "uid": self.uid,
            "title": self.title,
            "entity_type": self.entity_type,
            "readiness_score": self.readiness_score,
            "relevance_score": self.relevance_score,
            "priority_score": self.priority_score,
            "blocking_reasons": list(self.blocking_reasons),
            "unlocks": list(self.unlocks),
            "learning_gaps": list(self.learning_gaps),
            "is_ready": self.is_ready(),
            "is_relevant": self.is_relevant(),
            "is_high_priority": self.is_high_priority(),
        }


# =============================================================================
# DOMAIN-SPECIFIC CONTEXTUAL TYPES
# =============================================================================


@dataclass(frozen=True)
class ContextualTask(ContextualEntity):
    """
    Task enriched with user context.

    **Additional Context:**
    - can_start: All prerequisites met?
    - estimated_time_minutes: Time to complete
    - contributes_to_goals: Which active goals this advances
    - applies_knowledge: Knowledge units practiced by this task

    **Use Cases:**
    - get_actionable_tasks_for_user(): Tasks ready to start
    - get_learning_tasks_for_user(): Tasks that reinforce learning
    - get_goal_tasks_for_user(): Tasks advancing active goals
    """

    can_start: bool = False
    estimated_time_minutes: int = 0
    contributes_to_goals: tuple[str, ...] = field(default_factory=tuple)
    applies_knowledge: tuple[str, ...] = field(default_factory=tuple)

    # Task-specific context
    is_overdue: bool = False
    is_milestone: bool = False
    dependency_count: int = 0
    dependent_count: int = 0  # Tasks waiting on this one

    @property
    def entity_type(self) -> str:
        return "task"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "can_start": self.can_start,
                "estimated_time_minutes": self.estimated_time_minutes,
                "contributes_to_goals": list(self.contributes_to_goals),
                "applies_knowledge": list(self.applies_knowledge),
                "is_overdue": self.is_overdue,
                "is_milestone": self.is_milestone,
                "dependency_count": self.dependency_count,
                "dependent_count": self.dependent_count,
            }
        )
        return base


@dataclass(frozen=True)
class ContextualKnowledge(ContextualEntity):
    """
    Knowledge unit enriched with user context.

    **Additional Context:**
    - user_mastery: User's current mastery level (0.0-1.0)
    - prerequisites_met: All required knowledge mastered?
    - application_opportunities: Tasks/habits that apply this knowledge

    **Use Cases:**
    - get_ready_to_learn_for_user(): Knowledge with prerequisites met
    - get_learning_gaps_for_user(): Knowledge blocking progress
    - get_application_opportunities_for_user(): Where to practice
    """

    user_mastery: float = 0.0
    prerequisites_met: bool = False
    application_opportunities: tuple[str, ...] = field(default_factory=tuple)

    # Knowledge-specific context
    prerequisite_count: int = 0
    dependent_count: int = 0  # Knowledge that requires this
    substance_score: float = 0.0  # Real-world application level

    def mastery_category(self) -> str:
        """Categorize mastery level."""
        if self.user_mastery >= 0.9:
            return "expert"
        elif self.user_mastery >= 0.7:
            return "competent"
        elif self.user_mastery >= 0.4:
            return "developing"
        elif self.user_mastery > 0:
            return "beginner"
        else:
            return "unstarted"

    @property
    def entity_type(self) -> str:
        return "knowledge"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "user_mastery": self.user_mastery,
                "prerequisites_met": self.prerequisites_met,
                "application_opportunities": list(self.application_opportunities),
                "prerequisite_count": self.prerequisite_count,
                "dependent_count": self.dependent_count,
                "substance_score": self.substance_score,
                "mastery_category": self.mastery_category(),
            }
        )
        return base


@dataclass(frozen=True)
class ContextualGoal(ContextualEntity):
    """
    Goal enriched with user context.

    **Additional Context:**
    - current_progress: User's progress percentage (0.0-1.0)
    - contributing_tasks: Active tasks advancing this goal
    - contributing_habits: Habits reinforcing this goal
    - knowledge_gaps: Knowledge needed for goal completion

    **Use Cases:**
    - get_advancing_goals_for_user(): Goals with active momentum
    - get_stalled_goals_for_user(): Goals needing attention
    - get_achievable_goals_for_user(): Goals near completion
    """

    current_progress: float = 0.0
    contributing_tasks: tuple[str, ...] = field(default_factory=tuple)
    contributing_habits: tuple[str, ...] = field(default_factory=tuple)
    knowledge_required: tuple[str, ...] = field(default_factory=tuple)

    # Goal-specific context
    days_to_deadline: int | None = None
    is_at_risk: bool = False
    milestone_count: int = 0
    milestones_completed: int = 0

    def is_near_completion(self, threshold: float = 0.8) -> bool:
        """Check if goal is near completion."""
        return self.current_progress >= threshold

    def is_stalled(self, progress_threshold: float = 0.1) -> bool:
        """Check if goal has minimal progress."""
        return self.current_progress < progress_threshold

    @property
    def entity_type(self) -> str:
        return "goal"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "current_progress": self.current_progress,
                "contributing_tasks": list(self.contributing_tasks),
                "contributing_habits": list(self.contributing_habits),
                "knowledge_required": list(self.knowledge_required),
                "days_to_deadline": self.days_to_deadline,
                "is_at_risk": self.is_at_risk,
                "milestone_count": self.milestone_count,
                "milestones_completed": self.milestones_completed,
                "is_near_completion": self.is_near_completion(),
                "is_stalled": self.is_stalled(),
            }
        )
        return base


@dataclass(frozen=True)
class ContextualHabit(ContextualEntity):
    """
    Habit enriched with user context.

    **Additional Context:**
    - current_streak: User's current streak count
    - completion_rate: Recent completion percentage (0.0-1.0)
    - is_at_risk: Streak in danger of breaking?
    - supports_goals: Goals this habit contributes to

    **Use Cases:**
    - get_at_risk_habits_for_user(): Habits needing attention
    - get_keystone_habits_for_user(): High-impact habits
    - get_goal_habits_for_user(): Habits supporting active goals
    """

    current_streak: int = 0
    completion_rate: float = 0.0
    is_at_risk: bool = False
    supports_goals: tuple[str, ...] = field(default_factory=tuple)

    # Habit-specific context
    is_keystone: bool = False
    days_since_last: int = 0
    best_streak: int = 0
    applies_knowledge: tuple[str, ...] = field(default_factory=tuple)

    def streak_status(self) -> str:
        """Categorize streak health."""
        if self.is_at_risk:
            return "at_risk"
        elif self.current_streak >= 30:
            return "strong"
        elif self.current_streak >= 7:
            return "building"
        elif self.current_streak > 0:
            return "starting"
        else:
            return "broken"

    @property
    def entity_type(self) -> str:
        return "habit"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "current_streak": self.current_streak,
                "completion_rate": self.completion_rate,
                "is_at_risk": self.is_at_risk,
                "supports_goals": list(self.supports_goals),
                "is_keystone": self.is_keystone,
                "days_since_last": self.days_since_last,
                "best_streak": self.best_streak,
                "applies_knowledge": list(self.applies_knowledge),
                "streak_status": self.streak_status(),
            }
        )
        return base


@dataclass(frozen=True)
class ContextualEvent(ContextualEntity):
    """
    Event enriched with user context.

    **Additional Context:**
    - fits_schedule: Does event fit user's available time?
    - supports_habits: Habits this event reinforces
    - applies_knowledge: Knowledge practiced at event

    **Use Cases:**
    - get_upcoming_events_for_user(): Upcoming relevant events
    - get_habit_events_for_user(): Events reinforcing habits
    - get_learning_events_for_user(): Events for knowledge practice
    """

    fits_schedule: bool = True
    supports_habits: tuple[str, ...] = field(default_factory=tuple)
    applies_knowledge: tuple[str, ...] = field(default_factory=tuple)

    # Event-specific context
    days_until: int = 0
    duration_minutes: int = 0
    is_recurring: bool = False
    attendance_streak: int = 0

    @property
    def entity_type(self) -> str:
        return "event"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "fits_schedule": self.fits_schedule,
                "supports_habits": list(self.supports_habits),
                "applies_knowledge": list(self.applies_knowledge),
                "days_until": self.days_until,
                "duration_minutes": self.duration_minutes,
                "is_recurring": self.is_recurring,
                "attendance_streak": self.attendance_streak,
            }
        )
        return base


@dataclass(frozen=True)
class ContextualPrinciple(ContextualEntity):
    """
    Principle enriched with user context.

    **Additional Context:**
    - alignment_score: How aligned is user's behavior? (0.0-1.0)
    - guided_goals: Goals inspired by this principle
    - guided_choices: Decisions aligned with this principle

    **Use Cases:**
    - get_core_principles_for_user(): User's highest priority principles
    - get_misaligned_principles_for_user(): Principles needing attention
    - get_principles_needing_attention_for_user(): Principles that need review/practice
    - get_contextual_principles_for_user(): Principles relevant to today's activities

    **Planning Service Fields (January 2026):**
    - attention_score: How urgently does this principle need attention? (0.0-1.0)
    - alignment_trend: Is alignment improving, declining, or stable?
    - days_since_reflection: Days since last reflection on this principle
    - attention_reasons: Why does this principle need attention?
    - suggested_action: Actionable recommendation
    - connected_task_uids: Today's tasks connected to this principle
    - connected_event_uids: Today's events connected to this principle
    - connected_goal_uids: Active goals connected to this principle
    - practice_opportunity: Description of today's practice opportunity
    """

    # Note: ContextualPrinciple uses 'name' field, not 'title'
    # Override title to be optional since principles use 'name'
    name: str = ""

    alignment_score: float = 0.0
    guided_goals: tuple[str, ...] = field(default_factory=tuple)
    guided_choices: tuple[str, ...] = field(default_factory=tuple)

    # Principle-specific context
    is_core: bool = False
    grounding_knowledge: tuple[str, ...] = field(default_factory=tuple)

    # Planning service fields (January 2026)
    attention_score: float = 0.0
    relevance_score: float = 0.0
    alignment_trend: str = "stable"  # "improving", "declining", "stable"
    days_since_reflection: int = 0
    attention_reasons: tuple[str, ...] = field(default_factory=tuple)
    suggested_action: str = ""
    connected_task_uids: tuple[str, ...] = field(default_factory=tuple)
    connected_event_uids: tuple[str, ...] = field(default_factory=tuple)
    connected_goal_uids: tuple[str, ...] = field(default_factory=tuple)
    practice_opportunity: str = ""

    @property
    def entity_type(self) -> str:
        return "principle"

    def needs_attention(self, threshold: float = 0.5) -> bool:
        """Check if principle needs attention based on attention score."""
        return self.attention_score >= threshold

    def has_practice_opportunity(self) -> bool:
        """Check if there are connected activities for practice."""
        return bool(
            self.connected_task_uids or self.connected_event_uids or self.connected_goal_uids
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "name": self.name,
                "alignment_score": self.alignment_score,
                "guided_goals": list(self.guided_goals),
                "guided_choices": list(self.guided_choices),
                "is_core": self.is_core,
                "grounding_knowledge": list(self.grounding_knowledge),
                "attention_score": self.attention_score,
                "relevance_score": self.relevance_score,
                "alignment_trend": self.alignment_trend,
                "days_since_reflection": self.days_since_reflection,
                "attention_reasons": list(self.attention_reasons),
                "suggested_action": self.suggested_action,
                "connected_task_uids": list(self.connected_task_uids),
                "connected_event_uids": list(self.connected_event_uids),
                "connected_goal_uids": list(self.connected_goal_uids),
                "practice_opportunity": self.practice_opportunity,
                "needs_attention": self.needs_attention(),
                "has_practice_opportunity": self.has_practice_opportunity(),
            }
        )
        return base


@dataclass(frozen=True)
class ContextualChoice(ContextualEntity):
    """
    Choice/decision enriched with user context.

    **Additional Context:**
    - informed_by_knowledge: Knowledge informing this decision
    - aligned_principles: Principles this choice aligns with
    - resulting_goals: Goals that may emerge from this choice

    **Use Cases:**
    - get_pending_decisions_for_user(): Decisions awaiting resolution
    - get_principle_aligned_choices_for_user(): Choices matching values
    """

    informed_by_knowledge: tuple[str, ...] = field(default_factory=tuple)
    aligned_principles: tuple[str, ...] = field(default_factory=tuple)
    resulting_goals: tuple[str, ...] = field(default_factory=tuple)

    # Choice-specific context
    is_resolved: bool = False
    impact_score: float = 0.0

    @property
    def entity_type(self) -> str:
        return "choice"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "informed_by_knowledge": list(self.informed_by_knowledge),
                "aligned_principles": list(self.aligned_principles),
                "resulting_goals": list(self.resulting_goals),
                "is_resolved": self.is_resolved,
                "impact_score": self.impact_score,
            }
        )
        return base


# =============================================================================
# PRINCIPLE PLANNING TYPES (January 2026)
# =============================================================================


@dataclass(frozen=True)
class PracticeOpportunity:
    """
    An activity that could strengthen principle alignment.

    **Purpose:** Identifies specific activities (tasks, events, goals) that offer
    opportunities to practice and reinforce a particular principle.

    **Use Cases:**
    - get_principle_practice_opportunities_for_user(): Find today's practice opportunities
    - Daily planning: Show how principles connect to scheduled activities
    - Reflection prompts: Suggest what to reflect on after completing activities

    **Fields:**
    - principle_uid/name: The principle this opportunity strengthens
    - activity_type: Type of activity ("task", "event", "goal", "habit")
    - activity_uid/title: The specific activity
    - opportunity_type: How this activity relates to the principle
    - guidance: Actionable suggestion for the user

    Version: 1.0.0
    Date: January 2026
    """

    principle_uid: str
    principle_name: str
    activity_type: str  # "task", "event", "goal", "habit"
    activity_uid: str
    activity_title: str
    opportunity_type: str  # "direct_alignment", "practice_context", "reflection_trigger"
    guidance: str

    def is_today(self) -> bool:
        """Check if this is a today-relevant opportunity."""
        return self.activity_type in ("task", "event")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "principle_uid": self.principle_uid,
            "principle_name": self.principle_name,
            "activity_type": self.activity_type,
            "activity_uid": self.activity_uid,
            "activity_title": self.activity_title,
            "opportunity_type": self.opportunity_type,
            "guidance": self.guidance,
            "is_today": self.is_today(),
        }


# =============================================================================
# AGGREGATE CONTEXTUAL TYPES
# =============================================================================


@dataclass(frozen=True)
class ContextualDependencies:
    """
    Complete dependency analysis enriched with user context.

    **Purpose:** Provide actionable dependency information for an entity,
    categorized by user's readiness to engage.

    **Categories:**
    - ready_dependencies: User can engage with these now
    - blocked_dependencies: User needs to complete prerequisites first

    **Insights:**
    - recommended_next_action: Most impactful action to take
    - learning_path_suggestion: Knowledge to acquire for unblocking
    """

    entity_uid: str
    entity_type: str  # "Task", "Goal", "Habit", etc.

    # Categorized by readiness
    ready_dependencies: tuple[ContextualEntity, ...] = field(default_factory=tuple)
    blocked_dependencies: tuple[ContextualEntity, ...] = field(default_factory=tuple)

    # Categorized by type
    knowledge_requirements: tuple[ContextualKnowledge, ...] = field(default_factory=tuple)
    task_requirements: tuple[ContextualTask, ...] = field(default_factory=tuple)
    habit_requirements: tuple[ContextualHabit, ...] = field(default_factory=tuple)

    # Aggregated insights
    total_blocking_items: int = 0
    estimated_unblock_time_minutes: int = 0
    highest_priority_blocker: str | None = None

    # User-specific recommendations
    recommended_next_action: str = ""
    learning_path_suggestion: tuple[str, ...] = field(default_factory=tuple)

    # Metadata
    analyzed_at: datetime = field(default_factory=datetime.now)

    def is_fully_ready(self) -> bool:
        """Check if all dependencies are met."""
        return self.total_blocking_items == 0

    def get_critical_blockers(self, limit: int = 3) -> list[ContextualEntity]:
        """Get highest priority blockers."""

        def get_relevance_score(entity: ContextualEntity) -> float:
            return entity.relevance_score

        sorted_blockers = sorted(self.blocked_dependencies, key=get_relevance_score, reverse=True)
        return list(sorted_blockers[:limit])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_uid": self.entity_uid,
            "entity_type": self.entity_type,
            "ready_dependencies": [d.to_dict() for d in self.ready_dependencies],
            "blocked_dependencies": [d.to_dict() for d in self.blocked_dependencies],
            "knowledge_requirements": [k.to_dict() for k in self.knowledge_requirements],
            "task_requirements": [t.to_dict() for t in self.task_requirements],
            "habit_requirements": [h.to_dict() for h in self.habit_requirements],
            "total_blocking_items": self.total_blocking_items,
            "estimated_unblock_time_minutes": self.estimated_unblock_time_minutes,
            "highest_priority_blocker": self.highest_priority_blocker,
            "recommended_next_action": self.recommended_next_action,
            "learning_path_suggestion": list(self.learning_path_suggestion),
            "is_fully_ready": self.is_fully_ready(),
        }


@dataclass(frozen=True)
class DailyWorkPlan:
    """
    Comprehensive plan for what user should work on today.

    **THE FLAGSHIP OUTPUT** of UserContextIntelligence.get_ready_to_work_on_today()

    **Respects:**
    - User's available time (capacity)
    - User's energy level (cognitive load)
    - User's current workload (not overloading)
    - User's preferences (scheduling, learning style)

    **Contains:**
    - Prioritized lists of UIDs for each domain
    - Estimated time and capacity utilization
    - Rationale explaining the plan
    """

    user_uid: str

    # Prioritized entity UIDs for each domain
    learning: tuple[str, ...] = field(default_factory=tuple)  # KU UIDs to learn
    tasks: tuple[str, ...] = field(default_factory=tuple)  # Task UIDs to complete
    habits: tuple[str, ...] = field(default_factory=tuple)  # Habit UIDs to maintain
    events: tuple[str, ...] = field(default_factory=tuple)  # Event UIDs to attend
    goals: tuple[str, ...] = field(default_factory=tuple)  # Goal UIDs to advance

    # Capacity metrics
    estimated_time_minutes: int = 0
    available_time_minutes: int = 60
    fits_capacity: bool = True
    workload_utilization: float = 0.0  # 0.0-1.0

    # Plan metadata
    rationale: str = ""
    priorities: tuple[str, ...] = field(default_factory=tuple)  # Ordered priority list
    generated_at: datetime = field(default_factory=datetime.now)

    # Insights
    at_risk_items: tuple[str, ...] = field(default_factory=tuple)  # Items needing urgent attention
    learning_opportunities: tuple[str, ...] = field(default_factory=tuple)
    goal_contributions: dict[str, list[str]] = field(
        default_factory=dict
    )  # goal_uid -> [contributing_item_uids]

    def total_items(self) -> int:
        """Get total number of items in plan."""
        return len(self.learning) + len(self.tasks) + len(self.habits) + len(self.events)

    def is_overloaded(self) -> bool:
        """Check if plan exceeds capacity."""
        return not self.fits_capacity

    def utilization_status(self) -> str:
        """Categorize workload utilization."""
        if self.workload_utilization >= 0.9:
            return "full"
        elif self.workload_utilization >= 0.7:
            return "heavy"
        elif self.workload_utilization >= 0.4:
            return "moderate"
        else:
            return "light"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "user_uid": self.user_uid,
            "learning": list(self.learning),
            "tasks": list(self.tasks),
            "habits": list(self.habits),
            "events": list(self.events),
            "goals": list(self.goals),
            "estimated_time_minutes": self.estimated_time_minutes,
            "available_time_minutes": self.available_time_minutes,
            "fits_capacity": self.fits_capacity,
            "workload_utilization": self.workload_utilization,
            "rationale": self.rationale,
            "priorities": list(self.priorities),
            "at_risk_items": list(self.at_risk_items),
            "learning_opportunities": list(self.learning_opportunities),
            "goal_contributions": self.goal_contributions,
            "total_items": self.total_items(),
            "utilization_status": self.utilization_status(),
        }


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================


def create_contextual_task(
    uid: str,
    title: str,
    readiness: float = 0.0,
    relevance: float = 0.0,
    can_start: bool = False,
    blocking_reasons: list[str] | None = None,
    contributes_to_goals: list[str] | None = None,
    applies_knowledge: list[str] | None = None,
    **kwargs: Any,
) -> ContextualTask:
    """Factory function to create ContextualTask with sensible defaults."""
    priority = (readiness * 0.4) + (relevance * 0.4) + (0.2 if can_start else 0.0)

    return ContextualTask(
        uid=uid,
        title=title,
        readiness_score=readiness,
        relevance_score=relevance,
        priority_score=priority,
        can_start=can_start,
        blocking_reasons=tuple(blocking_reasons or []),
        contributes_to_goals=tuple(contributes_to_goals or []),
        applies_knowledge=tuple(applies_knowledge or []),
        **kwargs,
    )


def create_contextual_knowledge(
    uid: str,
    title: str,
    user_mastery: float = 0.0,
    prerequisites_met: bool = False,
    blocking_reasons: list[str] | None = None,
    application_opportunities: list[str] | None = None,
    **kwargs: Any,
) -> ContextualKnowledge:
    """Factory function to create ContextualKnowledge with sensible defaults."""
    # Readiness based on prerequisites
    readiness = 1.0 if prerequisites_met else 0.3

    # Relevance inversely related to mastery (learn what you don't know)
    relevance = 1.0 - user_mastery if user_mastery < 0.9 else 0.1

    priority = (readiness * 0.5) + (relevance * 0.5)

    return ContextualKnowledge(
        uid=uid,
        title=title,
        readiness_score=readiness,
        relevance_score=relevance,
        priority_score=priority,
        user_mastery=user_mastery,
        prerequisites_met=prerequisites_met,
        blocking_reasons=tuple(blocking_reasons or []),
        application_opportunities=tuple(application_opportunities or []),
        **kwargs,
    )


def create_contextual_habit(
    uid: str,
    title: str,
    current_streak: int = 0,
    completion_rate: float = 0.0,
    is_at_risk: bool = False,
    supports_goals: list[str] | None = None,
    **kwargs: Any,
) -> ContextualHabit:
    """Factory function to create ContextualHabit with sensible defaults."""
    # At-risk habits are high priority
    urgency = 1.0 if is_at_risk else 0.3

    # Long streaks are high relevance (don't want to break them)
    streak_factor = min(1.0, current_streak / 30)

    readiness = 1.0  # Habits are always "ready" (daily actions)
    relevance = (streak_factor * 0.5) + (urgency * 0.5)
    priority = (readiness * 0.3) + (relevance * 0.4) + (urgency * 0.3)

    return ContextualHabit(
        uid=uid,
        title=title,
        readiness_score=readiness,
        relevance_score=relevance,
        priority_score=priority,
        current_streak=current_streak,
        completion_rate=completion_rate,
        is_at_risk=is_at_risk,
        supports_goals=tuple(supports_goals or []),
        **kwargs,
    )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "ContextualChoice",
    # Aggregate types
    "ContextualDependencies",
    # Base types
    "ContextualEntity",
    "ContextualEvent",
    "ContextualGoal",
    "ContextualHabit",
    "ContextualKnowledge",
    "ContextualPrinciple",
    # Domain types
    "ContextualTask",
    "DailyWorkPlan",
    # Principle planning types (January 2026)
    "PracticeOpportunity",
    "create_contextual_habit",
    "create_contextual_knowledge",
    # Factory functions
    "create_contextual_task",
]
