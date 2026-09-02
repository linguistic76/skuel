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
Navigation guide for this ~250-field read model. Each entry points at the
section banner ("# CORE IDENTITY", etc.) used in the class body below —
grep for the banner to jump. Line numbers are deliberately omitted; they
drift as fields are added.

Field blocks (data):

 1. Identity & session        → CORE IDENTITY
 2. Activity domains          → TASK / EVENT / GOAL / HABIT AWARENESS
 3. Curriculum & learning     → KNOWLEDGE & LEARNING PATH AWARENESS
 4. Graph-sourced metadata    → GRAPH-SOURCED RELATIONSHIP METADATA
 5. Principles & choices      → PRINCIPLE AWARENESS, CHOICE AWARENESS
 6. Latest activity report    → FEEDBACK DOMAIN
 7. ZPD capstone              → ZPD AWARENESS
                                (rich-only; computed last, reads all prior
                                 fields; None at standard depth or when
                                 INTELLIGENCE_TIER=core)
 8. Learning-loop engagement  → SUBMISSION & FEEDBACK AWARENESS
 9. Progress & capacity       → PROGRESS AWARENESS, WORKLOAD & CAPACITY
10. Preferences               → USER PREFERENCES & STATE
11. Groups                    → GROUP AWARENESS
12. Rich entity data          → RICH GRAPH CONTEXT
                                (entities_rich; rich-only via build_rich())
13. Organizers                → ORGANIZER (EMERGENT MOC) AWARENESS

Method blocks (read API):

14. Validation                → CONTEXT VALIDATION METHODS (_as_rich)
15. Per-domain queries        → TASK / EVENT / GOAL / HABIT / KNOWLEDGE /
                                PRINCIPLE / WORKLOAD QUERY METHODS
16. Convenience properties    → CONVENIENCE PROPERTIES
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar, TypeGuard, cast

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
        CapacityWarnings,
        CrossDomainInsightsData,
        CurrentPathStepItem,
        GroupSummary,
        PendingRevisedExerciseItem,
        RichEntityItem,
        RichKnowledgeUnitItem,
        RichLearningPathItem,
        RichPathStepItem,
        UnsubmittedExerciseItem,
    )
    from core.services.ps_engagement.engagement import Engagement


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

    # User-level dual-track perception-gap check-ins (ADR-030), keyed by
    # DualTrackDimension value (productivity/engagement/decision_quality). Copied
    # straight off the :User node by UserContextBuilder so the perception-gap
    # aggregator (get_cross_domain_perception_analysis) can fold the user-level
    # dims in alongside the per-entity ones without a second User read.
    dual_track_checkins: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    # Knowledge dual-track (mastery) perception-gap check-ins (ADR-030), keyed by
    # Ku uid. The Knowledge dimension is per-(user, Ku) — a Ku is SHARED, so its
    # mastery check-ins live on the :User node (not the shared :Ku node). Copied off
    # the :User node by UserContextBuilder so the perception-gap aggregator can fold
    # a "Knowledge" bucket in alongside the other dimensions without a second read.
    knowledge_checkins: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

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

    # PS engagement state (per ADR-059) — ps_uid -> Engagement projection of the
    # (User)-[:ENGAGED_WITH]->(PathStep) edge. Populated by build_rich() via
    # PsEngagementService.list_engaged(). None in standard build() path or when
    # list_engaged fails. Consumers must null-check before reading.
    active_ps_engagements: dict[str, Engagement] | None = None

    # Reverse index over active_ps_engagements: spawned instance UID -> ps_uid.
    # Flat lookup so intelligence consumers can ask "did this activity come from
    # a PS engagement?" without scanning every engagement's spawned tuple.
    # Each instance UID is unique to one engagement (engage_pathstep mints fresh
    # `_template_uid` suffixes per spawn), so the mapping is single-valued.
    # Empty dict when active_ps_engagements is None/empty.
    spawned_uid_to_ps_uid: dict[str, str] = field(default_factory=dict)

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

    # UserEntry knowledge metadata (from [:APPLIES_KNOWLEDGE] relationships,
    # written by the EXTRACT_ACTIVITIES pipeline — ADR-069)
    entry_knowledge_applied: dict[str, list[str]] = field(default_factory=dict)  # entry -> ku_uids

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
    # Populated at BOTH depths — the consolidated (standard) and MEGA (rich)
    # queries each carry the latest report. Intelligence services use these
    # fields to reason about recent patterns without an extra round-trip.
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
    # ORGANIZER (EMERGENT MOC) AWARENESS
    # =========================================================================
    # A "MOC" is not a special entity — any owned Entity with outgoing
    # ORGANIZES edges is an organizer (emergent identity). These fields carry
    # the emergent read-pattern from the MEGA-QUERY; Askesis uses them to
    # nudge users toward organizing their knowledge.

    # Owned entities that organize others (have outgoing ORGANIZES edges)
    active_moc_uids: list[str] = field(default_factory=list)

    # Most recently UPDATED organizers (by updated_at, last 10)
    recently_viewed_moc_uids: list[str] = field(default_factory=list)

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

    def _as_rich(self, operation: str) -> RichUserContext:
        """Guard + cast chokepoint for strict rich-only accessors.

        Raises ``RichContextRequiredError`` on a standard-depth context,
        otherwise returns ``self`` narrowed to ``RichUserContext`` so callers
        read the ``RICH_ONLY_FIELDS`` as non-Optional without a separate
        ``assert``. ``cast()`` is a runtime no-op — identity, not a copy.
        """
        if not self.is_rich_context:
            from core.errors import RichContextRequiredError

            raise RichContextRequiredError(operation)
        return cast("RichUserContext", self)

    # =========================================================================
    # TASK QUERY METHODS
    # =========================================================================

    def get_tasks_for_goal(self, goal_uid: str) -> list[str]:
        """Get all tasks contributing to a specific goal. Requires rich context."""
        return self._as_rich("get_tasks_for_goal").tasks_by_goal.get(goal_uid, [])

    def get_tasks_by_goal(self) -> dict[str, list[str]]:
        """Full goal_uid -> task_uids mapping. Requires rich context."""
        return self._as_rich("get_tasks_by_goal").tasks_by_goal

    def tasks_by_goal_or_empty(self) -> dict[str, list[str]]:
        """tasks_by_goal with graceful fallback — empty dict at standard depth."""
        return self.tasks_by_goal if self.tasks_by_goal is not None else {}

    def get_blocked_tasks(self) -> set[str]:
        """Get tasks blocked by prerequisites. Requires rich context."""
        return self._as_rich("get_blocked_tasks").blocked_task_uids

    def blocked_task_uids_or_empty(self) -> set[str]:
        """blocked_task_uids with graceful fallback — empty set at standard depth."""
        return self.blocked_task_uids if self.blocked_task_uids is not None else set()

    # =========================================================================
    # EVENT QUERY METHODS
    # =========================================================================

    def get_events_for_habit(self, habit_uid: str) -> list[str]:
        """Get events that reinforce a specific habit"""
        return self.events_by_habit.get(habit_uid, [])

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
        return self._as_rich("get_habits_needing_reinforcement").at_risk_habits

    def at_risk_habits_or_empty(self) -> list[str]:
        """at_risk_habits with graceful fallback — empty list at standard depth."""
        return self.at_risk_habits if self.at_risk_habits is not None else []

    def get_habits_for_goal(self, goal_uid: str) -> list[str]:
        """Get habits supporting a specific goal. Requires rich context."""
        return self._as_rich("get_habits_for_goal").habits_by_goal.get(goal_uid, [])

    def get_habits_by_goal(self) -> dict[str, list[str]]:
        """Full goal_uid -> habit_uids mapping. Requires rich context."""
        return self._as_rich("get_habits_by_goal").habits_by_goal

    def habits_by_goal_or_empty(self) -> dict[str, list[str]]:
        """habits_by_goal with graceful fallback — empty dict at standard depth."""
        return self.habits_by_goal if self.habits_by_goal is not None else {}

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

    def known_or_engaged_ku_uids(self) -> set[str]:
        """All KUs the user has any relationship with (mastered, in-progress, or blocked).

        Used by entity extraction to scope fuzzy-matching to KUs the user actually
        touches, rather than the full graph.
        """
        return (
            self.mastered_knowledge_uids
            | self.in_progress_knowledge_uids
            | self.blocked_knowledge_uids
        )

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
    # PRINCIPLE QUERY METHODS
    # =========================================================================

    def get_principle_guided_choice_counts(self) -> dict[str, int]:
        """Counts of principle-guided choices by principle uid. Requires rich context."""
        return self._as_rich("get_principle_guided_choice_counts").principle_guided_choice_counts

    def principle_guided_choice_counts_or_empty(self) -> dict[str, int]:
        """principle_guided_choice_counts with graceful fallback — empty dict at standard depth."""
        return (
            self.principle_guided_choice_counts
            if self.principle_guided_choice_counts is not None
            else {}
        )

    def get_recent_principle_aligned_choices(self) -> list[str]:
        """Up to 10 recently principle-aligned choice uids. Requires rich context."""
        return self._as_rich(
            "get_recent_principle_aligned_choices"
        ).recent_principle_aligned_choices

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
        return self._as_rich("get_principle_integration_score").principle_integration_score

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

    def get_capacity_warnings(self) -> "CapacityWarnings":
        """Advisory warnings for surfaces that offer NEW work (search, recommendations).

        Empty dict means no concerns — callers put it straight on
        ``SearchResponse.capacity_warnings``. Reads the builder-computed
        ``current_workload_score`` (calculate_current_workload) and the
        overdue backlog; at most two entries (payload shapes:
        ``core/ports/query_types.py`` WorkloadWarning / OverdueTasksWarning):

        - ``workload`` — score ≥ 0.8: approaching (``high``) or at
          (``at_capacity``) the user's daily capacity
        - ``overdue_tasks`` — any overdue tasks outstanding
        """
        warnings: CapacityWarnings = {}

        score = self.current_workload_score
        if score >= 0.8:
            active_items = (
                len(self.active_task_uids) + len(self.today_event_uids) + len(self.daily_habits)
            )
            at_capacity = score >= 1.0
            descriptor = "at" if at_capacity else "near"
            warnings["workload"] = {
                "level": "at_capacity" if at_capacity else "high",
                "score": round(score, 2),
                "active_items": active_items,
                "message": (
                    f"You're {descriptor} your daily capacity "
                    f"({active_items} active items) — be selective about taking on more."
                ),
            }

        if self.overdue_task_uids:
            count = len(self.overdue_task_uids)
            plural = "s" if count != 1 else ""
            warnings["overdue_tasks"] = {
                "count": count,
                "message": f"{count} task{plural} overdue — consider clearing those first.",
            }

        return warnings

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

    `is_rich_context` is pinned `True`, so the runtime `_as_rich()` guard
    is effectively compile-time enforced for any code typed against
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

    **Internal chokepoint:** strict accessors on ``UserContext`` delegate to
    ``_as_rich(operation)``, which raises ``RichContextRequiredError`` on a
    standard-depth context and otherwise returns ``self`` typed as
    ``RichUserContext``. This collapses the former guard + ``assert`` pair
    into a single expression whose return type carries the invariant.
    ``is_rich()`` remains the external ``TypeGuard``.
    """

    # Narrow rich-only containers from `X | None` to `X`.
    # mypy flags the override as incompatible because `default_factory=...`
    # changes the effective default from None → empty container.
    tasks_by_goal: dict[str, list[str]] = field(default_factory=dict)
    habits_by_goal: dict[str, list[str]] = field(default_factory=dict)
    at_risk_habits: list[str] = field(default_factory=list)
    blocked_task_uids: set[str] = field(default_factory=set)
    principle_guided_choice_counts: dict[str, int] = field(default_factory=dict)
    recent_principle_aligned_choices: list[str] = field(default_factory=list)
    principle_integration_score: float = 0.0

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
