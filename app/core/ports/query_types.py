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
    from core.ports.query_types import (
        CypherParams, ActivityFilterSpec, KuUpdatePayload
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
    /core/ports/base_protocols.py - Related TypedDicts
    /core/models/query/cypher/_types.py - Cypher query types

Date Added: January 2026 (Type Safety Improvements)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypedDict

from core.models.type_hints import Neo4jProperties, UserUID

if TYPE_CHECKING:
    from datetime import date, datetime

    from core.models.enums import ContextHealthScore

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
    user_uid: UserUID
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
    user_uid: UserUID
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
    Filter specification for Curriculum domains (KU, PS, LP).

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
    all entity types.

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


class PsUpdatePayload(BaseUpdatePayload, total=False):
    """
    Update payload for PathStep entities.

    PS-Specific Fields:
        order_index: Position in learning path
        estimated_minutes: Estimated time to complete
        is_optional: Whether step is optional

    Progress:
        is_completed: Whether step is completed
        completed_at: ISO timestamp when completed

    Usage:
        updates: PsUpdatePayload = {
            "is_completed": True,
            "completed_at": "2026-01-21T10:00:00Z",
        }
        result = await ps_service.update(uid, updates)
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


class WorkloadWarning(TypedDict):
    """Workload capacity warning entry.

    Producer: ``UserContext.get_capacity_warnings`` (reads the
    builder-computed ``current_workload_score``).
    """

    level: Literal["high", "at_capacity"]
    score: float
    active_items: int
    message: str


class OverdueTasksWarning(TypedDict):
    """Overdue-backlog warning entry.

    Producer: ``UserContext.get_capacity_warnings`` (from ``overdue_task_uids``).
    """

    count: int
    message: str


class CapacityWarnings(TypedDict, total=False):
    """Advisory capacity warnings for surfaces that offer NEW work.

    Empty dict = no concerns. Producer: ``UserContext.get_capacity_warnings``;
    consumers: ``SearchResponse.capacity_warnings`` (wire field) and the
    /search advisory banner (``_render_capacity_banner``).
    """

    workload: WorkloadWarning
    overdue_tasks: OverdueTasksWarning


class NousSubtopicPair(TypedDict):
    """A single (NOUS topic, sub-topic) co-occurrence pair.

    The typed record each curriculum domain contributes from its own label
    (`KuSearchService`/`PsSearchService.nous_subtopic_pairs`), which
    `SearchRouter.nous_subtopic_map` merges into the dependent /search dropdown's
    vocabulary. Both fields are always present strings (narrowed from the raw
    Neo4j property union at the domain boundary).
    """

    nous: str
    subtopic: str


def to_nous_subtopic_pairs(records: list[Neo4jProperties]) -> list[NousSubtopicPair]:
    """Narrow raw Neo4j `(nous, subtopic)` rows to typed `NousSubtopicPair`s.

    The domain-boundary converter for both `KuSearchService` and
    `PsSearchService.nous_subtopic_pairs`: it drops any row whose `nous` or
    `subtopic` is missing or non-string, so only well-formed pairs reach the
    router merge (no arbitrary record shapes flow into the UI vocabulary).
    """
    pairs: list[NousSubtopicPair] = []
    for record in records:
        nous = record.get("nous")
        subtopic = record.get("subtopic")
        if isinstance(nous, str) and isinstance(subtopic, str):
            pairs.append(NousSubtopicPair(nous=nous, subtopic=subtopic))
    return pairs


class SearchEventProps(TypedDict):
    """Write-side properties for one :SearchEvent node.

    Built by ``SearchEventRecorder`` from a ``search.executed`` event and
    persisted verbatim by ``SearchEventBackend.record_search_event``.
    ``created_at`` is an isoformat string — the backend stores it as a native
    Neo4j datetime via ``datetime($created_at)`` (the writer decides storage
    type; the gap reader returns it back as ``toString(...)``).
    """

    uid: str
    query_text: str
    query_normalized: str
    user_uid: str | None
    entry_point: str
    domains: list[str]
    filters_json: str
    result_count: int
    zero_results: bool
    semantic_boost: bool
    created_at: str


class SearchGapRow(TypedDict):
    """One aggregated content-gap row from ``SearchEventBackend.get_search_gaps``.

    Groups :SearchEvent nodes by ``query_normalized`` over the low/zero-result
    window — the content-authoring queue ("what did people search and not find").
    """

    query: str
    searches: int
    zero_count: int
    avg_results: float
    last_seen: str
    entry_points: list[str]


def _numeric_or_zero(value: object) -> float:
    """Narrow a raw Neo4j property to a number, defaulting non-numerics to 0."""
    return float(value) if isinstance(value, (int, float)) else 0.0


def to_search_gap_rows(records: list[Neo4jProperties]) -> list[SearchGapRow]:
    """Narrow raw Neo4j gap-aggregation rows to typed ``SearchGapRow``s.

    The domain-boundary converter for ``SearchEventBackend.get_search_gaps`` —
    numeric properties are isinstance-narrowed before casting and rows missing
    a query key are dropped, so only well-formed gap rows reach the admin
    surface.
    """
    rows: list[SearchGapRow] = []
    for record in records:
        query = record.get("query")
        if not isinstance(query, str):
            continue
        raw_entry_points = record.get("entry_points") or []
        entry_points = (
            [str(ep) for ep in raw_entry_points] if isinstance(raw_entry_points, list) else []
        )
        rows.append(
            SearchGapRow(
                query=query,
                searches=int(_numeric_or_zero(record.get("searches"))),
                zero_count=int(_numeric_or_zero(record.get("zero_count"))),
                avg_results=_numeric_or_zero(record.get("avg_results")),
                last_seen=str(record.get("last_seen") or ""),
                entry_points=entry_points,
            )
        )
    return rows


class KuEmbeddingRow(TypedDict):
    """One Ku with its stored entity embedding, for in-process pair scoring.

    Read by ``PrereqCandidateBackend.get_kus_with_embeddings`` — the candidate
    stage of prerequisite-edge suggestions computes pairwise cosine over these
    rows in Python (121 Kus ⇒ trivial), so no vector index round-trips are
    needed. ``summary`` coalesces ``summary``/``description`` for LLM-judge
    context.
    """

    uid: str
    title: str
    summary: str
    embedding: list[float]


class KuEdgeRow(TypedDict):
    """One directed Ku→Ku relationship (any type), as stored in the graph.

    Read by ``PrereqCandidateBackend.get_ku_ku_edges`` — candidate generation
    excludes pairs already connected by ANY authored Ku↔Ku edge (checked both
    directions) and pairs transitively covered by a directed path.
    """

    from_uid: str
    to_uid: str
    rel_type: str


def to_ku_embedding_rows(records: list[Neo4jProperties]) -> list[KuEmbeddingRow]:
    """Narrow raw Neo4j Ku rows to typed ``KuEmbeddingRow``s (malformed rows dropped)."""
    rows: list[KuEmbeddingRow] = []
    for record in records:
        uid = record.get("uid")
        embedding = record.get("embedding")
        if not isinstance(uid, str) or not isinstance(embedding, list) or not embedding:
            continue
        rows.append(
            KuEmbeddingRow(
                uid=uid,
                title=str(record.get("title") or uid),
                summary=str(record.get("summary") or ""),
                embedding=[float(v) for v in embedding],
            )
        )
    return rows


def to_ku_edge_rows(records: list[Neo4jProperties]) -> list[KuEdgeRow]:
    """Narrow raw Neo4j Ku→Ku edge rows to typed ``KuEdgeRow``s (malformed rows dropped)."""
    rows: list[KuEdgeRow] = []
    for record in records:
        from_uid = record.get("from_uid")
        to_uid = record.get("to_uid")
        if not isinstance(from_uid, str) or not isinstance(to_uid, str):
            continue
        rows.append(
            KuEdgeRow(from_uid=from_uid, to_uid=to_uid, rel_type=str(record.get("rel_type") or ""))
        )
    return rows


class GroundingEntryRow(TypedDict):
    """One knowledge-pipeline UserEntry awaiting a Ku-grounding pass.

    Read by ``EntryGroundingBackend.get_pending_entries`` — the candidate
    stage of entry→Ku grounding queries the Ku vector index with the entry's
    stored embedding. ``applied_ku_uids`` (existing APPLIES_KNOWLEDGE targets)
    and ``rejected_ku_uids`` (user-removed inferred links) are carried so the
    service never re-writes an existing edge, never re-publishes its substance
    event, and never re-infers a link the user deliberately removed.
    """

    uid: str
    user_uid: str
    title: str
    content: str
    embedding: list[float]
    embedding_text_hash: str
    applied_ku_uids: list[str]
    rejected_ku_uids: list[str]


class GroundingRemovalRow(TypedDict):
    """Provenance of one removed ``(entry)-[:APPLIES_KNOWLEDGE]->(ku)`` edge.

    Returned by ``EntryGroundingBackend.remove_grounded_edge`` so removals can
    be logged as threshold-calibration data (Mike's ruling 2026-07-11: the
    user is editor, not approver — removals teach us where the knob is wrong).
    """

    ku_uid: str
    confidence: float | None
    inferred: bool


def to_grounding_entry_rows(records: list[Neo4jProperties]) -> list[GroundingEntryRow]:
    """Narrow raw pending-entry rows to typed ``GroundingEntryRow``s (malformed rows dropped)."""
    rows: list[GroundingEntryRow] = []
    for record in records:
        uid = record.get("uid")
        user_uid = record.get("user_uid")
        embedding = record.get("embedding")
        if (
            not isinstance(uid, str)
            or not isinstance(user_uid, str)
            or not isinstance(embedding, list)
            or not embedding
        ):
            continue
        applied = record.get("applied_ku_uids")
        rejected = record.get("rejected_ku_uids")
        rows.append(
            GroundingEntryRow(
                uid=uid,
                user_uid=user_uid,
                title=str(record.get("title") or uid),
                content=str(record.get("content") or ""),
                embedding=[float(v) for v in embedding],
                embedding_text_hash=str(record.get("embedding_text_hash") or ""),
                applied_ku_uids=[str(k) for k in applied] if isinstance(applied, list) else [],
                rejected_ku_uids=[str(k) for k in rejected] if isinstance(rejected, list) else [],
            )
        )
    return rows


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


class PathStepPrediction(TypedDict, total=False):
    """
    Single prediction item for path steps.

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
        next_path_steps: List of predicted path steps
    """

    next_path_steps: list[PathStepPrediction]


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
        context_version: Context version label (semver string, e.g. "3.0")
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

    user_uid: UserUID
    context_version: str
    last_refresh: str
    time_window: str
    tasks: DashboardTasksOverview
    goals: DashboardGoalsOverview
    habits: DashboardHabitsOverview
    events: DashboardEventsOverview
    learning: DashboardLearningOverview
    capacity: DashboardCapacityInfo
    predictions: PredictionsData


class BaseStats(TypedDict):
    """Guaranteed keys every domain's stats dict MUST include.

    All ``_compute_*_stats`` functions return at least ``total`` and ``active``.
    Domain-specific keys (``overdue``, ``streaks``, ``pending``, etc.) are added
    alongside these two. Intelligence consumers can rely on ``active`` for
    generic health checks without knowing domain-specific keys.
    """

    total: int
    active: int


class ListContext(TypedDict, total=False):
    """
    Typed context returned by service.get_filtered_context() methods.

    Every domain facade (Activity + Curriculum) exposes get_filtered_context()
    which fetches, computes stats, filters, and sorts entities in one call.
    All implementations satisfy the FilteredContextProvider protocol.

    Fields:
        entities: Filtered and sorted entity list
        stats: Aggregate stats computed BEFORE filtering. Every domain includes
            at least ``total`` and ``active`` (see BaseStats). Domain-specific
            keys are added alongside these two guaranteed keys.
        metadata: Domain-specific extras (e.g., tasks' project/assignee lists for
            UI dropdowns, principle/goal/habit category lists).

    Usage:
        ctx = result.value
        render_list(ctx["entities"], ctx["stats"])

    See: core/ports/filtered_context_protocols.py
    """

    entities: list[Any]
    stats: dict[str, int | float]
    metadata: dict[str, Any]


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

    user_uid: UserUID
    generated_at: str
    top_priorities: TopPriorities
    key_metrics: KeyMetrics
    alerts: list[ContextAlert]
    insights: ContextInsights


# ============================================================================
# CONTEXT INTELLIGENCE RESULT TYPES
# ============================================================================


class NextActionResult(TypedDict, total=False):
    """Return shape for UserContextService.get_next_action().

    AI-recommended next action based on current priorities, overdue items,
    and at-risk habits.
    """

    user_uid: str
    recommended_action: TopPriorities
    insights: ContextInsights
    alerts: list[ContextAlert]
    rationale: str


class AtRiskHabitsResult(TypedDict, total=False):
    """Return shape for UserContextService.get_at_risk_habits().

    Habits at risk of breaking streaks, with streak counts and completion rates
    filtered to only the at-risk subset.
    """

    user_uid: str
    at_risk_habits: list[str]
    habit_streaks: dict[str, int]
    completion_rates: dict[str, float]
    count: int


class AdaptiveLearningPathResult(TypedDict, total=False):
    """Return shape for UserContextService.get_adaptive_learning_path().

    Personalized learning recommendations based on current context: enrolled path,
    life path alignment, ready-to-learn KUs, and mastery state.
    """

    user_uid: str
    current_path: str | None
    life_path: str | None
    life_path_alignment: float
    ready_to_learn: list[str]
    next_recommended: list[str]
    mastered_knowledge: list[str]
    mastered_count: int


class FutureContextStateResult(TypedDict, total=False):
    """Return shape for UserContextService.predict_future_context_state().

    Predicted user state based on current patterns, extracted from the dashboard
    with predictions enabled.
    """

    user_uid: str
    horizon: str
    generated_at: str
    predictions: PredictionsData
    current_state: dict[str, Any]  # boundary: nested dashboard domain slices


class ContextHealthResult(TypedDict, total=False):
    """Return shape for UserContextService.get_context_health().

    Overall context system health: composite health score, key metrics,
    alerts, insights, and generated recommendations.

    ``overall_health`` is a ``ContextHealthScore`` StrEnum (e.g. ``"good"``);
    it serializes to its string value over ``/api/context/health``.
    """

    user_uid: str
    overall_health: ContextHealthScore
    metrics: KeyMetrics
    alerts: list[ContextAlert]
    insights: ContextInsights
    recommendations: list[str]


# ============================================================================
# AUTH RESULT TYPES
# ============================================================================


class SignUpResult(TypedDict, total=False):
    """Return shape for graph_auth.sign_up()."""

    user_uid: UserUID
    email: str
    username: str
    display_name: str | None
    is_verified: bool


class SignInResult(TypedDict, total=False):
    """Return shape for graph_auth.sign_in()."""

    user_uid: UserUID
    email: str
    session_token: str
    session_uid: str
    expires_at: str  # ISO format
    user: Any  # User model (TYPE_CHECKING boundary)


# ============================================================================
# TEACHER REVIEW RESULT TYPES
# ============================================================================


class ReviewQueueItem(TypedDict, total=False):
    """Single item in teacher's review queue."""

    submission_uid: str
    title: str
    status: str
    entity_type: str
    submitted_at: str  # ISO format
    student_uid: str
    student_name: str
    exercise_uid: str
    exercise_name: str
    due_date: str | None
    original_filename: str | None
    feedback_count: int


class SubmissionDetailResult(TypedDict, total=False):
    """Full submission detail for teacher review."""

    uid: str
    title: str
    content: str
    processed_content: str
    original_filename: str
    entity_type: str
    status: str
    created_at: str  # ISO format
    student_uid: str
    student_name: str
    exercise_uid: str
    exercise_title: str
    exercise_instructions: str
    file_path: str | None


class TeacherDashboardStats(TypedDict, total=False):
    """At-a-glance stats for teacher dashboard."""

    pending_count: int
    total_students: int
    total_exercises: int
    total_groups: int


# ============================================================================
# KNOWLEDGE INTELLIGENCE RESULT TYPES
# ============================================================================


class KnowledgeSuggestionsResult(TypedDict, total=False):
    """Return shape for get_knowledge_suggestions()."""

    entity_patterns: list[dict[str, Any]]
    learning_opportunities: list[str]
    knowledge_gaps: list[str]
    metadata: dict[str, Any]


class KnowledgeGenerationResult(TypedDict, total=False):
    """Return shape for generate_knowledge_from_entities()."""

    knowledge_units: list[dict[str, Any]]
    patterns_discovered: list[str]
    documentation_suggestions: list[str]
    metadata: dict[str, Any]


class LearningOpportunitiesResult(TypedDict, total=False):
    """Return shape for get_learning_opportunities()."""

    opportunities: list[dict[str, Any]]
    recommended_focus: list[str]
    estimated_impact: dict[str, Any]
    metadata: dict[str, Any]


# ============================================================================
# DOMAIN INTELLIGENCE RESULT TYPES
# ============================================================================


class BehavioralInsightsResult(TypedDict, total=False):
    """Return shape for get_behavioral_insights()."""

    behavior_patterns: list[dict[str, Any]]
    success_factors: list[str]
    recommendations: list[str]
    metadata: dict[str, Any]


class PerformanceAnalyticsResult(TypedDict, total=False):
    """Return shape for get_performance_analytics()."""

    metrics: dict[str, Any]
    trends: dict[str, Any]
    optimization_opportunities: list[dict[str, Any]]
    learning_state: dict[str, Any]
    metadata: dict[str, Any]


# ============================================================================
# LIFE PATH RESULT TYPES
# ============================================================================


class VisionData(TypedDict, total=False):
    """Nested shape for life path vision capture."""

    statement: str
    themes: list[str]
    captured_at: str | None  # ISO format


class DesignationData(TypedDict, total=False):
    """Nested shape for life path designation."""

    life_path_uid: str | None
    designated_at: str | None  # ISO format
    vision_statement: str


class AlignmentDimensions(TypedDict):
    """Nested shape for alignment dimension scores."""

    knowledge: float
    activity: float
    goal: float
    principle: float
    momentum: float


class LpMatchResult(TypedDict):
    """LP match result from vision-based recommendation."""

    lp_uid: str
    lp_name: str
    match_score: float
    matching_themes: list[str]


class LifePathRecommendationItem(TypedDict, total=False):
    """Single life path recommendation item."""

    type: str
    priority: str
    title: str
    description: str
    action: str  # single action (getting_started, knowledge_gap, momentum, maintenance)
    actions: list[str]  # multiple actions (dimension recommendations)
    dimension: str  # present on dimension recommendations
    score: float  # present on dimension recommendations


class DailyFocusResult(TypedDict, total=False):
    """Return shape for lifepath intelligence get_daily_focus()."""

    focus: str
    reason: str
    action: str
    dimension: str | None
    current_score: float


class LifePathAlignmentResult(TypedDict, total=False):
    """Return shape for lifepath alignment calculation."""

    life_path_uid: str | None
    life_path_title: str
    alignment_score: float
    alignment_level: str
    dimensions: AlignmentDimensions
    knowledge_stats: dict[str, int]
    recommendations: list[str]
    calculated_at: str  # ISO format
    message: str  # Present when no designation exists


class LifePathStatus(TypedDict, total=False):
    """Return shape for lifepath_service.get_full_status()."""

    has_vision: bool
    has_designation: bool
    vision: VisionData | None
    designation: DesignationData | None
    alignment: LifePathAlignmentResult | None
    recommendations: list[LifePathRecommendationItem]
    daily_focus: DailyFocusResult | None
    next_step: str


class LifePathRecommendation(TypedDict, total=False):
    """Return shape for lifepath_service.capture_and_recommend()."""

    vision: VisionData
    recommendations: list[LpMatchResult]
    next_step: str


class LifePathDesignation(TypedDict, total=False):
    """Return shape for lifepath_service.designate_and_calculate()."""

    designation: DesignationData
    alignment: LifePathAlignmentResult
    recommendations: list[LifePathRecommendationItem]


# ============================================================================
# GRAPH ENTITY RESULT TYPES
# ============================================================================


class GraphInfluenceItem(TypedDict, total=False):
    """Single upstream influence or downstream impact in the reasoning graph.

    Used by GraphEntity.get_upstream_influences() and get_downstream_impacts().
    Each item represents an entity that shaped (upstream) or is shaped by
    (downstream) the current entity.
    """

    uid: str
    entity_type: str
    relationship_type: str
    reasoning: str
    strength: float
    confidence: float
    manifestation: str


class RelationshipSummaryResult(TypedDict, total=False):
    """Return shape for GraphEntity.get_relationship_summary().

    Combines explain_existence(), upstream influences, and downstream impacts
    into a complete picture of an entity's place in the reasoning graph.
    The GraphEntityBase ABC adds domain-specific metrics via _get_domain_metrics().
    """

    explanation: str
    upstream: list[GraphInfluenceItem]
    downstream: list[GraphInfluenceItem]
    upstream_count: int
    downstream_count: int
    metrics: dict[str, Any]  # boundary: domain-specific, varies per entity type


# ============================================================================
# CURRICULUM STRUCTURE RESULT TYPES
# ============================================================================


class SubstantiationBreakdownDomain(TypedDict):
    """Per-domain substantiation breakdown (tasks, events, habits, entries, choices)."""

    count: int
    progress: float
    max_score: float


class SubstantiationReviewStatus(TypedDict):
    """Review timing within SubstantiationSummaryResult."""

    needs_review: bool
    days_until_review: int | None


class SubstantiationSummaryResult(TypedDict, total=False):
    """Return shape for CurriculumOperations.get_substantiation_summary().

    Detailed breakdown of how a KU is substantiated through lived experience:
    tasks applied, events practiced, habits built, reflective entries, and choices.
    """

    substance_score: float
    breakdown: dict[str, SubstantiationBreakdownDomain]
    gaps: list[str]
    review_status: SubstantiationReviewStatus
    recommendations: list[dict[str, str]]  # boundary: {type, message, impact}
    status_message: str
    is_theoretical_only: bool
    is_well_practiced: bool


class PsKnowledgeSummaryResult(TypedDict):
    """Return shape for PathStepOperations.get_knowledge_summary().

    Aggregated count and UIDs of knowledge in a step.
    """

    count: int
    uids: list[str]


class PsPracticeSummaryResult(TypedDict):
    """Return shape for PathStepOperations.get_practice_summary().

    Counts of activity entities connected to this path step.
    """

    habits: int
    tasks: int
    events: int
    goals: int
    principles: int
    choices: int
    total: int


# ============================================================================
# PS INTELLIGENCE RESULT TYPES
# ============================================================================


class PsAnalyticsSummary(TypedDict):
    """Nested summary for PS analytics."""

    total: int
    note: str


class PsPerformanceAnalytics(TypedDict, total=False):
    """Return shape for PsIntelligenceService.get_performance_analytics()."""

    user_uid: str
    period_days: int
    total_path_steps: int
    analytics: PsAnalyticsSummary


class PsDomainInsights(TypedDict, total=False):
    """Return shape for PsIntelligenceService.get_domain_insights()."""

    ps_uid: str
    ps_title: str
    ps_intent: str | None
    practice_summary: PsPracticeSummaryResult
    practice_completeness: float
    has_prerequisites: bool
    min_confidence: float


# ============================================================================
# LP INTELLIGENCE RESULT TYPES
# ============================================================================


class LpAnalyticsSummary(TypedDict):
    """Nested summary for LP analytics."""

    total: int
    note: str


class LpPerformanceAnalytics(TypedDict, total=False):
    """Return shape for LpIntelligenceService.get_performance_analytics()."""

    user_uid: str
    period_days: int
    total_learning_paths: int
    analytics: LpAnalyticsSummary


class LpDomainInsights(TypedDict, total=False):
    """Return shape for LpIntelligenceService.get_domain_insights()."""

    lp_uid: str
    lp_title: str
    lp_domain: str | None
    total_steps: int
    min_confidence: float


class LpPathOverview(TypedDict, total=False):
    """Return shape for LpAIService.generate_path_overview()."""

    lp_uid: str
    lp_name: str
    hook: str
    target_audience: str
    key_learnings: str
    commitment: str
    success_outcome: str


class LpCompletionStrategy(TypedDict, total=False):
    """Return shape for LpAIService.suggest_completion_strategy()."""

    lp_uid: str
    lp_name: str
    recommended_pace: str
    schedule_pattern: str
    focus_tip: str
    likely_challenge: str
    mid_point_milestone: str


class LpPrerequisiteValidation(TypedDict, total=False):
    """Return shape for LpIntelligenceService.validate_path_prerequisites()."""

    path_uid: str
    is_valid: bool
    total_steps: int
    steps_with_issues: int
    issues: list[dict[str, Any]]  # boundary: raw Cypher validation records
    recommendations: list[str]
    validated_at: str


class LpBlockerAnalysis(TypedDict, total=False):
    """Return shape for LpIntelligenceService.identify_path_blockers()."""

    recommendations: list[str]
    status: str
    blocker_count: int
    analyzed_at: str
    total_steps: int
    blocked_steps: list[dict[str, Any]]  # boundary: raw Cypher blocker records
    first_blocker: dict[str, Any] | None  # boundary: raw Cypher record
    can_progress: bool


class LpPathRecommendation(TypedDict, total=False):
    """Return shape for LpIntelligenceService.get_optimal_path_recommendation()."""

    recommended_path_uid: str | None
    path_name: str
    readiness_score: float
    estimated_hours: float | None
    reason: str
    alternatives: list[dict[str, Any]]  # boundary: raw Cypher path records
    recommended_at: str


class LpRecommendedStep(TypedDict):
    """Return shape for items in LpIntelligenceService.get_recommended_path_steps()."""

    uid: str
    title: str
    domain: str | None
    confidence: float
    strength: float
    difficulty_gap: float
    semantic_distance: float
    prerequisite_readiness: float


class UserProgressResult(TypedDict, total=False):
    """Return shape for CurriculumOperations.get_user_progress().

    User's learning progress on a specific curriculum entity (KU, PS, LP).
    """

    mastery_level: float
    is_mastered: bool
    last_accessed: str | None
    time_spent: int
    attempts: int
    relationship_type: str | None
    started_at: str | None
    completed_at: str | None


# ============================================================================
# LATERAL RELATIONSHIP RESULT TYPES
# ============================================================================


class LateralRelationshipItem(TypedDict, total=False):
    """Single lateral relationship in get_lateral_relationships() result."""

    type: str
    target_uid: str
    target_title: str
    metadata: dict[str, Any]
    direction: str


class AlternativeComparisonItem(TypedDict, total=False):
    """Single alternative in get_alternatives_with_comparison() result.

    A wrapper around an entity's summary fields plus a ``comparison_data``
    payload (built from the ALTERNATIVE_TO edge properties) and a ``metadata``
    block, consumed by the comparison-grid UI. Distinct from
    ``LateralRelationshipItem`` — this is an entity-with-comparison row, not a
    raw relationship row.
    """

    uid: str
    title: str
    entity_type: str
    status: str | None
    priority: str | None
    description: str | None
    # boundary: edge-properties — comparison_data is assembled from arbitrary
    # ALTERNATIVE_TO relationship properties (timeframe/difficulty/resources plus
    # any user-defined comparison fields), and metadata holds free-form
    # tradeoffs/criteria; both are genuinely heterogeneous per edge.
    comparison_data: dict[str, Any]
    metadata: dict[str, Any]


class BlockingChainResult(TypedDict, total=False):
    """Return shape for get_blocking_chain()."""

    root_uid: str
    total_blockers: int
    chain_depth: int
    levels: list[dict[str, Any]]
    critical_path: list[str]


class RelationshipGraphData(TypedDict, total=False):
    """Vis.js network format for get_relationship_graph()."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


# ============================================================================
# ACTIVITY REPORT RESULT TYPES
# ============================================================================


class AnnotationResult(TypedDict, total=False):
    """Return shape for activity report annotate()."""

    uid: str
    annotation_mode: str
    user_annotation: str | None
    user_revision: str | None


class AnnotationState(TypedDict, total=False):
    """Return shape for activity report get_annotation()."""

    uid: str
    annotation_mode: str | None
    user_annotation: str | None
    user_revision: str | None
    annotation_updated_at: str | None  # ISO format


class PrivacySummary(TypedDict, total=False):
    """Return shape for activity report get_privacy_summary()."""

    user_uid: UserUID
    admin_snapshots: list[dict[str, Any]]
    admin_snapshot_count: int
    shares_granted: list[dict[str, Any]]
    shares_granted_count: int
    report_schedule: dict[str, Any]


# ============================================================================
# USER CONTEXT FIELD TYPES — typed shapes for UserContext dict fields
# ============================================================================


class CurrentPathStepItem(TypedDict):
    """Shape for UserContext.current_path_steps items."""

    uid: str
    title: str


class UnsubmittedExerciseItem(TypedDict):
    """Shape for UserContext.unsubmitted_exercises items."""

    uid: str
    title: str
    due_date: str | None


class PendingRevisedExerciseItem(TypedDict, total=False):
    """Shape for UserContext.pending_revised_exercises items."""

    uid: str
    title: str
    instructions: str | None
    original_exercise_uid: str | None
    report_uid: str | None
    revision_number: int
    created_at: str | None


class RichEntityItem(TypedDict, total=False):
    """Shape for items in UserContext.entities_rich lists.

    Keys: "tasks", "goals", "habits", "events", "choices", "principles"
    Inner dict[str, Any] for entity/graph_context — per-domain typing deferred.
    """

    entity: dict[str, Any]
    graph_context: dict[str, Any]


class RichKnowledgeUnitItem(TypedDict, total=False):
    """Shape for UserContext.knowledge_units_rich values."""

    ku: dict[str, Any]
    graph_context: dict[str, Any]


class RichLearningPathItem(TypedDict, total=False):
    """Shape for UserContext.enrolled_paths_rich items."""

    path: dict[str, Any]
    graph_context: dict[str, Any]


class RichPathStepItem(TypedDict, total=False):
    """Shape for UserContext.active_path_steps_rich items."""

    step: dict[str, Any]
    graph_context: dict[str, Any]


class GroupSummary(TypedDict, total=False):
    """Shape for UserContext.user_groups and teacher_groups items.

    Populated from (user)-[:MEMBER_OF]->(g:Group) and
    (user)-[:OWNS]->(g:Group) Cypher patterns.
    """

    uid: str
    name: str
    role: str  # "owner" | "student" | "teacher" | other edge role
    member_count: int
    is_active: bool


class CrossDomainInsightItem(TypedDict):
    """Single insight in UserContext.cross_domain_insights."""

    uid: str
    type: str
    title: str
    impact: str
    confidence: float


class CrossDomainInsightsData(TypedDict, total=False):
    """Shape for UserContext.cross_domain_insights."""

    active_count: int
    top_insights: list[CrossDomainInsightItem]


# ============================================================================
# INTELLIGENCE PROTOCOL RESULT TYPES — remaining untyped protocol returns
# ============================================================================


class KnowledgePrerequisiteItem(TypedDict):
    """Single prerequisite in KnowledgePrerequisitesResult."""

    uid: str
    title: str
    importance: str
    domain: str


class KnowledgePrerequisitesResult(TypedDict, total=False):
    """Return shape for get_knowledge_prerequisites()."""

    required_knowledge: list[KnowledgePrerequisiteItem]
    learning_path: list[dict[str, Any]]
    estimated_prep_time: str


class CrossDomainConnectionItem(TypedDict, total=False):
    """Single connection in CrossDomainOpportunitiesResult."""

    from_uid: str
    to_uid: str
    relationship: str
    strength: float


class CrossDomainOpportunitiesResult(TypedDict, total=False):
    """Return shape for get_cross_domain_opportunities()."""

    connections: list[CrossDomainConnectionItem]
    opportunities: list[str]
    synergies: list[str]
    metadata: dict[str, Any]


class AIInsightsResult(TypedDict, total=False):
    """Return shape for get_ai_insights(). Minimal — not yet implemented."""

    insights: list[dict[str, Any]]
    recommendations: list[str]
    confidence: float
    metadata: dict[str, Any]


# ============================================================================
# VISUALIZATION RESULT TYPES
# ============================================================================
# Return shapes for VisualizationService chart methods.
# Inner structures (options, item details) remain dict[str, Any] because
# they're consumed by Chart.js/Vis.js/Gantt JavaScript libraries.


class ChartJsDataset(TypedDict, total=False):
    """Single dataset in a Chart.js chart configuration."""

    label: str
    data: list[int] | list[float]
    backgroundColor: str | list[str]
    borderColor: str | list[str]
    borderWidth: int
    fill: bool
    tension: float


class ChartJsData(TypedDict, total=False):
    """Data section of a Chart.js chart configuration."""

    labels: list[str]
    datasets: list[ChartJsDataset]


class ChartJsConfig(TypedDict, total=False):
    """Return shape for Chart.js chart methods (format_*_chart, get_*_chart_data)."""

    type: str
    data: ChartJsData
    options: dict[str, Any]


class VisTimelineConfig(TypedDict, total=False):
    """Return shape for Vis.js timeline methods (format_for_visjs, get_timeline_data)."""

    items: list[dict[str, Any]]
    groups: list[dict[str, Any]]
    options: dict[str, Any]


class GanttConfig(TypedDict, total=False):
    """Return shape for Gantt chart methods (format_for_gantt, get_*_gantt_data)."""

    tasks: list[dict[str, Any]]
    options: dict[str, Any]


# ============================================================================
# TEACHER REVIEW RESULT TYPES
# ============================================================================
# Return shapes for TeacherReviewService methods.


class ReportSubmitResult(TypedDict, total=False):
    """Return shape for TeacherReviewService.submit_report()."""

    submission_uid: str
    status: str
    report_uid: str
    feedback_submitted: bool


class RevisionRequestResult(TypedDict, total=False):
    """Return shape for TeacherReviewService.request_revision()."""

    submission_uid: str
    status: str
    report_uid: str
    revision_requested: bool
    student_uid: str


class RevisionWithExerciseResult(TypedDict):
    """Return shape for TeacherReviewService.request_revision_with_exercise().

    Atomic operation that creates both EntryReport and RevisedExercise
    in a single Neo4j transaction.
    """

    submission_uid: str
    status: str
    report_uid: str
    revised_exercise_uid: str
    student_uid: str
    revision_number: int


class ReportApprovalResult(TypedDict, total=False):
    """Return shape for TeacherReviewService.approve_report()."""

    submission_uid: str
    status: str
    approved: bool
    mastered_ku_count: int


class ExerciseWithSubmissionCounts(TypedDict, total=False):
    """Item in TeacherReviewService.get_exercises_with_submission_counts()."""

    uid: str
    title: str
    scope: str
    created_at: str
    total_count: int
    reviewed_count: int
    pending_count: int


class SubmissionForExercise(TypedDict, total=False):
    """Item in TeacherReviewService.get_submissions_for_exercise()."""

    uid: str
    title: str
    original_filename: str
    status: str
    created_at: str
    student_uid: str
    student_name: str
    feedback_count: int


class StudentSummaryItem(TypedDict, total=False):
    """Item in TeacherReviewService.get_students_summary()."""

    student_uid: str
    student_name: str
    submission_count: int
    reviewed_count: int
    pending_count: int


class StudentSubmissionItem(TypedDict, total=False):
    """Item in TeacherReviewService.get_student_submissions()."""

    uid: str
    title: str
    original_filename: str
    status: str
    created_at: str
    feedback_count: int
    exercise_uid: str
    exercise_title: str


class TeacherGroupStats(TypedDict, total=False):
    """Item in TeacherReviewService.get_teacher_groups_with_stats()."""

    uid: str
    name: str
    description: str
    is_active: bool
    member_count: int
    exercise_count: int
    pending_count: int


class GroupMemberProgress(TypedDict, total=False):
    """Item in TeacherReviewService.get_group_detail()."""

    user_uid: str
    user_name: str
    role: str
    joined_at: str
    submission_count: int
    reviewed_count: int
    pending_count: int


class ReviewRequestResult(TypedDict, total=False):
    """Return shape for ReviewQueueService.request_review()."""

    uid: str
    status: str
    user_uid: str


class PendingReviewItem(TypedDict, total=False):
    """Item in ReviewQueueService.get_pending_reviews()."""

    uid: str
    user_uid: str
    time_period: str
    domains: list[str]
    message: str
    created_at: str
    username: str


# ============================================================================
# SUBMISSION/REPORT RESULT TYPES
# ============================================================================
# Return shapes for submission and report service methods.


class SubmissionStatistics(TypedDict, total=False):
    """Return shape for SubmissionsSearchService.get_report_statistics().

    All keys are optional — callers should treat missing keys as zero/empty.
    """

    total: int
    total_words: int
    average_words: float
    longest_streak: int
    current_streak: int
    submissions_by_day_of_week: dict[str, int]
    submissions_by_type: dict[str, int]
    # Legacy aliases retained for existing consumers that key off these names.
    by_type: dict[str, int]
    by_status: dict[str, int]


class ReportSummary(TypedDict, total=False):
    """Return shape for ReportRelationshipService.get_report_summary()."""

    total_submissions: int
    with_report: int
    without_report: int
    total_reports: int


class LearningLoopChain(TypedDict, total=False):
    """Return shape for ReportRelationshipService.get_learning_loop_chain()."""

    exercise: dict[str, Any]
    submissions: list[dict[str, Any]]
    feedback: list[dict[str, Any]]
    revised_exercises: list[dict[str, Any]]


class SubmissionChain(TypedDict, total=False):
    """Return shape for ReportRelationshipService.get_submission_chain()."""

    submission: dict[str, Any]
    exercise: dict[str, Any] | None
    feedback: list[dict[str, Any]]
    revised_exercises: list[dict[str, Any]]


# ============================================================================
# SYSTEM HEALTH RESULT TYPES
# ============================================================================
# Return shapes for SystemService health monitoring methods.


class SystemInfoResult(TypedDict, total=False):
    """Return shape for SystemService.get_system_info()."""

    service: str
    version: str
    timestamp: str
    components_registered: int


class HealthSummaryResult(TypedDict, total=False):
    """Return shape for SystemService.get_health_summary()."""

    healthy: bool
    status: str
    components_total: int
    components_healthy: int
    components_unhealthy: int
    unhealthy_components: list[str]
    timestamp: str


class AlertCheckResult(TypedDict, total=False):
    """Return shape for SystemService.check_alerts()."""

    timestamp: str
    alerts_triggered: list[dict[str, Any]]
    alert_count: int
    system_healthy: bool
    has_alerts: bool


class ComponentHealthStatus(TypedDict, total=False):
    """Health status for a single system component."""

    status: str  # "healthy" or "error"
    healthy: bool
    error: str  # Only present if status is "error"


class SystemHealthStatus(TypedDict):
    """Return shape for SystemService.get_health_status()."""

    status: str  # "healthy" or "unhealthy"
    timestamp: str  # ISO format
    components: dict[str, ComponentHealthStatus]
    healthy: bool


class HealthCheckerValidationResult(TypedDict, total=False):
    """Validation result for a single health checker."""

    valid: bool
    response_time_ms: int  # Only present if valid
    returned_type: str  # Only present if valid
    returned_value: Any  # Only present if valid
    error: str  # Only present if not valid
    error_type: str  # Only present if not valid


class HealthCheckValidation(TypedDict):
    """Return shape for SystemService.validate_health_checkers()."""

    timestamp: str  # ISO format
    total_checkers: int
    valid_checkers: int
    invalid_checkers: int
    results: dict[str, HealthCheckerValidationResult]
    all_valid: bool


# ============================================================================
# FINANCE STATS RESULT TYPES
# ============================================================================


class InvoiceStats(TypedDict, total=False):
    """Return shape for FinanceInvoiceService.get_invoice_stats()."""

    total_count: int
    outgoing_total: float
    incoming_total: float
    overdue_count: int
    outstanding_total: float


# ============================================================================
# DOMAIN STATS RESULT TYPES
# ============================================================================
# Return shapes for get_stats_for_user() across all 6 Activity Domains.
# Each backend returns a small fixed dict of int counts via Cypher COUNT.


class TaskStats(TypedDict, total=False):
    """Return shape for TasksBackend.get_stats_for_user()."""

    total: int
    completed: int
    overdue: int


class GoalStats(TypedDict, total=False):
    """Return shape for GoalsBackend.get_stats_for_user()."""

    total: int
    active: int
    completed: int


class HabitStats(TypedDict, total=False):
    """Return shape for HabitsBackend.get_stats_for_user()."""

    total: int
    active: int
    streaks: int


class EventStats(TypedDict, total=False):
    """Return shape for EventsBackend.get_stats_for_user()."""

    total: int
    scheduled: int
    today: int


class ChoiceStats(TypedDict, total=False):
    """Return shape for ChoicesBackend.get_stats_for_user()."""

    total: int
    pending: int
    decided: int


class PrincipleStats(TypedDict, total=False):
    """Return shape for PrinciplesBackend.get_stats_for_user()."""

    total: int
    core: int
    active: int


# ============================================================================
# TASK HIERARCHY RESULT TYPES
# ============================================================================


class ParentProgressResult(TypedDict, total=False):
    """Return shape for TasksBackend.calculate_parent_progress().

    Weighted subtask completion percentage for a parent task.
    """

    total_weight: float
    completed_weight: float
    progress_percentage: float
    total_subtasks: int
    completed_subtasks: int


# ============================================================================
# CURRICULUM BACKEND RESULT TYPES — PsOperations Cypher returns
# ============================================================================
# TypedDicts for stable Cypher RETURN shapes from PsBackend mixins.
# Methods that return variable-depth graph traversals or arbitrary Cypher
# remain as dict[str, Any] with # boundary: comments in the protocol.


class OrganizerResult(TypedDict):
    """Return shape for find_organizers() and get_organized_children().

    ``entity_type`` rides along because ORGANIZES is entity-agnostic — a MOC's
    children can be any of the 25 EntityTypes, and UI surfaces need the type to
    build the right detail href (``ui/patterns/entity_links.py``).
    """

    uid: str
    title: str
    order: int | None
    entity_type: str | None


class RootOrganizerResult(TypedDict):
    """Return shape for list_root_organizers()."""

    uid: str
    title: str
    child_count: int


class ReadyToLearnResult(TypedDict):
    """Return shape for find_ready_to_learn()."""

    uid: str
    title: str
    domain: str | None
    summary: str | None
    readiness: float
    total_prereqs: int
    satisfied_prereqs: int
    prereq_uids: list[str]
    dependent_count: int


class LearningGapResult(TypedDict):
    """Return shape for find_learning_gaps()."""

    uid: str
    title: str
    domain: str | None
    goals_blocked: int
    blocking_goal_uids: list[str]
    prereq_count: int
    satisfied_prereqs: int
    readiness: float


class ReinforcementCandidateResult(TypedDict):
    """Return shape for find_reinforcement_candidates()."""

    uid: str
    title: str
    domain: str | None
    goal_relevance: int
    dependent_count: int


class UserMasteryResult(TypedDict, total=False):
    """Return shape for query_user_masteries() — MASTERED relationship properties."""

    ku_uid: str
    mastery_level: str | None
    confidence_score: float | None
    mastery_score: float | None
    learning_velocity: float | None
    time_to_mastery_hours: float | None
    review_frequency_days: int | None
    mastery_evidence: str | None
    last_reviewed: str | None
    last_practiced: str | None
    learning_path_context: str | None
    difficulty_experienced: str | None
    preferred_learning_method: str | None
    created_at: str | None
    updated_at: str | None


class PrereqMasteryResult(TypedDict, total=False):
    """Return shape for query_user_mastery_for_prereqs()."""

    ku_uid: str | None
    score: float | None
    confidence: float | None
    last_practiced: str | None


class LearningRecommendationResult(TypedDict):
    """Return shape for find_learning_recommendations()."""

    uid: str
    title: str
    summary: str | None
    domain: str | None
    readiness: float
    total_prereqs: int
    satisfied_prereqs: int
    enables_count: int


class SemanticSearchChunkResult(TypedDict):
    """Return shape for semantic_search_chunks().

    `parent_uid` / `parent_title` / `parent_entity_type` refer to the owning
    Entity. Both PathStep and Ku lesson bodies are chunked (the
    `chunks_body_content` ingestion configs, #535), so `parent_entity_type` is
    `"path_step"` or `"ku"` — callers stamp it as the result `_domain` to route
    the parent card through entity_detail_href.
    """

    chunk_uid: str
    chunk_type: str
    text: str
    context_window: str | None
    similarity_score: float
    parent_uid: str
    parent_title: str
    parent_entity_type: str


class ReferenceChunkHit(TypedDict):
    """Return shape for search_reference_chunks() — the canon shelf's read side.

    Mirrors ``SemanticSearchChunkResult`` but reference-flavored: the owning node
    is always a :Resource (a shelved canon book), so the parent is surfaced as
    ``resource_uid`` / ``book_title`` rather than a generic entity. Lives on the
    walled reference index (``referencechunk_embedding_idx``), never on the
    curriculum chunk path — see ``test_reference_chunk_isolation.py``.
    """

    chunk_uid: str
    text: str
    context_window: str | None
    heading: str | None  # immediate section heading of the passage
    section_path: str | None  # ancestor-heading breadcrumb ("Part > Chapter > Section")
    sequence: int | None  # 0-based position of the chunk within the book
    similarity_score: float
    resource_uid: str
    book_title: str


class RequiredKnowledgeResult(TypedDict):
    """Return shape for ExerciseBackend.get_required_knowledge()."""

    uid: str
    title: str
    entity_type: str
    complexity: str | None
    learning_level: str | None


class CurriculumExerciseResult(TypedDict, total=False):
    """Return shape for ExerciseBackend.get_exercises_for_curriculum()."""

    uid: str
    title: str
    scope: str
    due_date: str | None
    status: str | None
    form_schema: str | None


class ExerciseStatusRow(TypedDict):
    """Return shape for ExerciseBackend/ExerciseService.get_student_exercises_with_status().

    Enriches exercise properties with the student's latest submission and report info
    so the Library Exercises tab can display submission/feedback status inline.

    ``has_in_progress`` / ``in_progress_uid`` reflect the vault living channel:
    an owned UserEntry that declares the exercise via its
    ``fulfills_exercise_uid`` intent property WITHOUT a FULFILLS_EXERCISE edge
    (frozen copies carry the edge). The newest such entry is the user's
    work-in-progress against the exercise.
    """

    uid: str
    title: str
    description: str | None
    due_date: str | None
    group_name: str
    has_submission: bool
    submission_uid: str | None
    submission_status: str | None
    has_report: bool
    report_uid: str | None
    report_outcome: str | None
    has_in_progress: bool
    in_progress_uid: str | None


class PathStepSubmissionRow(TypedDict):
    """Return shape for LearningLoopQueryService.get_submissions_for_path_step().

    A user's submissions that occurred during a specific PathStep, enriched
    with the exercise title and report status for the learning loop UI.
    """

    uid: str
    title: str | None
    status: str | None
    created_at: str | None
    exercise_uid: str | None
    exercise_title: str | None
    report_uid: str | None
    report_outcome: str | None


class RevisionChainResult(TypedDict):
    """Return shape for RevisedExerciseBackend.get_revision_chain()."""

    uid: str
    title: str
    revision_number: int
    student_uid: str
    report_uid: str | None
    status: str
    created_at: str


# ============================================================================
# PS BACKEND RESULT TYPES
# ============================================================================
# TypedDicts for stable Cypher RETURN shapes from PsBackend domain methods.


# --- Row-level result types ---


class PsStepWithKnowledgeRow(TypedDict):
    """Return shape for PsBackend.get_step_with_knowledge()."""

    s: Neo4jProperties
    knowledge_uids: list[str]


class PsDeleteStepRow(TypedDict):
    """Return shape for PsBackend.delete_step_node()."""

    deleted_count: int


class PsStandaloneStepRow(TypedDict):
    """Return shape for PsBackend.get_standalone_steps()."""

    ps: Neo4jProperties


# ============================================================================
# LATERAL RELATIONSHIP BACKEND RESULT TYPES
# ============================================================================
# TypedDicts for stable Cypher RETURN shapes from LateralRelationshipBackend.


class LateralRelationshipRow(TypedDict, total=False):
    """Return shape for LateralRelationshipBackend.get_relationships()."""

    relationship_type: str
    related_uid: str
    related_title: str
    metadata: dict[str, Any]
    direction: str


class SiblingRow(TypedDict):
    """Return shape for LateralRelationshipBackend.get_siblings()."""

    sibling_uid: str
    sibling_title: str
    hierarchy_type: str
    order: int | None


class CousinRow(TypedDict):
    """Return shape for LateralRelationshipBackend.get_cousins()."""

    cousin_uid: str
    cousin_title: str
    shared_ancestor_uid: str
    shared_ancestor_title: str


class BlockingChainRow(TypedDict):
    """Return shape for LateralRelationshipBackend.get_blocking_chain()."""

    uid: str
    title: str
    status: str | None
    entity_type: str
    depth: int
    blocks_count: int


class RelationshipGraphRow(TypedDict, total=False):
    """Return shape for LateralRelationshipBackend.get_relationship_graph()."""

    center_uid: str
    center_title: str
    center_type: str
    center_status: str | None
    related_uid: str
    related_title: str
    related_type: str
    related_status: str | None
    relationships: list[dict[str, Any]]
    depth_level: int


# ============================================================================
# JOURNAL RESULT TYPES
# ============================================================================


class CleanupStats(TypedDict):
    """Result of file cleanup operations (e.g., UserEntry date range cleanup)."""

    files_deleted: int
    bytes_freed: int


# ============================================================================
# PS AI SERVICE RESULT TYPES
# ============================================================================


class StepApplicationsResult(TypedDict):
    """Return shape for PsAIService.suggest_step_applications()."""

    ps_uid: str
    ps_title: str
    tasks: list[str]
    habits: list[str]
    goals: list[str]
    real_world_examples: list[str]


class StepLearningSequenceItem(TypedDict):
    """A single step in a learning sequence (prerequisite or next step)."""

    title: str
    reason: str


class StepLearningSequenceResult(TypedDict):
    """Return shape for PsAIService.suggest_learning_sequence()."""

    ps_uid: str
    ps_title: str
    prerequisites: list[StepLearningSequenceItem]
    next_steps: list[StepLearningSequenceItem]


# ============================================================================
# KU INTELLIGENCE RESULT TYPES
# ============================================================================


class KuUserSubstanceResult(TypedDict):
    """Return shape for KuIntelligenceService.calculate_user_substance().

    Measures how much a specific user has applied a Ku's knowledge in their life,
    per the Knowledge Substance Philosophy.

    See: /docs/architecture/knowledge_substance_philosophy.md
    """

    user_substance_score: float
    global_substance_score: float | None
    breakdown: dict[str, float]
    mastery_level: str
    is_ready_to_learn: bool
    recommendations: list[str]
    status_message: str


# ============================================================================
# PS TEMPLATE VALIDATION TYPES
# ============================================================================


class Violation(TypedDict):
    """One referential-integrity violation found during PS-save validation.

    A PathStep author may leave cross-template references unresolved during
    free-order authoring. On save, each broken reference produces one
    Violation pinpointing the offending template, field, and reason.

    Collected into a list and packed into ``ErrorContext.details["violations"]``
    via ``Errors.ps_validation_report()`` — see ``core/utils/result_simplified.py``.
    """

    template_uid: str
    template_title: str  # human-readable, for error display (NOT the uid)
    template_type: Literal[
        "TaskTemplate",
        "GoalTemplate",
        "HabitTemplate",
        "EventTemplate",
        "ChoiceTemplate",
        "PrincipleTemplate",
    ]
    field: str  # offending reference field, e.g. "fulfills_goal_template_uid"
    violation: Literal[
        "target_missing",  # references a template uid not on this PS
        "wrong_type",  # references the wrong template type for this field
        "cycle",  # would form a reference cycle
        "cross_ps",  # references a template on a different PS
        "self_reference",  # references its own uid
        "not_active",  # template status is not ACTIVE (DRAFT or ARCHIVED)
    ]
    referenced_uid: str | None  # the bad reference value, if any
    hint: str | None  # closest fuzzy-matched candidate, if any


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
    # Update Payloads - Curriculum Domains
    # (Activity Domains use frozen `*UpdateIntent` dataclasses — ADR-066 Phase 7)
    "KuUpdatePayload",
    "PsUpdatePayload",
    "LpUpdatePayload",
    # Update Payloads - Other Domains
    "FinanceUpdatePayload",
    "ReportUpdatePayload",
    # Query Building Types
    "WhereClauseSpec",
    "OrderBySpec",
    "PaginationSpec",
    # Response/Context Types
    "CapacityWarnings",
    "GraphContextResult",
    "OverdueTasksWarning",
    "WorkloadWarning",
    "ProgressResult",
    "IntelligenceResult",
    "ListContext",
    # User Context Service Response Types - Nested Structures
    "DashboardTasksOverview",
    "DashboardGoalsOverview",
    "DashboardHabitsOverview",
    "DashboardEventsOverview",
    "DashboardLearningOverview",
    "DashboardCapacityInfo",
    "PathStepPrediction",
    "PredictionsData",
    # User Context Service Response Types - Summary Structures
    "ContextAlert",
    "TopPriorities",
    "KeyMetrics",
    "ContextInsights",
    # User Context Service Response Types - Main Response Types
    "ContextDashboard",
    "ContextSummary",
    # Auth Result Types
    "SignUpResult",
    "SignInResult",
    # Teacher Review Result Types
    "ReviewQueueItem",
    "SubmissionDetailResult",
    "TeacherDashboardStats",
    # Knowledge Intelligence Result Types
    "KnowledgeSuggestionsResult",
    "KnowledgeGenerationResult",
    "LearningOpportunitiesResult",
    # Domain Intelligence Result Types
    "BehavioralInsightsResult",
    "PerformanceAnalyticsResult",
    # Life Path Result Types
    "LpMatchResult",
    "LifePathRecommendationItem",
    "DailyFocusResult",
    "LifePathAlignmentResult",
    "LifePathStatus",
    "LifePathRecommendation",
    "LifePathDesignation",
    # Lateral Relationship Result Types
    "LateralRelationshipItem",
    "BlockingChainResult",
    "RelationshipGraphData",
    # Activity Report Result Types
    "AnnotationResult",
    "AnnotationState",
    "PrivacySummary",
    # User Context Field Types
    "UnsubmittedExerciseItem",
    "PendingRevisedExerciseItem",
    "RichEntityItem",
    "RichKnowledgeUnitItem",
    "RichLearningPathItem",
    "RichPathStepItem",
    "GroupSummary",
    "CrossDomainInsightItem",
    "CrossDomainInsightsData",
    # Intelligence Protocol Result Types
    "KnowledgePrerequisiteItem",
    "KnowledgePrerequisitesResult",
    "CrossDomainConnectionItem",
    "CrossDomainOpportunitiesResult",
    "AIInsightsResult",
    # Visualization Result Types
    "ChartJsDataset",
    "ChartJsData",
    "ChartJsConfig",
    "VisTimelineConfig",
    "GanttConfig",
    # Teacher Review Result Types
    "ReportSubmitResult",
    "RevisionRequestResult",
    "ReportApprovalResult",
    "ExerciseWithSubmissionCounts",
    "SubmissionForExercise",
    "StudentSummaryItem",
    "StudentSubmissionItem",
    "TeacherGroupStats",
    # Submission/Report Result Types
    "SubmissionStatistics",
    "ReportSummary",
    "LearningLoopChain",
    "SubmissionChain",
    # System Health Result Types
    "SystemInfoResult",
    "HealthSummaryResult",
    "AlertCheckResult",
    "ComponentHealthStatus",
    "SystemHealthStatus",
    "HealthCheckerValidationResult",
    "HealthCheckValidation",
    # Finance Stats Result Types
    "InvoiceStats",
    # Domain Stats Result Types
    "TaskStats",
    "GoalStats",
    "HabitStats",
    "EventStats",
    "ChoiceStats",
    "PrincipleStats",
    # Task Hierarchy Result Types
    "ParentProgressResult",
    # Curriculum Backend Result Types
    "OrganizerResult",
    "RootOrganizerResult",
    "ReadyToLearnResult",
    "LearningGapResult",
    "ReinforcementCandidateResult",
    "UserMasteryResult",
    "PrereqMasteryResult",
    "LearningRecommendationResult",
    "SemanticSearchChunkResult",
    "ReferenceChunkHit",
    "RequiredKnowledgeResult",
    "CurriculumExerciseResult",
    "RevisionChainResult",
    # PS Backend Result Types
    "PsStepWithKnowledgeRow",
    "PsDeleteStepRow",
    "PsStandaloneStepRow",
    # PS Intelligence Result Types
    "PsAnalyticsSummary",
    "PsPerformanceAnalytics",
    "PsDomainInsights",
    # LP Intelligence Result Types
    "LpAnalyticsSummary",
    "LpPerformanceAnalytics",
    "LpDomainInsights",
    "LpPathOverview",
    "LpCompletionStrategy",
    "LpPrerequisiteValidation",
    "LpBlockerAnalysis",
    "LpPathRecommendation",
    "LpRecommendedStep",
    # Life Path Nested Types
    "VisionData",
    "DesignationData",
    "AlignmentDimensions",
    # Lateral Relationship Backend Result Types
    "LateralRelationshipRow",
    "SiblingRow",
    "CousinRow",
    "BlockingChainRow",
    "RelationshipGraphRow",
    # Journal Result Types
    "CleanupStats",
    # PS AI Service Result Types
    "StepApplicationsResult",
    "StepLearningSequenceItem",
    "StepLearningSequenceResult",
    # Ku Intelligence Result Types
    "KuUserSubstanceResult",
    # PS Template Validation Types
    "Violation",
]
