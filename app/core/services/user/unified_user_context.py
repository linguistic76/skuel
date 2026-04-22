"""
Unified User Context - The Master Integration Point
====================================================

This is THE way to understand a user's complete state across all domains.
The UserContext wraps around everything, providing rich awareness
of tasks, events, goals, habits, knowledge, principles, and progress.

This context is:
- Cached and maintained for performance (via UserContextCache)
- Full depth by default (no complexity of multiple depths)
- READ-ONLY aggregate view (mutations handled by domain services)
- The primary integration point for all intelligence services

Architecture:
- User exists as both a domain entity AND a context provider
- This file handles the context provider role (read model)
- All services should use this context for user state understanding
- Mutations go through domain services, then cache is invalidated

**Canonical Location (ADR-030):**
This is THE single source for UserContext. The models layer re-exports from here.
See: `/docs/decisions/ADR-030-usercontext-file-consolidation.md`

UserContext Layers (Mental Map)
-------------------------------
Navigation guide for this ~240-field read model:

1. **Identity & Session** (lines ~55-72)
   - user_uid, username, email, display_name
   - session_id, session_start, last_activity
   - context_version, cache_ttl, is_rich_context

2. **Activity Domain Awareness** (lines ~74-240)
   - Tasks: active, priorities, blocked, today/week scheduling
   - Events: upcoming, recurring, attendance, streaks
   - Goals: active, progress, deadlines, categorization
   - Habits: active, streaks, completion rates, keystone

3. **Curriculum Domain Awareness** (lines ~145-175)
   - Learning paths, enrolled/completed paths
   - Life path, alignment score, milestones
   - Knowledge mastery, prerequisites, recommendations

4. **Graph-Sourced Metadata** (lines ~177-207)
   - Relationship data extracted from Neo4j edges
   - Task dependencies/blockers, goal-knowledge mappings
   - Habit reinforcement patterns

5. **Principles & Choices** (lines ~209-240)
   - Core principles, priorities, conflicts
   - Principle-choice integration tracking
   - Pending/resolved choices

5.5. **ZPD Awareness** (after submissions, before progress)
   - zpd_assessment: ZPDAssessment — capstone of build_rich()
   - Computed last, reads all prior fields
   - None in standard build() or INTELLIGENCE_TIER=core

6. **Progress & Capacity** (lines ~242-301)
   - Overall progress, domain progress
   - Velocity, acceleration, consistency
   - Workload score, capacity by domain

7. **Rich Entity Data** (lines ~303-420) - Optional
   - Full entity objects with graph neighborhoods
   - Only populated via build_rich() path

8. **Query Helpers** (lines ~480-730)
   - Read-only, deterministic query methods
   - Facet evaluation and recommendations

9. **Derived/Cache-Local Mutations** (lines ~737-786)
   - Facet tracking (acceptable mutations)
   - See MUTATION GOVERNANCE in class docstring

10. **Convenience Properties** (lines ~976-1021)
    - Derived properties with multiple call sites
    - Per "One Path Forward": properties with 0-1 usages removed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from operator import itemgetter
from typing import TYPE_CHECKING, Any, ClassVar, TypeGuard

from core.models.enums import (
    Domain,
    EnergyLevel,
    GuidanceMode,
    LearningLevel,
    Personality,
    ResponseTone,
    TimeOfDay,
)
from core.models.enums.user_enums import UserRole
from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.models.zpd.zpd_assessment import ZPDAssessment
    from core.ports.query_types import (
        CrossDomainInsightsData,
        CurrentPathStepItem,
        FacetInteractionItem,
        GroupSummary,
        PendingRevisedExerciseItem,
        RichEntityItem,
        RichKnowledgeUnitItem,
        RichLearningPathItem,
        RichMOCItem,
        RichPathStepItem,
        UnsubmittedExerciseItem,
    )


@dataclass
class UserContext:
    """
    The master context that provides complete awareness of a user's state
    across all domains. This is THE integration point for understanding users.

    This is a READ-ONLY aggregate - mutations happen via domain services.
    After mutations, the cache is invalidated and context is rebuilt.

    MUTATION GOVERNANCE
    -------------------
    While UserContext is declared READ-ONLY, some controlled mutations exist.

    **ALLOWED mutations** (cache-local, non-authoritative):
    - Derived/cached values: life_path_alignment_score, current_workload_score
    - Facet tracking: facet_affinities, facet_profile, facet_interaction_history
    - Session state: is_rich_context

    **FORBIDDEN mutations** (domain-authoritative state):
    - Task/Goal/Habit/Event UIDs or progress
    - Knowledge mastery, prerequisites
    - Any field populated by UserContextBuilder

    Rule: If a change should persist beyond the current context lifetime,
    it MUST go through the domain service, not be mutated here.

    SERIALIZATION POLICY
    --------------------
    Fields using Domain enum as dict keys (e.g., learning_velocity_by_domain)
    are for in-memory use only. When serializing to JSON or external storage,
    convert enum keys to their string values: {Domain.TECH.value: 0.8}
    """

    # =========================================================================
    # CORE IDENTITY
    # =========================================================================
    user_uid: UserUID
    username: str = ""  # Optional - populated by UserContextBuilder when available
    email: str = ""
    display_name: str = ""
    user_role: UserRole = UserRole.REGISTERED

    # Session tracking
    session_id: str | None = None
    session_start: datetime | None = None
    last_activity: datetime | None = None

    # Context metadata
    context_version: str = "3.0"  # Bumped to 3.0 for services layer move
    last_refresh: datetime = field(default_factory=datetime.now)
    cache_ttl_seconds: int = 300  # 5 minutes default

    # Context depth marker (January 2026)
    # Standard (build) = UIDs only, Rich (build_rich) = UIDs + full entities + graph neighborhoods
    is_rich_context: bool = False  # Set to True by build_rich() path

    # Rich-only derived fields. None at standard depth — populated only by
    # build_rich() via populate_derived_fields() / populate_principle_choice_integration().
    # Reading these at standard depth should raise RichContextRequiredError; the
    # public accessor methods enforce that. The canonical set lives on
    # `RichUserContext.RICH_ONLY_FIELDS`.

    # =========================================================================
    # TASK AWARENESS - Complete task state understanding
    # =========================================================================
    active_task_uids: list[str] = field(default_factory=list)
    current_task_focus: str | None = None
    task_priorities: dict[str, float] = field(default_factory=dict)  # uid -> priority (0-1)
    completed_task_uids: set[str] = field(default_factory=set)
    blocked_task_uids: set[str] | None = field(
        default=None
    )  # RICH-ONLY (see RichUserContext.RICH_ONLY_FIELDS)
    task_progress: dict[str, float] = field(default_factory=dict)  # uid -> completion %

    # Task-Goal relationships (RICH-ONLY — see RichUserContext.RICH_ONLY_FIELDS)
    tasks_by_goal: dict[str, list[str]] | None = field(default=None)  # goal_uid -> task_uids
    milestone_tasks: list[str] = field(default_factory=list)

    # Task scheduling
    overdue_task_uids: list[str] = field(default_factory=list)
    today_task_uids: list[str] = field(default_factory=list)
    this_week_task_uids: list[str] = field(default_factory=list)

    # =========================================================================
    # EVENT AWARENESS - Calendar and scheduling state
    # =========================================================================
    upcoming_event_uids: list[str] = field(default_factory=list)
    recurring_event_uids: list[str] = field(default_factory=list)
    today_event_uids: list[str] = field(default_factory=list)

    # Event participation
    event_attendance: dict[str, int] = field(default_factory=dict)  # uid -> quality (1-5)
    missed_event_uids: set[str] = field(default_factory=set)
    event_streaks: dict[str, int] = field(default_factory=dict)  # recurring_uid -> streak

    # Event scheduling
    scheduled_event_uids: list[str] = field(default_factory=list)  # All scheduled (future) events

    # Event-Habit relationships
    events_by_habit: dict[str, list[str]] = field(default_factory=dict)  # habit_uid -> event_uids

    # =========================================================================
    # GOAL AWARENESS - Outcomes and milestones
    # =========================================================================
    active_goal_uids: list[str] = field(default_factory=list)
    primary_goal_focus: str | None = None
    goal_progress: dict[str, float] = field(default_factory=dict)  # uid -> progress %
    goal_milestones_completed: dict[str, list[str]] = field(default_factory=dict)
    goal_deadlines: dict[str, date] = field(default_factory=dict)
    completed_goal_uids: set[str] = field(default_factory=set)

    # Goal categorization
    learning_goals: list[str] = field(default_factory=list)
    outcome_goals: list[str] = field(default_factory=list)
    process_goals: list[str] = field(default_factory=list)

    # Goal risk tracking
    at_risk_goals: list[str] = field(default_factory=list)  # Goals needing attention

    # =========================================================================
    # HABIT AWARENESS - Behavioral patterns and streaks
    # =========================================================================
    active_habit_uids: list[str] = field(default_factory=list)
    habit_streaks: dict[str, int] = field(default_factory=dict)  # uid -> current streak
    habit_completion_rates: dict[str, float] = field(default_factory=dict)  # uid -> rate
    at_risk_habits: list[str] | None = field(
        default=None
    )  # RICH-ONLY (see RichUserContext.RICH_ONLY_FIELDS)

    # Habit categorization
    keystone_habits: list[str] = field(default_factory=list)
    daily_habits: list[str] = field(default_factory=list)
    weekly_habits: list[str] = field(default_factory=list)

    # Habit-Goal relationships (RICH-ONLY — see RichUserContext.RICH_ONLY_FIELDS)
    habits_by_goal: dict[str, list[str]] | None = field(default=None)  # goal_uid -> habit_uids

    # =========================================================================
    # KNOWLEDGE & LEARNING PATH AWARENESS
    # =========================================================================
    current_learning_path_uid: str | None = None
    enrolled_path_uids: list[str] = field(default_factory=list)
    completed_path_uids: set[str] = field(default_factory=set)

    # Life Path - THE ONE ultimate learning path (converges all learning)
    life_path_uid: str | None = None  # The user's life path (ultimate convergence)
    life_path_milestones: list[str] = field(default_factory=list)  # Major life milestones
    life_path_alignment_score: float = 0.0  # 0.0-1.0: How aligned are activities?

    # Knowledge mastery
    knowledge_mastery: dict[str, float] = field(default_factory=dict)  # uid -> mastery %
    mastered_knowledge_uids: set[str] = field(default_factory=set)
    in_progress_knowledge_uids: set[str] = field(default_factory=set)
    current_ps_uids: set[str] = field(default_factory=set)  # Path steps user is studying
    current_path_steps: list[CurrentPathStepItem] = field(
        default_factory=list
    )  # {uid, title} for path steps with IN_PROGRESS relationship

    # KU interaction tracking (Phase B)
    ku_view_counts: dict[str, int] = field(default_factory=dict)  # uid -> total view count
    ku_time_spent_seconds: dict[str, int] = field(default_factory=dict)  # uid -> cumulative seconds
    recently_viewed_ku_uids: list[str] = field(default_factory=list)  # Last 10 viewed KUs (ordered)
    ku_marked_as_read_uids: set[str] = field(default_factory=set)  # KUs marked as read
    ku_bookmarked_uids: set[str] = field(default_factory=set)  # Bookmarked KUs

    # Learning recommendations
    next_recommended_knowledge: list[str] = field(default_factory=list)
    prerequisites_completed: set[str] = field(default_factory=set)
    prerequisites_needed: dict[str, list[str]] = field(default_factory=dict)

    # Learning path tracking
    learning_path_step_uids: list[str] = field(default_factory=list)  # Active path step UIDs
    recently_mastered_uids: set[str] = field(
        default_factory=set
    )  # Recently mastered KU UIDs (for momentum)

    # Learning velocity
    learning_velocity_by_domain: dict[Domain, float] = field(default_factory=dict)
    estimated_time_to_mastery: dict[str, int] = field(default_factory=dict)  # uid -> hours

    # Learning focus tracking (aligns with other domain focus fields)
    current_learning_focus: str | None = (
        None  # Current learning/curriculum focus (KU, PS, or LP UID)
    )

    # =========================================================================
    # GRAPH-SOURCED RELATIONSHIP METADATA - Data FROM graph edges
    # =========================================================================
    # ** NEW (November 15, 2025): Graph-sourced context enhancement **
    # These fields are extracted FROM relationship properties and graph patterns,
    # not just node properties. This provides richer context with relationship
    # semantics (confidence, timestamps, etc.) directly from Neo4j edges.

    # Knowledge mastery metadata (from [:MASTERED] relationships)
    mastery_timestamps: dict[str, datetime] = field(default_factory=dict)  # uid -> when mastered
    mastery_confidence_scores: dict[str, float] = field(default_factory=dict)  # uid -> confidence
    ready_to_learn_uids: set[str] = field(default_factory=set)  # Computed from graph pattern
    prerequisite_counts: dict[str, int] = field(default_factory=dict)  # uid -> prereq count

    # Task relationship metadata (from [:DEPENDS_ON], [:BLOCKS] relationships)
    task_dependencies: dict[str, list[str]] = field(default_factory=dict)  # task -> dependencies
    task_blockers: dict[str, list[str]] = field(default_factory=dict)  # task -> blockers
    task_knowledge_applied: dict[str, list[str]] = field(default_factory=dict)  # task -> ku_uids
    task_goal_associations: dict[str, str] = field(default_factory=dict)  # task -> goal_uid

    # Goal progress metadata (from [:REQUIRES_KNOWLEDGE], [:MASTERED] relationships)
    goal_knowledge_required: dict[str, list[str]] = field(default_factory=dict)  # goal -> ku_uids
    goal_knowledge_mastered: dict[str, list[str]] = field(default_factory=dict)  # goal -> ku_uids
    goal_completion_from_graph: dict[str, float] = field(
        default_factory=dict
    )  # Computed from graph
    goal_supporting_tasks: dict[str, list[str]] = field(default_factory=dict)  # goal -> task_uids

    # Habit reinforcement metadata (from [:APPLIES_KNOWLEDGE], [:REQUIRES_HABIT] relationships)
    habit_knowledge_applied: dict[str, list[str]] = field(default_factory=dict)  # habit -> ku_uids
    habit_prerequisites: dict[str, list[str]] = field(default_factory=dict)  # habit -> habit_uids

    # Event knowledge metadata (from [:APPLIES_KNOWLEDGE] relationships)
    event_knowledge_applied: dict[str, list[str]] = field(default_factory=dict)  # event -> ku_uids

    # Choice knowledge metadata (from [:INFORMS_CHOICE] relationships)
    choice_knowledge_informed: dict[str, list[str]] = field(
        default_factory=dict
    )  # choice -> ku_uids

    # Principle knowledge metadata (from [:GROUNDED_IN_KNOWLEDGE] relationships)
    principle_knowledge_grounded: dict[str, list[str]] = field(
        default_factory=dict
    )  # principle -> ku_uids

    # =========================================================================
    # PRINCIPLE AWARENESS - Values and alignment
    # =========================================================================
    core_principle_uids: list[str] = field(default_factory=list)
    current_principle_focus: str | None = None
    principle_priorities: dict[str, float] = field(default_factory=dict)  # uid -> importance
    principle_conflicts: list[tuple[str, str]] = field(default_factory=list)

    # Principle alignment scores
    principle_alignment_by_domain: dict[Domain, float] = field(default_factory=dict)
    decisions_aligned_with_principles: int = 0
    decisions_against_principles: int = 0

    # Principle-choice integration tracking (January 2026)
    # RICH-ONLY — see RichUserContext.RICH_ONLY_FIELDS
    principle_guided_choice_counts: dict[str, int] | None = field(
        default=None
    )  # principle_uid -> count of guided choices
    principle_choice_satisfaction_avg: dict[str, float] = field(
        default_factory=dict
    )  # principle_uid -> avg satisfaction (0.0-1.0)
    # RICH-ONLY — see RichUserContext.RICH_ONLY_FIELDS. None at standard depth distinguishes
    # "not computed" from a legitimate rich-depth 0.0 ("no alignment").
    principle_integration_score: float | None = field(default=None)  # 0.0-1.0 at rich depth
    # RICH-ONLY — see RichUserContext.RICH_ONLY_FIELDS
    recent_principle_aligned_choices: list[str] | None = field(
        default=None
    )  # Last 10 principle-aligned choice UIDs

    # =========================================================================
    # CHOICE AWARENESS - Decisions pending and resolved
    # =========================================================================
    pending_choice_uids: list[str] = field(default_factory=list)  # Choices awaiting decision
    resolved_choice_uids: set[str] = field(default_factory=set)  # Recently resolved choices
    choice_outcomes: dict[str, str] = field(default_factory=dict)  # choice_uid -> outcome

    # =========================================================================
    # FEEDBACK DOMAIN - Latest activity report reference
    # =========================================================================
    # Pointer to the most recent ActivityReport for this user.
    # Populated by build_rich_user_context() only — None in standard build().
    # Intelligence services use these fields to reason about recent patterns
    # without an extra round-trip.
    latest_activity_report_uid: str | None = None
    latest_activity_report_period: str | None = None  # "7d" | "14d" | "30d" | "90d"
    latest_activity_report_generated_at: datetime | None = None  # period_end datetime
    latest_activity_report_content: str | None = None  # processed_content for inline reasoning
    latest_activity_report_user_annotation: str | None = (
        None  # Owner's self-reflection (additive mode only)
    )

    # =========================================================================
    # ZPD AWARENESS — Zone of Proximal Development (capstone)
    # =========================================================================
    # Computed as final step of build_rich() — reads all prior fields.
    # None in standard build() path. None when INTELLIGENCE_TIER=core.
    # See: core/models/zpd/zpd_assessment.py, core/services/zpd/zpd_service.py
    zpd_assessment: ZPDAssessment | None = None

    # =========================================================================
    # SUBMISSION & FEEDBACK AWARENESS - Learning loop engagement tracking
    # =========================================================================
    total_submission_count: int = 0
    total_journal_count: int = 0
    submissions_in_window: int = 0
    last_submission_date: datetime | None = None
    feedback_received_count: int = 0
    feedback_in_window: int = 0
    pending_feedback_count: int = 0
    assigned_exercise_count: int = 0
    completed_exercise_count: int = 0
    unsubmitted_exercises: list[UnsubmittedExerciseItem] = field(
        default_factory=list
    )  # Up to 5: {uid, title, due_date}, due_date ASC
    pending_revised_exercises: list[PendingRevisedExerciseItem] = field(
        default_factory=list
    )  # Up to 5: {uid, title, instructions, revision_number, ...}

    # =========================================================================
    # PROGRESS AWARENESS - Unified progress tracking
    # =========================================================================
    overall_progress: float = 0.0
    domain_progress: dict[Domain, float] = field(default_factory=dict)

    # Progress velocity (rate of improvement)
    velocity_by_domain: dict[Domain, float] = field(default_factory=dict)
    acceleration_by_domain: dict[Domain, float] = field(
        default_factory=dict
    )  # Is velocity increasing?

    # Consistency metrics
    overall_consistency_score: float = 0.0
    consistency_by_domain: dict[Domain, float] = field(default_factory=dict)

    # Time investment
    time_invested_hours_by_domain: dict[Domain, float] = field(default_factory=dict)
    time_invested_this_week: float = 0.0
    time_invested_this_month: float = 0.0

    # =========================================================================
    # FACET AWARENESS - Tags, domains, and content preferences
    # =========================================================================
    facet_profile: dict[str, list[str]] = field(default_factory=dict)
    # Example: {"tags": ["python", "testing"], "domains": ["TECH"], "difficulty": ["intermediate"]}

    facet_affinities: dict[str, float] = field(default_factory=dict)
    # Example: {"python": 0.8, "testing": 0.6, "TECH": 0.9}

    facet_interaction_history: list[FacetInteractionItem] = field(default_factory=list)
    # Track recent facet interactions for learning preferences

    content_type_preferences: dict[str, float] = field(default_factory=dict)
    # Example: {"tutorial": 0.7, "reference": 0.5, "exercise": 0.8}

    # =========================================================================
    # USER PREFERENCES & STATE
    # =========================================================================
    learning_level: LearningLevel = LearningLevel.INTERMEDIATE
    current_energy_level: EnergyLevel | None = None
    preferred_time: TimeOfDay = TimeOfDay.ANYTIME
    available_minutes_daily: int = 60

    # Interaction preferences
    preferred_personality: Personality = Personality.KNOWLEDGEABLE_FRIEND
    preferred_tone: ResponseTone = ResponseTone.FRIENDLY
    preferred_guidance: GuidanceMode = GuidanceMode.DIRECT

    # Current state
    is_overwhelmed: bool = False  # Too many active items
    is_blocked: bool = False  # Blocked by prerequisites
    needs_review: bool = False  # Has items needing review

    # =========================================================================
    # WORKLOAD & CAPACITY
    # =========================================================================
    current_workload_score: float = 0.0  # 0-1, where 1 is at capacity
    recommended_daily_tasks: int = 3
    recommended_daily_events: int = 2
    capacity_by_domain: dict[Domain, float] = field(default_factory=dict)

    # =========================================================================
    # GROUP AWARENESS — Teacher-student group membership
    # =========================================================================
    # Groups the user belongs to as a member (student role).
    # Populated from (user)-[:MEMBER_OF]->(g:Group).
    user_groups: list[GroupSummary] = field(default_factory=list)

    # Groups the user owns as a teacher. Populated from (user)-[:OWNS]->(g:Group).
    # Empty for non-teachers.
    teacher_groups: list[GroupSummary] = field(default_factory=list)

    # Curriculum shared with this user's groups via SHARED_WITH_GROUP.
    # Populated by the MEGA-QUERY from
    # (user)-[:MEMBER_OF]->(g)<-[:SHARED_WITH_GROUP]-(entity:Entity)
    # filtered by entity_type.
    group_assigned_exercise_uids: list[str] = field(default_factory=list)
    group_assigned_path_step_uids: list[str] = field(default_factory=list)
    group_assigned_learning_path_uids: list[str] = field(default_factory=list)

    # =========================================================================
    # RICH GRAPH CONTEXT (Optional - November 22, 2025)
    # =========================================================================
    # These fields contain FULL entity details WITH graph neighborhoods.
    # Only populated via UserService.get_rich_unified_context() (expensive MEGA-QUERY).
    #
    # Philosophy: "50-100 queries → 1 query"
    # - Standard context: UIDs only (lightweight)
    # - Rich context: Full entities + relationships (comprehensive)
    #
    # Use Cases:
    # - Dashboard views (need full entity data)
    # - Cross-domain intelligence (need relationship semantics)
    # - Deep analytics (need graph patterns)
    #
    # Performance:
    # - MEGA-QUERY fetches everything in ONE database round-trip
    # - 3-4x faster than sequential get_with_context() calls
    # - Cached for 5 minutes (same as standard context)

    # ACTIVITY DOMAINS — unified rich data (all 6 domains, one shape)
    # Populated by build_rich(). Status included on every entity — consumers filter.
    # Active entities always present. Completed entities present if touched within window.
    # Curriculum domains (KU, LP, PS) remain in their own fields below.
    #
    # Keys: "tasks", "goals", "habits", "events", "choices", "principles"
    # Values: [{"entity": {all entity properties}, "graph_context": {...}}, ...]
    entities_rich: dict[str, list[RichEntityItem]] = field(default_factory=dict)

    # Rich knowledge data (full KU objects with graph neighborhoods)
    knowledge_units_rich: dict[str, RichKnowledgeUnitItem] = field(default_factory=dict)
    # Key: knowledge_uid
    # Value: {ku: Full KU properties, graph_context: {prerequisites, dependents, related, mastery, etc.}}

    # Rich learning path data (full Lp objects with graph neighborhoods)
    enrolled_paths_rich: list[RichLearningPathItem] = field(default_factory=list)
    # Each dict contains:
    # - path: Full LearningPath entity properties
    # - graph_context: {steps, prerequisite_knowledge, aligned_goals, embodied_principles, milestone_events, progress, etc.}

    # Rich path step data (full Ls objects with graph neighborhoods)
    active_path_steps_rich: list[RichPathStepItem] = field(default_factory=list)
    # Each dict contains:
    # - step: Full PathStep entity properties
    # - graph_context: {knowledge, prerequisites, practice_opportunities, guiding_principles, learning_path, etc.}

    # =========================================================================
    # MOC (MAP OF CONTENT) AWARENESS - Non-linear knowledge navigation
    # =========================================================================
    # MOCs provide non-linear organization complementing linear Learning Paths.
    # They serve as navigation hubs, topic overviews, and cross-domain bridges.
    #
    # Design Philosophy:
    # - LP is linear: "Step 1 → Step 2 → Step 3"
    # - MOC is non-linear: "Browse everything about Python by topic"
    # - MOC and LP are complementary, not competing

    # Active MOC UIDs the user has created or enrolled in
    active_moc_uids: list[str] = field(default_factory=list)

    # Current MOC the user is focused on (for navigation context)
    current_moc_focus: str | None = None

    # MOC usage tracking (for discovery and recommendations)
    moc_view_counts: dict[str, int] = field(default_factory=dict)  # moc_uid -> views
    recently_viewed_moc_uids: list[str] = field(default_factory=list)  # Last 10 viewed

    # MOC template enrollment (templates user has instantiated)
    enrolled_template_moc_uids: list[str] = field(default_factory=list)

    # MOC-Knowledge relationships (which KUs are organized in which MOCs)
    mocs_by_knowledge: dict[str, list[str]] = field(default_factory=dict)  # ku_uid -> moc_uids
    knowledge_by_moc: dict[str, list[str]] = field(default_factory=dict)  # moc_uid -> ku_uids

    # MOC-Learning Path alignment (which MOCs support which LPs)
    mocs_by_learning_path: dict[str, list[str]] = field(default_factory=dict)  # lp_uid -> moc_uids

    # Rich MOC data (full KU-based MOC objects with graph neighborhoods) - Optional
    active_mocs_rich: list[RichMOCItem] = field(default_factory=list)
    # Each dict contains:
    # - moc: KU entity properties (MOC is a KU with ORGANIZES relationships)
    # - graph_context: {organized_kus, related_content}

    # Cross-domain relationship insights (extracted from MEGA-QUERY)
    cross_domain_insights: CrossDomainInsightsData = field(default_factory=dict)  # type: ignore[assignment]  # empty dict is valid runtime default for TypedDict
    # Contains:
    # - task_goal_alignments: {task_uid: {goal_uid, alignment_score}}
    # - knowledge_task_applications: {ku_uid: [task_uids applying this knowledge]}
    # - principle_goal_alignments: {principle_uid: {goal_uid, alignment_score}}
    # - learning_path_progress: {path_uid: {completed_steps, total_steps, next_step}}

    # =========================================================================
    # CORE METHODS - Validation and metadata
    # =========================================================================

    def is_cached_valid(self) -> bool:
        """Check if cached context is still valid"""
        if not self.last_refresh:
            return False
        age = (datetime.now() - self.last_refresh).total_seconds()
        return age < self.cache_ttl_seconds

    @property
    def mastery_average(self) -> float:
        """Compute average mastery across all knowledge units"""
        if not self.knowledge_mastery:
            return 0.0
        return sum(self.knowledge_mastery.values()) / len(self.knowledge_mastery)

    @property
    def concepts_needing_review(self) -> list[str]:
        """Get knowledge units that need review (mastery 0.4-0.8 range)"""
        return [
            uid
            for uid, mastery in self.knowledge_mastery.items()
            if 0.4 <= mastery < 0.8  # Not mastered but not completely forgotten
        ]

    # =========================================================================
    # CONTEXT VALIDATION METHODS
    # =========================================================================

    def require_rich_context(self, operation: str) -> None:
        """
        Validate this context was built with rich data (build_rich path).

        Defensive runtime guard used inside the strict rich-only accessors
        (``get_tasks_for_goal``, ``get_blocked_tasks``, etc.) so a
        ``UserContext``-typed value that slipped through static typing still
        fails loudly.

        Prefer the compile-time guard: type the parameter as
        ``RichUserContext`` and the subclass's narrowed fields + pinned
        ``is_rich_context=True`` remove the need for a runtime check.

        Args:
            operation: Name of the operation requiring rich context

        Raises:
            RichContextRequiredError: If context is not rich (built via build() not build_rich())
        """
        if not self.is_rich_context:
            from core.errors import RichContextRequiredError

            raise RichContextRequiredError(operation)

    def get_rich_entities(
        self,
        domain: str,
        filter_uids: set[str] | None = None,
    ) -> list[RichEntityItem]:
        """
        Get rich entity data for an activity domain, optionally filtered by UIDs.

        Args:
            domain: Domain key — "tasks", "goals", "habits", "events", "choices", "principles"
            filter_uids: If provided, only return entities whose uid is in this set.
                         Pass None to return all entities for the domain.

        Returns:
            List of {"entity": {...}, "graph_context": {...}} dicts.
            Empty list if domain not found or no entities match filter.
        """
        entities = self.entities_rich.get(domain, [])
        if filter_uids is None:
            return entities
        return [e for e in entities if e.get("entity", {}).get("uid") in filter_uids]

    # =========================================================================
    # TASK QUERY METHODS
    # =========================================================================

    def get_tasks_for_today(self) -> list[str]:
        """Get prioritized tasks for today"""
        return self.today_task_uids

    def get_tasks_for_goal(self, goal_uid: str) -> list[str]:
        """Get all tasks contributing to a specific goal. Requires rich context."""
        self.require_rich_context("get_tasks_for_goal")
        assert self.tasks_by_goal is not None
        return self.tasks_by_goal.get(goal_uid, [])

    def get_tasks_by_goal(self) -> dict[str, list[str]]:
        """Full goal_uid -> task_uids mapping. Requires rich context."""
        self.require_rich_context("get_tasks_by_goal")
        assert self.tasks_by_goal is not None
        return self.tasks_by_goal

    def tasks_by_goal_or_empty(self) -> dict[str, list[str]]:
        """tasks_by_goal with graceful fallback — empty dict at standard depth."""
        return self.tasks_by_goal if self.tasks_by_goal is not None else {}

    def get_blocked_tasks(self) -> set[str]:
        """Get tasks blocked by prerequisites. Requires rich context."""
        self.require_rich_context("get_blocked_tasks")
        assert self.blocked_task_uids is not None
        return self.blocked_task_uids

    def blocked_task_uids_or_empty(self) -> set[str]:
        """blocked_task_uids with graceful fallback — empty set at standard depth."""
        return self.blocked_task_uids if self.blocked_task_uids is not None else set()

    def get_high_impact_tasks(self, threshold: float = 0.7) -> list[str]:
        """Get tasks with high goal contribution"""
        return [
            uid
            for uid, priority in self.task_priorities.items()
            if priority >= threshold and uid in self.active_task_uids
        ]

    # =========================================================================
    # EVENT QUERY METHODS
    # =========================================================================

    def get_events_for_habit(self, habit_uid: str) -> list[str]:
        """Get events that reinforce a specific habit"""
        return self.events_by_habit.get(habit_uid, [])

    def get_events_needing_attendance(self) -> list[str]:
        """Get upcoming events that maintain important streaks"""
        critical_events = []
        for event_uid in self.upcoming_event_uids:
            if event_uid in self.recurring_event_uids:
                streak = self.event_streaks.get(event_uid, 0)
                if streak > 7:  # Week+ streak at risk
                    critical_events.append(event_uid)
        return critical_events

    # =========================================================================
    # GOAL QUERY METHODS
    # =========================================================================

    def get_goals_nearing_deadline(self, days: int = 30) -> list[str]:
        """Get goals with deadlines within specified days"""
        near_deadline = []
        cutoff_date = date.today() + timedelta(days=days)
        for goal_uid, deadline in self.goal_deadlines.items():
            if deadline <= cutoff_date and goal_uid not in self.completed_goal_uids:
                near_deadline.append(goal_uid)
        return near_deadline

    def get_stalled_goals(self, _threshold_days: int = 14) -> list[str]:
        """Get goals with no recent progress"""
        # Simplified version based on low progress
        return [
            uid
            for uid in self.active_goal_uids
            if self.goal_progress.get(uid, 0) < 0.1  # Less than 10% progress
        ]

    # =========================================================================
    # HABIT QUERY METHODS
    # =========================================================================

    def get_habits_needing_reinforcement(self) -> list[str]:
        """Get habits that need attention to maintain streaks. Requires rich context."""
        self.require_rich_context("get_habits_needing_reinforcement")
        assert self.at_risk_habits is not None
        return self.at_risk_habits

    def at_risk_habits_or_empty(self) -> list[str]:
        """at_risk_habits with graceful fallback — empty list at standard depth."""
        return self.at_risk_habits if self.at_risk_habits is not None else []

    def get_habits_for_goal(self, goal_uid: str) -> list[str]:
        """Get habits supporting a specific goal. Requires rich context."""
        self.require_rich_context("get_habits_for_goal")
        assert self.habits_by_goal is not None
        return self.habits_by_goal.get(goal_uid, [])

    def get_habits_by_goal(self) -> dict[str, list[str]]:
        """Full goal_uid -> habit_uids mapping. Requires rich context."""
        self.require_rich_context("get_habits_by_goal")
        assert self.habits_by_goal is not None
        return self.habits_by_goal

    def habits_by_goal_or_empty(self) -> dict[str, list[str]]:
        """habits_by_goal with graceful fallback — empty dict at standard depth."""
        return self.habits_by_goal if self.habits_by_goal is not None else {}

    def get_high_impact_habits(self) -> list[str]:
        """Get keystone habits that affect multiple goals"""
        return self.keystone_habits

    # =========================================================================
    # KNOWLEDGE QUERY METHODS
    # =========================================================================

    def get_ready_to_learn(self) -> list[str]:
        """Get knowledge where prerequisites are met"""
        ready = []
        for knowledge_uid in self.next_recommended_knowledge:
            prereqs = self.prerequisites_needed.get(knowledge_uid, [])
            if all(p in self.prerequisites_completed for p in prereqs):
                ready.append(knowledge_uid)
        return ready

    def get_knowledge_gaps_for_goal(self, _goal_uid: str) -> list[str]:
        """Get missing knowledge for a goal"""
        # Would need goal-knowledge mapping
        gaps = []
        for knowledge_uid, prereqs in self.prerequisites_needed.items():
            if prereqs and knowledge_uid not in self.mastered_knowledge_uids:
                gaps.append(knowledge_uid)
        return gaps

    def calculate_life_alignment(self, life_path_knowledge_uids: list[str]) -> float:
        """
        Calculate life path alignment score based on knowledge substance.

        This method embodies "Everything flows toward the life path" philosophy.
        It measures how well the user is APPLYING life path knowledge in real life.

        Args:
            life_path_knowledge_uids: Knowledge UIDs from the user's life path

        Returns:
            0.0-1.0 alignment score (average substance across life path knowledge)

        Philosophy:
            - Pure mastery (0.8+) without substance = 0.5 alignment (theory only)
            - High substance (0.7+) = 0.9+ alignment (lifestyle integration)
            - Life path alignment is NOT about completion, it's about LIVING it
        """
        if not life_path_knowledge_uids:
            return 0.0

        # Get substance scores for all life path knowledge
        # NOTE: This assumes knowledge_mastery dict contains substance scores
        # In practice, this would query PsService for substance_score() values
        total_substance = 0.0
        count = 0

        for ku_uid in life_path_knowledge_uids:
            # Use knowledge_mastery as proxy for substance (would be substance_score in real impl)
            substance = self.knowledge_mastery.get(ku_uid, 0.0)
            total_substance += substance
            count += 1

        # Average substance across all life path knowledge
        avg_alignment = total_substance / count if count > 0 else 0.0

        # Update cached alignment score (NOTE: this is mutation - acceptable for cached derived value)
        self.life_path_alignment_score = avg_alignment

        return avg_alignment

    def is_life_aligned(self, threshold: float = 0.7) -> bool:
        """
        Check if user is living in alignment with their life path.

        Args:
            threshold: Minimum alignment score (default 0.7 = well practiced)

        Returns:
            True if alignment score >= threshold
        """
        return self.life_path_alignment_score >= threshold

    def get_life_path_gaps(self) -> list[str]:
        """
        Get life path knowledge that needs more real-world application.

        Returns:
            List of knowledge UIDs with low substance (<0.5)
        """
        if not self.life_path_uid:
            return []

        gaps = []
        for ku_uid, mastery in self.knowledge_mastery.items():
            # In real implementation, would check if ku_uid is in life path
            # and check actual substance_score, not mastery
            if mastery < 0.5:  # Low substance
                gaps.append(ku_uid)

        return gaps

    # =========================================================================
    # MOC (MAP OF CONTENT) QUERY METHODS
    # =========================================================================

    def get_mocs_for_knowledge(self, ku_uid: str) -> list[str]:
        """Get all MOCs that contain a specific knowledge unit."""
        return self.mocs_by_knowledge.get(ku_uid, [])

    def get_knowledge_in_moc(self, moc_uid: str) -> list[str]:
        """Get all knowledge units organized in a specific MOC."""
        return self.knowledge_by_moc.get(moc_uid, [])

    def get_mocs_for_learning_path(self, lp_uid: str) -> list[str]:
        """Get MOCs that support a specific learning path."""
        return self.mocs_by_learning_path.get(lp_uid, [])

    def get_recently_viewed_mocs(self, limit: int = 5) -> list[str]:
        """Get recently viewed MOCs for quick navigation."""
        return self.recently_viewed_moc_uids[:limit]

    def get_most_used_mocs(self, limit: int = 5) -> list[str]:
        """Get most frequently accessed MOCs."""
        from core.utils.sort_functions import get_result_score

        sorted_mocs = sorted(self.moc_view_counts.items(), key=get_result_score, reverse=True)
        return [moc_uid for moc_uid, _ in sorted_mocs[:limit]]

    def has_moc_for_domain(self, domain: Domain) -> bool:
        """Check if user has any MOC for a specific domain."""
        # This would require domain info from active_mocs_rich
        # For now, check if any MOCs exist
        return len(self.active_moc_uids) > 0

    # =========================================================================
    # FACET QUERY METHODS
    # =========================================================================

    def evaluate_against_facets(self, required_facets: dict[str, list[str]]) -> float:
        """
        Evaluate how well user context matches required facets.

        Args:
            required_facets: Dict of facet types to required values

        Returns:
            Match score from 0.0 to 1.0
        """
        if not required_facets:
            return 1.0

        total_score = 0.0
        facet_count = 0

        for facet_type, required_values in required_facets.items():
            if not required_values:
                continue

            user_values = self.facet_profile.get(facet_type, [])
            if user_values:
                # Calculate overlap
                overlap = len(set(required_values) & set(user_values))
                score = overlap / len(required_values)

                # Weight by affinity if available
                for value in required_values:
                    if value in self.facet_affinities:
                        score *= (1 + self.facet_affinities[value]) / 2

                total_score += score
                facet_count += 1

        return total_score / facet_count if facet_count > 0 else 0.0

    def get_top_facets(self, facet_type: str, n: int = 10) -> list[str]:
        """Get top N facets of a given type, sorted by affinity."""
        facets = self.facet_profile.get(facet_type, [])

        # Sort by affinity
        facets_with_scores = []
        for facet in facets:
            score = self.facet_affinities.get(facet, 0.5)
            facets_with_scores.append((facet, score))

        facets_with_scores.sort(key=itemgetter(1), reverse=True)
        return [f[0] for f in facets_with_scores[:n]]

    # =========================================================================
    # DERIVED / CACHE-LOCAL MUTATIONS (SAFE)
    # =========================================================================
    # These methods mutate context state, but only for:
    # - Non-authoritative derived values
    # - Session-local facet tracking
    # - Cached computation results
    #
    # See MUTATION GOVERNANCE in class docstring for rules.

    def update_facet_affinity(self, facet: str, delta: float = 0.1) -> None:
        """
        Update affinity for a facet based on user interaction.

        MUTATION: Modifies facet_affinities, facet_interaction_history.
        This is acceptable - facet tracking is cache-local, non-authoritative.
        """
        current = self.facet_affinities.get(facet, 0.5)
        new_value = min(1.0, max(0.0, current + delta))
        self.facet_affinities[facet] = new_value

        # Track in history
        self.facet_interaction_history.append(
            {
                "facet": facet,
                "action": "affinity_update",
                "delta": delta,
                "new_value": new_value,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # Limit history size
        if len(self.facet_interaction_history) > 100:
            self.facet_interaction_history = self.facet_interaction_history[-100:]

    def add_facet(self, facet_type: str, value: str) -> None:
        """
        Add a facet value to the profile.

        MUTATION: Modifies facet_profile, facet_affinities.
        This is acceptable - facet tracking is cache-local, non-authoritative.
        """
        if facet_type not in self.facet_profile:
            self.facet_profile[facet_type] = []

        if value not in self.facet_profile[facet_type]:
            self.facet_profile[facet_type].append(value)

            # Initialize affinity if not present
            if value not in self.facet_affinities:
                self.facet_affinities[value] = 0.5

    def get_facet_recommendations(self) -> dict[str, Any]:
        """Get recommendations based on facet profile."""
        return {
            "preferred_tags": self.get_top_facets("tags", 10),
            "preferred_domains": self.get_top_facets("domains", 5),
            "preferred_difficulty": self.get_top_facets("difficulty", 1),
            "content_types": sorted(
                self.content_type_preferences.items(), key=itemgetter(1), reverse=True
            )[:5],
        }

    # =========================================================================
    # PRINCIPLE QUERY METHODS
    # =========================================================================

    def get_principle_aligned_tasks(self, principle_uid: str) -> list[str]:
        """Get tasks aligned with a specific principle"""
        # Would need task-principle alignment data
        aligned = []
        if principle_uid in self.core_principle_uids:
            importance = self.principle_priorities.get(principle_uid, 0.5)
            if importance > 0.7:
                # Return high-priority tasks when principle is important
                aligned = self.get_high_impact_tasks()
        return aligned

    def has_principle_conflict(self, action_domain: Domain) -> bool:
        """Check if an action might conflict with principles"""
        alignment = self.principle_alignment_by_domain.get(action_domain, 1.0)
        return alignment < 0.5

    def get_principle_guided_choice_counts(self) -> dict[str, int]:
        """Counts of principle-guided choices by principle uid. Requires rich context."""
        self.require_rich_context("get_principle_guided_choice_counts")
        assert self.principle_guided_choice_counts is not None
        return self.principle_guided_choice_counts

    def principle_guided_choice_counts_or_empty(self) -> dict[str, int]:
        """principle_guided_choice_counts with graceful fallback — empty dict at standard depth."""
        return (
            self.principle_guided_choice_counts
            if self.principle_guided_choice_counts is not None
            else {}
        )

    def get_recent_principle_aligned_choices(self) -> list[str]:
        """Up to 10 recently principle-aligned choice uids. Requires rich context."""
        self.require_rich_context("get_recent_principle_aligned_choices")
        assert self.recent_principle_aligned_choices is not None
        return self.recent_principle_aligned_choices

    def recent_principle_aligned_choices_or_empty(self) -> list[str]:
        """recent_principle_aligned_choices with graceful fallback — empty list at standard depth."""
        return (
            self.recent_principle_aligned_choices
            if self.recent_principle_aligned_choices is not None
            else []
        )

    def get_principle_integration_score(self) -> float:
        """Overall principle-choice integration score (0.0-1.0). Requires rich context.

        No graceful accessor: a standard-depth read is a bug, not a degraded path —
        0.0 at rich depth is a legitimate "no alignment" signal and must not be
        conflated with "not computed" at standard depth.
        """
        self.require_rich_context("get_principle_integration_score")
        assert self.principle_integration_score is not None
        return self.principle_integration_score

    # =========================================================================
    # WORKLOAD QUERY METHODS
    # =========================================================================

    def calculate_current_workload(self) -> float:
        """Calculate current workload (0-1 scale)"""
        # Simple heuristic based on active items
        active_items = (
            len(self.active_task_uids) + len(self.today_event_uids) + len(self.daily_habits)
        )
        capacity = self.available_minutes_daily // 15  # 15 min per item average
        return min(1.0, active_items / max(capacity, 1))

    def has_capacity_for_new_goal(self) -> bool:
        """Check if user can take on a new goal"""
        return (
            self.current_workload_score < 0.8
            and len(self.active_goal_uids) < 5
            and not self.is_overwhelmed
        )

    def get_recommended_next_action(self) -> dict[str, Any]:
        """
        Get a conservative next-action hint based on context state.

        **FALLBACK HEURISTIC ONLY**

        This method provides a basic, deterministic recommendation based on
        simple priority rules. It does NOT consider:
        - User preferences or learning style
        - Time of day or energy levels
        - Cross-domain optimization
        - Semantic relationships between items

        For comprehensive recommendations, use UserContextIntelligence methods:
        - get_ready_to_work_on_today()
        - get_optimal_next_path_steps()
        - get_schedule_aware_recommendations()

        This method exists for:
        - Quick fallback when intelligence services are unavailable
        - Simple API responses where full intelligence is overkill
        - Testing and debugging

        Returns:
            Dict with type, action, and items (UIDs)
        """
        if self.is_blocked:
            # Focus on unblocking
            return {
                "type": "unblock",
                "action": "complete_prerequisites",
                "items": list(self.prerequisites_needed.keys())[:3],
            }
        elif at_risk := self.at_risk_habits_or_empty():
            # Maintain streaks (empty at standard depth — accessor handles the gate)
            return {
                "type": "maintain",
                "action": "reinforce_habits",
                "items": at_risk[:2],
            }
        elif self.overdue_task_uids:
            # Catch up on overdue
            return {
                "type": "catch_up",
                "action": "complete_overdue",
                "items": self.overdue_task_uids[:2],
            }
        else:
            # Progress on primary goal
            return {
                "type": "progress",
                "action": "advance_goal",
                "items": self.get_tasks_for_goal(self.primary_goal_focus)[:2]
                if self.primary_goal_focus
                else [],
            }

    # =========================================================================
    # CONVENIENCE PROPERTIES (Derived from canonical fields)
    # =========================================================================
    # Per SKUEL's "One Path Forward" philosophy, these are NOT backward
    # compatibility shims. They are convenience methods that:
    # 1. Derive from canonical fields (no separate data storage)
    # 2. Provide meaningful aggregation or transformation
    # 3. Are used in multiple call sites (justifies the abstraction)
    #
    # Properties with 0-1 usages have been removed - call sites updated
    # to use canonical fields directly.

    @property
    def has_overdue_items(self) -> bool:
        """
        Check if user has any overdue tasks.

        Convenience: Derives from overdue_task_uids (2 call sites).
        """
        return len(self.overdue_task_uids) > 0

    @property
    def blocked_knowledge_uids(self) -> set[str]:
        """
        Get knowledge units blocked by missing prerequisites.

        Convenience: Derives from prerequisites_needed keys (4 call sites).
        Provides set semantics for membership testing.
        """
        return set(self.prerequisites_needed.keys())

    def calculate_learning_velocity(self) -> float:
        """
        Calculate overall learning velocity across all domains.

        Convenience: Aggregates learning_velocity_by_domain (5 call sites).
        Provides single scalar for quick velocity assessment.

        Returns:
            Average learning velocity (0.0-1.0)
        """
        if not self.learning_velocity_by_domain:
            return 0.0
        return sum(self.learning_velocity_by_domain.values()) / len(
            self.learning_velocity_by_domain
        )


# =========================================================================
# RICH USER CONTEXT — static-type split (ADR-like Step B, 2026-04-21)
# =========================================================================


@dataclass
class RichUserContext(UserContext):
    """
    UserContext subclass whose type narrows the seven RICH_ONLY_FIELDS
    to their populated container types (no `| None`).

    `is_rich_context` is pinned `True`, so the runtime `require_rich_context()`
    guard is effectively compile-time enforced for any code typed against
    `RichUserContext`.

    **When to use:**
    - Builder `build_rich()` / `build_rich_user_context()` return this.
    - Intelligence services that require rich data declare `context: RichUserContext`.
    - Planning methods that need rich-only fields take `context: RichUserContext`.

    **Relationship to rich-only accessors (important):**

    `RichUserContext` is the *compile-time* guard. The `get_X()` /
    `X_or_empty()` accessors on `UserContext` are the *read path*. They serve
    different jobs and both stay in use:

    - The type prevents None-unsafety — mypy sees the narrowed field and
      every method on a `RichUserContext`-typed consumer is provably called
      with rich data.
    - The accessors are the uniform read path for ALL consumers, including
      ones typed against plain `UserContext` that branch on `is_rich()`.
      They also act as the single audit chokepoint if the rich/standard
      contract ever changes.

    Narrowing the parameter type does **not** license inlining
    `self.context.habits_by_goal` in place of `self.context.get_habits_by_goal()`.
    SKUEL018 is name-based by design — it flags direct rich-only field reads
    regardless of receiver type so the read path stays uniform across
    consumers with different static context types. Files typed against
    `RichUserContext` are still expected to go through the accessors; the
    lint whitelist exists only for the accessor definitions themselves and
    for the populator.

    **mypy note:** narrowing a dataclass field in a subclass needs
    `type: ignore[assignment]` — this is a well-known mypy limitation
    (python/mypy#9254), not a design flaw. Six ignores total.
    """

    # Narrow rich-only containers from `X | None` to `X`.
    # mypy flags the override as incompatible because `default_factory=...`
    # changes the effective default from None → empty container.
    tasks_by_goal: dict[str, list[str]] = field(default_factory=dict)  # type: ignore[assignment]
    habits_by_goal: dict[str, list[str]] = field(default_factory=dict)  # type: ignore[assignment]
    at_risk_habits: list[str] = field(default_factory=list)  # type: ignore[assignment]
    blocked_task_uids: set[str] = field(default_factory=set)  # type: ignore[assignment]
    principle_guided_choice_counts: dict[str, int] = field(default_factory=dict)  # type: ignore[assignment]
    recent_principle_aligned_choices: list[str] = field(default_factory=list)  # type: ignore[assignment]
    principle_integration_score: float = 0.0  # type: ignore[assignment]

    # Pinned: every RichUserContext is — by construction — a rich context.
    is_rich_context: bool = True

    # Canonical set of fields this subclass narrows. Populated only by the
    # rich build path; every entry has a matching `get_X()` strict accessor
    # and (except `principle_integration_score`) a matching `X_or_empty()`
    # graceful accessor on `UserContext`. SKUEL018 references this set by
    # name for its direct-access lint. Living on the subclass matches its
    # role as metadata about what `RichUserContext` itself narrows.
    RICH_ONLY_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "tasks_by_goal",
            "habits_by_goal",
            "at_risk_habits",
            "blocked_task_uids",
            "principle_guided_choice_counts",
            "recent_principle_aligned_choices",
            "principle_integration_score",
        }
    )


def is_rich(ctx: UserContext) -> TypeGuard[RichUserContext]:
    """
    Type guard for opportunistic narrowing.

    Use when you hold a `UserContext` and want to call rich-required methods
    when the context happens to be rich, without a cast:

        if is_rich(ctx):
            # ctx is narrowed to RichUserContext in this block
            plan = await intelligence_factory.create(ctx).get_ready_to_work_on_today()
    """
    return ctx.is_rich_context


# =========================================================================
# EXPORTS
# =========================================================================

__all__ = [
    "UserContext",
    "RichUserContext",
    "is_rich",
]
