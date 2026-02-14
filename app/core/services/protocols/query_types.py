"""
Query Types - Type-safe TypedDicts for Query Parameters and Payloads
=====================================================================

Foundation TypedDicts replacing ~70% of `dict[str, Any]` patterns across SKUEL.

Design Philosophy
-----------------
These TypedDicts provide structure hints without sacrificing the 100% Dynamic
Backend Pattern. All fields use `total=False` for flexibility - callers can
provide any subset of fields. TypedDicts are structural subtypes of `dict[str, Any]`,
ensuring backward compatibility.

Coverage Areas
--------------
1. **CypherParams** - Common Cypher query parameters (~80% coverage)
2. **Filter Specs** - Service query filtering (Base, Activity, Curriculum)
3. **Update Payloads** - CRUD operation payloads (Base + domain-specific)
4. **Query/Response Types** - Cypher WHERE clauses, ORDER BY specs

Usage
-----
    from core.services.protocols.query_types import (
        CypherParams, ActivityFilterSpec, TaskUpdatePayload
    )

    # Type-safe filter construction
    filters: ActivityFilterSpec = {
        "status": "active",
        "priority": "high",
        "include_completed": False,
    }

    # IDE autocomplete works!
    result = await service.list(filters=filters)

Incremental Adoption
--------------------
- New code MUST use TypedDicts where applicable
- Existing code migrates gradually (backward compatible)
- Services can still accept `dict[str, Any]` - TypedDict is a subtype

See Also
--------
    /docs/patterns/three_tier_type_system.md - Three-tier architecture
    /core/services/protocols/base_protocols.py - Related TypedDicts
    /core/models/query/cypher/_types.py - Cypher query types

Date Added: January 2026 (Type Safety Improvements)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from datetime import date, datetime

# ============================================================================
# CYPHER QUERY PARAMETERS
# ============================================================================


class CypherParams(TypedDict, total=False):
    """
    Common Cypher query parameters covering ~80% of queries.

    These are the most frequently used parameters across SKUEL's Cypher queries.
    Using this TypedDict provides IDE autocomplete and catches typos at dev time.

    Core Identity Parameters:
        uid: Entity UID (e.g., "task_123abc", "goal_456def")
        user_uid: User UID (e.g., "user_mike")

    Pagination:
        limit: Maximum results to return
        offset: Skip first N results

    Common Filters:
        title: Entity title (text search target)
        status: Status string (e.g., "active", "completed")
        start_date: ISO date string for range start
        end_date: ISO date string for range end

    Usage:
        params: CypherParams = {"uid": "task_123abc", "user_uid": "user_mike"}
        await backend.execute_query(cypher, params)
    """

    uid: str
    user_uid: str
    limit: int
    offset: int
    title: str
    status: str
    start_date: str
    end_date: str
    # Additional common parameters
    category: str
    domain: str
    priority: str
    query_text: str


# ============================================================================
# FILTER SPECIFICATIONS
# ============================================================================


class BaseFilterSpec(TypedDict, total=False):
    """
    Base filter specification for service queries.

    All domain filter specs extend this base. Provides common filtering
    patterns used across Activity, Curriculum, and Finance domains.

    Status Filtering:
        status: Single status or list of statuses
        category: Single category or list of categories

    User Scoping:
        user_uid: Filter to specific user's entities

    Time Filtering:
        created_after: ISO date string
        created_before: ISO date string

    Pagination & Sorting:
        limit: Maximum results (default varies by service)
        offset: Skip first N results
        sort_by: Field to sort by
        sort_order: "asc" or "desc"

    Usage:
        filters: BaseFilterSpec = {
            "status": "active",
            "limit": 50,
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        result = await service.list(filters=filters)
    """

    status: str | list[str]
    category: str | list[str]
    user_uid: str
    created_after: str
    created_before: str
    limit: int
    offset: int
    sort_by: str
    sort_order: Literal["asc", "desc"]


class ActivityFilterSpec(BaseFilterSpec, total=False):
    """
    Filter specification for Activity domains (Tasks, Goals, Habits, Events, Choices, Principles).

    Extends BaseFilterSpec with activity-specific filtering.

    Priority Filtering:
        priority: Single priority or list (e.g., "high", ["high", "medium"])

    Date Range Filtering:
        due_date: Exact due date match
        due_after: Due date >= this date
        due_before: Due date <= this date

    Completion Handling:
        include_completed: Whether to include completed/archived items

    Domain Filtering:
        domain: Life domain (TECH, HEALTH, PERSONAL, etc.)

    Usage:
        filters: ActivityFilterSpec = {
            "priority": "high",
            "include_completed": False,
            "due_after": "2026-01-01",
            "domain": "TECH",
        }
        result = await tasks_service.list(filters=filters)
    """

    priority: str | list[str]
    due_date: str
    due_after: str
    due_before: str
    include_completed: bool
    domain: str


class CurriculumFilterSpec(BaseFilterSpec, total=False):
    """
    Filter specification for Curriculum domains (KU, LS, LP).

    Curriculum entities are shared (no user_uid ownership), but can be
    filtered by various curriculum-specific attributes.

    Complexity Filtering:
        complexity: Single or list (e.g., "beginner", ["intermediate", "advanced"])

    Domain Filtering:
        domain: Subject domain for curriculum content

    Graph Relationships:
        prerequisite_uid: Filter by prerequisite relationship
        learning_path_uid: Filter KUs/LSs by learning path membership

    Progress Filtering:
        is_completed: Filter by completion status (for user progress)
        mastery_level: Minimum mastery level

    Usage:
        filters: CurriculumFilterSpec = {
            "domain": "TECH",
            "complexity": "intermediate",
            "limit": 100,
        }
        result = await ku_service.list(filters=filters)
    """

    complexity: str | list[str]
    domain: str
    prerequisite_uid: str
    learning_path_uid: str
    is_completed: bool
    mastery_level: float


# ============================================================================
# UPDATE PAYLOADS
# ============================================================================


class BaseUpdatePayload(TypedDict, total=False):
    """
    Base update payload for CRUD operations.

    All domain update payloads extend this. These fields are common across
    all 14 domains.

    Core Fields:
        title: Entity title/name
        description: Entity description/details
        status: Current status

    Metadata:
        updated_at: ISO timestamp (usually auto-set by service)

    Usage:
        updates: BaseUpdatePayload = {
            "title": "New Title",
            "status": "active",
        }
        result = await service.update(uid, updates)
    """

    title: str
    description: str
    status: str
    updated_at: str


class TaskUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for Task entities.

    Task-Specific Fields:
        priority: Task priority (high, medium, low, urgent)
        due_date: ISO date string
        completed_at: ISO timestamp when completed
        progress: Completion progress 0.0-1.0

    Relationship Hints:
        goal_uid: Associated goal (for UI hints, actual link via relationships)

    Usage:
        updates: TaskUpdatePayload = {
            "status": "completed",
            "completed_at": "2026-01-21T10:30:00Z",
            "progress": 1.0,
        }
        result = await tasks_service.update(uid, updates)
    """

    priority: str
    due_date: str
    completed_at: str
    progress: float
    goal_uid: str


class GoalUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for Goal entities.

    Goal-Specific Fields:
        target_date: ISO date string for goal target
        progress_percentage: Progress toward goal 0.0-100.0
        completion_date: ISO date string when goal was completed
        domain: Life domain (TECH, HEALTH, etc.)
        current_value: Current value for measurable goals
        metadata: Goal metadata dict

    Usage:
        updates: GoalUpdatePayload = {
            "progress_percentage": 75.0,
            "target_date": "2026-06-30",
        }
        result = await goals_service.update(uid, updates)
    """

    target_date: str | date
    progress_percentage: float
    completion_date: str | date
    domain: str
    current_value: float
    metadata: dict[str, Any]
    milestones: list[Any]


class HabitUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for Habit entities.

    Habit-Specific Fields:
        frequency: Habit frequency (daily, weekly, etc.)
        current_streak: Current consecutive completions
        best_streak: Best streak ever achieved
        last_completed: ISO timestamp of last completion

    Tracking:
        target_count: Target completions per period
        actual_count: Actual completions this period

    Usage:
        updates: HabitUpdatePayload = {
            "current_streak": 7,
            "last_completed": "2026-01-21",
        }
        result = await habits_service.update(uid, updates)
    """

    frequency: str
    current_streak: int
    best_streak: int
    last_completed: str | datetime
    target_count: int
    actual_count: int
    total_completions: int
    consistency_30d: float


class EventUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for Event entities.

    Event-Specific Fields:
        event_date: ISO date string
        start_time: ISO time or datetime string
        end_time: ISO time or datetime string
        location: Event location

    Recurrence:
        is_recurring: Whether event recurs
        recurrence_pattern: Recurrence rule (e.g., "WEEKLY")

    Usage:
        updates: EventUpdatePayload = {
            "event_date": "2026-02-15",
            "start_time": "14:00",
            "end_time": "15:30",
        }
        result = await events_service.update(uid, updates)
    """

    event_date: str
    start_time: str
    end_time: str
    location: str
    is_recurring: bool
    recurrence_pattern: str
    notes: str


class ChoiceUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for Choice entities.

    Choice-Specific Fields:
        urgency: Urgency level (critical, high, medium, low)
        deadline: ISO date string for decision deadline
        decision_made: Whether decision has been made
        selected_option_uid: UID of selected option

    Analysis:
        confidence: Decision confidence 0.0-1.0
        decision_rationale: Why this option was selected

    Usage:
        updates: ChoiceUpdatePayload = {
            "decision_made": True,
            "selected_option_uid": "option:123",
            "confidence": 0.85,
        }
        result = await choices_service.update(uid, updates)
    """

    urgency: str
    deadline: str
    decision_made: bool
    selected_option_uid: str
    confidence: float
    decision_rationale: str


class PrincipleUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for Principle entities.

    Principle-Specific Fields:
        category: Principle category (CORE, GROWTH, etc.)
        strength: How strongly held (core, strong, developing, aspirational)
        why_matters: Explanation of importance

    Review:
        last_reviewed: ISO timestamp of last review
        review_notes: Notes from review

    Usage:
        updates: PrincipleUpdatePayload = {
            "strength": "core",
            "last_reviewed": "2026-01-21",
        }
        result = await principles_service.update(uid, updates)
    """

    category: str
    strength: str
    why_matters: str
    last_reviewed: str
    review_notes: str


class KuUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for KnowledgeUnit entities.

    KU-Specific Fields:
        complexity: Difficulty level (beginner, intermediate, advanced)
        domain: Subject domain
        source_path: Path to source markdown file

    Metadata:
        tags: List of tags
        aliases: Alternative names

    Usage:
        updates: KuUpdatePayload = {
            "complexity": "intermediate",
            "tags": ["python", "async"],
        }
        result = await ku_service.update(uid, updates)
    """

    complexity: str
    domain: str
    source_path: str
    tags: list[str]
    aliases: list[str]


class LsUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for LearningStep entities.

    LS-Specific Fields:
        order_index: Position in learning path
        estimated_minutes: Estimated time to complete
        is_optional: Whether step is optional

    Progress:
        is_completed: Whether step is completed
        completed_at: ISO timestamp when completed

    Usage:
        updates: LsUpdatePayload = {
            "is_completed": True,
            "completed_at": "2026-01-21T10:00:00Z",
        }
        result = await ls_service.update(uid, updates)
    """

    order_index: int
    estimated_minutes: int
    is_optional: bool
    is_completed: bool
    completed_at: str


class LpUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for LearningPath entities.

    LP-Specific Fields:
        goal: Learning objective/outcome
        domain: Subject domain
        estimated_hours: Total estimated time

    Progress:
        progress: Overall progress 0.0-1.0
        is_completed: Whether path is completed

    Usage:
        updates: LpUpdatePayload = {
            "progress": 0.5,
            "goal": "Master Python async programming",
        }
        result = await lp_service.update(uid, updates)
    """

    goal: str
    domain: str
    estimated_hours: float
    progress: float
    is_completed: bool


class FinanceUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for Finance/Expense entities.

    Finance-Specific Fields:
        amount: Expense amount
        paid_at: ISO date string when paid
        receipt_link: URL or path to receipt image/document
        has_receipt: Whether receipt is attached

    Categorization:
        category: Expense category
        vendor: Vendor/merchant name
        payment_method: How payment was made

    Usage:
        updates: FinanceUpdatePayload = {
            "status": "paid",
            "paid_at": "2026-01-21",
            "has_receipt": True,
        }
        result = await finance_service.update(uid, updates)
    """

    amount: float
    paid_at: str | date
    receipt_link: str
    has_receipt: bool
    category: str
    vendor: str
    payment_method: str


class ReportUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for Report entities.

    Report-Specific Fields:
        processing_started_at: ISO timestamp when processing began
        processing_completed_at: ISO timestamp when processing finished
        processing_error: Error message if processing failed

    Status Tracking:
        file_type: Type of uploaded file
        original_filename: Original uploaded filename

    Usage:
        updates: ReportUpdatePayload = {
            "status": "completed",
            "processing_completed_at": "2026-01-21T10:30:00Z",
        }
        result = await reports_service.update(uid, updates)
    """

    processing_started_at: str | datetime
    processing_completed_at: str | datetime
    processing_error: str
    file_type: str
    original_filename: str


# ============================================================================
# SPECIALIZED FILTER SPECIFICATIONS
# ============================================================================


class PropertyFilterSpec(TypedDict, total=False):
    """
    Filter specification supporting comparison operators.

    Used for relationship property filtering with operators like __gte, __lte.
    The field names use double-underscore suffix notation for operators.

    Operator Suffixes:
        field__gte: Greater than or equal (>=)
        field__gt: Greater than (>)
        field__lte: Less than or equal (<=)
        field__lt: Less than (<)
        field__in: In list
        field__contains: Contains substring

    Common Filter Fields:
        strength__gte: Minimum relationship strength
        confidence__gte: Minimum confidence score
        score__lte: Maximum score threshold

    Usage:
        filters: PropertyFilterSpec = {
            "strength__gte": 0.8,
            "confidence__gte": 0.7,
        }
        result = await service.find_relationships(filters=filters)
    """

    # Strength filters
    strength__gte: float
    strength__gt: float
    strength__lte: float
    strength__lt: float
    # Confidence filters
    confidence__gte: float
    confidence__gt: float
    confidence__lte: float
    confidence__lt: float
    # Score filters
    score__gte: float
    score__gt: float
    score__lte: float
    score__lt: float
    # Count filters
    count__gte: int
    count__gt: int
    count__lte: int
    count__lt: int


class PrinciplesFilterSpec(BaseFilterSpec, total=False):
    """
    Filter specification for Principles domain.

    Extends BaseFilterSpec with principles-specific filtering options.

    Principles-Specific Fields:
        strength: Filter by principle strength (core, strong, developing, aspirational)
        is_active: Whether principle is actively applied

    Usage:
        filters: PrinciplesFilterSpec = {
            "category": "CORE",
            "strength": "core",
            "sort_by": "strength",
        }
        result = await principles_service.list(filters=filters)
    """

    strength: str | list[str]
    is_active: bool


# ============================================================================
# CYPHER QUERY BUILDING TYPES
# ============================================================================


class WhereClauseSpec(TypedDict, total=False):
    """
    Specification for building WHERE clause conditions.

    Used by CypherGenerator and query builders to construct type-safe
    WHERE clauses.

    Fields:
        property_name: Neo4j property to filter on
        operator: Comparison operator
        value: Value to compare against
        param_name: Override parameter name (default: property_name)

    Usage:
        clause: WhereClauseSpec = {
            "property_name": "status",
            "operator": "=",
            "value": "active",
        }
    """

    property_name: str
    operator: Literal["=", "!=", ">", "<", ">=", "<=", "IN", "CONTAINS", "STARTS WITH", "ENDS WITH"]
    value: str | int | float | bool | list[str] | list[int]
    param_name: str


class OrderBySpec(TypedDict, total=False):
    """
    Specification for ORDER BY clauses.

    Fields:
        field: Property to sort by
        direction: ASC or DESC (default ASC)

    Usage:
        order: OrderBySpec = {
            "field": "created_at",
            "direction": "DESC",
        }
    """

    field: str
    direction: Literal["ASC", "DESC"]


class PaginationSpec(TypedDict, total=False):
    """
    Pagination specification.

    Fields:
        limit: Maximum results (default varies)
        offset: Skip first N results (default 0)
        cursor: Cursor-based pagination token (alternative to offset)

    Usage:
        pagination: PaginationSpec = {"limit": 50, "offset": 100}
    """

    limit: int
    offset: int
    cursor: str


# ============================================================================
# RESPONSE/CONTEXT TYPES
# ============================================================================


class GraphContextResult(TypedDict, total=False):
    """
    Result structure for cross-domain graph context queries.

    Used by `*_cross_domain_context` methods to return type-safe results.

    Entity Data:
        uid: Entity UID
        entity_type: Domain type (task, goal, etc.)
        title: Entity title
        status: Current status

    Related Entities (UIDs or summary objects):
        goals: Related goal UIDs
        tasks: Related task UIDs
        knowledge: Related KU UIDs
        habits: Related habit UIDs
        principles: Related principle UIDs

    Metadata:
        traversal_depth: How deep the graph was traversed
        total_relationships: Count of all relationships found

    Usage:
        context: GraphContextResult = await service.get_cross_domain_context(uid)
        goals = context.get("goals", [])
    """

    uid: str
    entity_type: str
    title: str
    status: str
    goals: list[str]
    tasks: list[str]
    knowledge: list[str]
    habits: list[str]
    principles: list[str]
    events: list[str]
    choices: list[str]
    traversal_depth: int
    total_relationships: int


class ProgressResult(TypedDict, total=False):
    """
    Result structure for progress tracking operations.

    Used by Goals, Habits, Tasks progress methods.

    Core Metrics:
        progress: Current progress 0.0-1.0
        previous_progress: Previous progress value
        delta: Change in progress

    Streak Data (Habits):
        current_streak: Current consecutive completions
        best_streak: Best streak ever
        streak_broken: Whether streak was broken

    Timestamps:
        updated_at: When progress was updated
        completed_at: When entity was completed (if applicable)

    Context:
        contributing_tasks: Tasks that contributed to progress
        milestone_completed: Whether a milestone was just completed

    Usage:
        result: ProgressResult = await service.update_progress(uid, 0.5)
        if result.get("milestone_completed"):
            # Celebrate!
    """

    progress: float
    previous_progress: float
    delta: float
    current_streak: int
    best_streak: int
    streak_broken: bool
    updated_at: str
    completed_at: str
    contributing_tasks: list[str]
    milestone_completed: bool


class IntelligenceResult(TypedDict, total=False):
    """
    Result structure for intelligence/analytics operations.

    Used by `*IntelligenceService` methods for comprehensive analytics.

    Scores:
        alignment_score: How well aligned (0.0-1.0)
        readiness_score: How ready to proceed (0.0-1.0)
        priority_score: Computed priority (0.0-1.0)
        confidence: Confidence in the analysis (0.0-1.0)

    Recommendations:
        recommended_actions: List of suggested next actions
        blocking_factors: What's preventing progress
        opportunities: Identified opportunities

    Analysis:
        insights: Key insights from analysis
        trends: Trend data over time
        comparisons: Comparisons to benchmarks/averages

    Usage:
        intel: IntelligenceResult = await service.analyze(uid)
        if intel.get("readiness_score", 0) > 0.8:
            # Ready to proceed
    """

    alignment_score: float
    readiness_score: float
    priority_score: float
    confidence: float
    recommended_actions: list[str]
    blocking_factors: list[str]
    opportunities: list[str]
    insights: list[str]
    trends: dict[str, list[float]]
    comparisons: dict[str, float]


# ============================================================================
# USER CONTEXT SERVICE RESPONSE TYPES
# ============================================================================


class DashboardTasksOverview(TypedDict, total=False):
    """
    Task statistics for context dashboard.

    Fields:
        active_count: Number of active tasks
        overdue_count: Number of overdue tasks
        today_count: Tasks due today
        current_focus: Current task focus UID
        blocked_count: Number of blocked tasks
    """

    active_count: int
    overdue_count: int
    today_count: int
    current_focus: str
    blocked_count: int


class DashboardGoalsOverview(TypedDict, total=False):
    """
    Goal categorization for context dashboard.

    Fields:
        active_count: Number of active goals
        primary_focus: Primary goal focus UID
        learning_goals: Count of learning-oriented goals
        outcome_goals: Count of outcome-oriented goals
        process_goals: Count of process-oriented goals
    """

    active_count: int
    primary_focus: str
    learning_goals: int
    outcome_goals: int
    process_goals: int


class DashboardHabitsOverview(TypedDict, total=False):
    """
    Habit health metrics for context dashboard.

    Fields:
        active_count: Number of active habits
        at_risk_count: Habits needing attention
        keystone_count: Keystone habits count
        daily_count: Daily habits count
        weekly_count: Weekly habits count
    """

    active_count: int
    at_risk_count: int
    keystone_count: int
    daily_count: int
    weekly_count: int


class DashboardEventsOverview(TypedDict, total=False):
    """
    Event counts for context dashboard.

    Fields:
        today_count: Events happening today
        upcoming_count: Upcoming events
        recurring_count: Recurring events
        missed_count: Missed events
    """

    today_count: int
    upcoming_count: int
    recurring_count: int
    missed_count: int


class DashboardLearningOverview(TypedDict, total=False):
    """
    Learning path info for context dashboard.

    Fields:
        current_path: Current learning path UID
        life_path: Life path UID
        life_path_alignment: Alignment score (0.0-1.0)
        mastered_knowledge_count: Number of mastered KUs
        ready_to_learn_count: Number of ready-to-learn KUs
    """

    current_path: str
    life_path: str
    life_path_alignment: float
    mastered_knowledge_count: int
    ready_to_learn_count: int


class DashboardCapacityInfo(TypedDict, total=False):
    """
    Workload/energy data for context dashboard.

    Fields:
        available_minutes_daily: Available time in minutes per day
        current_workload: Workload score
        energy_level: Current energy level string
        preferred_time: Preferred time string
    """

    available_minutes_daily: int
    current_workload: float
    energy_level: str
    preferred_time: str


class LearningStepPrediction(TypedDict, total=False):
    """
    Single prediction item for learning steps.

    Fields:
        ku_uid: Knowledge unit UID
        title: KU title
        priority_score: Priority score (0.0-1.0)
        estimated_time_minutes: Estimated completion time
    """

    ku_uid: str
    title: str
    priority_score: float
    estimated_time_minutes: int


class PredictionsData(TypedDict, total=False):
    """
    Wrapper for predictions list.

    Fields:
        next_learning_steps: List of predicted learning steps
    """

    next_learning_steps: list[LearningStepPrediction]


class ContextAlert(TypedDict, total=False):
    """
    Alert/warning structure for context summary.

    Fields:
        type: Alert type (e.g., "overdue_tasks", "at_risk_habits")
        severity: Severity level ("high", "medium", "low")
        message: Human-readable alert message
        item_count: Number of items involved
        workload_score: Workload score (for overloaded alerts)
        capacity: Available capacity (for overloaded alerts)
    """

    type: str
    severity: str
    message: str
    item_count: int
    workload_score: float
    capacity: int


class TopPriorities(TypedDict, total=False):
    """
    Top focus items for context summary.

    Fields:
        task_focus: Current task focus UID
        goal_focus: Primary goal focus UID
        overdue_tasks: List of overdue task UIDs (top 3)
        at_risk_habits: List of at-risk habit UIDs (top 3)
    """

    task_focus: str
    goal_focus: str
    overdue_tasks: list[str]
    at_risk_habits: list[str]


class KeyMetrics(TypedDict, total=False):
    """
    Performance metrics for context summary.

    Fields:
        active_items: Total active items count
        completion_rate: Completion rate (0.0-1.0)
        learning_progress: Learning progress score
        energy_level: Energy level string
    """

    active_items: int
    completion_rate: float
    learning_progress: float
    energy_level: str


class ContextInsights(TypedDict, total=False):
    """
    Intelligence insights for context summary.

    Fields:
        ready_to_learn_count: Number of ready-to-learn KUs
        blocked_items_count: Number of blocked items
        capacity_utilization: Capacity utilization score (0.0-1.0)
    """

    ready_to_learn_count: int
    blocked_items_count: int
    capacity_utilization: float


class ContextDashboard(TypedDict, total=False):
    """
    Dashboard response from UserContextService.get_context_dashboard().

    Comprehensive dashboard with current state across all domains,
    learning recommendations, task priorities, habit health, goal progress,
    and optional predictions.

    Core Fields:
        user_uid: User identifier
        context_version: Context version number
        last_refresh: ISO timestamp of last refresh
        time_window: Time window for analytics (e.g., "7d", "30d")

    Domain Overviews:
        tasks: Task statistics overview
        goals: Goal categorization overview
        habits: Habit health metrics
        events: Event counts
        learning: Learning path info

    Capacity:
        capacity: Workload and energy data

    Optional:
        predictions: Predictive insights (when include_predictions=True)

    Usage:
        dashboard: ContextDashboard = await service.get_context_dashboard(user_uid)
        tasks_info = dashboard.get("tasks", {})
        active_count = tasks_info.get("active_count", 0)
    """

    user_uid: str
    context_version: int
    last_refresh: str
    time_window: str
    tasks: DashboardTasksOverview
    goals: DashboardGoalsOverview
    habits: DashboardHabitsOverview
    events: DashboardEventsOverview
    learning: DashboardLearningOverview
    capacity: DashboardCapacityInfo
    predictions: PredictionsData


class ContextSummary(TypedDict, total=False):
    """
    Summary response from UserContextService.get_context_summary().

    High-level summary suitable for quick overview with top priorities,
    key metrics, and alerts/warnings.

    Core Fields:
        user_uid: User identifier
        generated_at: ISO timestamp of generation

    Summary Data:
        top_priorities: Top focus items
        key_metrics: Performance metrics
        alerts: List of alerts/warnings

    Optional:
        insights: Intelligence insights (when include_insights=True)

    Usage:
        summary: ContextSummary = await service.get_context_summary(user_uid)
        priorities = summary.get("top_priorities", {})
        task_focus = priorities.get("task_focus", "")
    """

    user_uid: str
    generated_at: str
    top_priorities: TopPriorities
    key_metrics: KeyMetrics
    alerts: list[ContextAlert]
    insights: ContextInsights


# ============================================================================
# EXPLICIT EXPORTS
# ============================================================================

__all__ = [
    # Cypher Parameters
    "CypherParams",
    # Filter Specifications - Base
    "BaseFilterSpec",
    "ActivityFilterSpec",
    "CurriculumFilterSpec",
    # Filter Specifications - Specialized
    "PropertyFilterSpec",
    "PrinciplesFilterSpec",
    # Update Payloads - Base
    "BaseUpdatePayload",
    # Update Payloads - Activity Domains
    "TaskUpdatePayload",
    "GoalUpdatePayload",
    "HabitUpdatePayload",
    "EventUpdatePayload",
    "ChoiceUpdatePayload",
    "PrincipleUpdatePayload",
    # Update Payloads - Curriculum Domains
    "KuUpdatePayload",
    "LsUpdatePayload",
    "LpUpdatePayload",
    # Update Payloads - Other Domains
    "FinanceUpdatePayload",
    "ReportUpdatePayload",
    # Query Building Types
    "WhereClauseSpec",
    "OrderBySpec",
    "PaginationSpec",
    # Response/Context Types
    "GraphContextResult",
    "ProgressResult",
    "IntelligenceResult",
    # User Context Service Response Types - Nested Structures
    "DashboardTasksOverview",
    "DashboardGoalsOverview",
    "DashboardHabitsOverview",
    "DashboardEventsOverview",
    "DashboardLearningOverview",
    "DashboardCapacityInfo",
    "LearningStepPrediction",
    "PredictionsData",
    # User Context Service Response Types - Summary Structures
    "ContextAlert",
    "TopPriorities",
    "KeyMetrics",
    "ContextInsights",
    # User Context Service Response Types - Main Response Types
    "ContextDashboard",
    "ContextSummary",
]
