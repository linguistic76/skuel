---
title: Unified User Architecture - ProfileHubData + UnifiedUserContext Integration
updated: 2026-01-20
status: current
category: architecture
tags:
- architecture
- unified
- user
- mega-query
related:
- ADR-015
- ADR-029
related_skills:
- user-context-intelligence
---

# Unified User Architecture - ProfileHubData + UnifiedUserContext Integration
**Last Updated:** January 20, 2026
**Status:** ✅ Complete - MEGA-QUERY Rich Queries + Profile Hub Intelligence Integration + Field Mapping
**One Path Forward:** UserContext for cached analysis, Services for fresh queries (ADR-029)
## Related Skills

For implementation guidance, see:
- [@user-context-intelligence](../../.claude/skills/user-context-intelligence/SKILL.md)


## 🎯 Core Principle: Single Source of Truth

**UnifiedUserContext** is THE authoritative source for all user state.
**ProfileHubData** is a computed, serializable view built FROM that context.

```
UnifiedUserContext (THE source of truth)
    ↓ Contains:
    - active_task_uids: ['task_1', 'task_2']
    - tasks_by_goal: {'goal_1': ['task_1']}
    - habit_streaks: {'habit_1': 7}
    - knowledge_mastery: {'ku_1': 0.85}
    ↓
ProfileHubData.from_context(context)
    ↓ Computes:
    - domain_stats: DomainStatsAggregate (stats computed from UIDs)
    - overall_metrics: OverallMetrics (computed from context)
    ↓ Includes:
    - context: UnifiedUserContext (full rich access)
```

## 🎯 One Path Forward: Context vs Services (ADR-029)

**January 8, 2026:** GraphNativeMixin removed (366 lines) - eliminated third path for context queries.

**Clear Decision Tree:**
```
Need user state data?
├─ Cached analysis (snapshot) → context.get_ready_to_learn() (8 lines)
│  └─ Use: Intelligence services analyzing user state
│  └─ Example: Daily planning, recommendations, alignment scoring
│
├─ Fresh queries (real-time) → ku_service.get_ready_to_learn_for_user(user_uid)
│  └─ Use: Direct API endpoints, real-time dashboards
│  └─ Example: /api/ku/ready-to-learn
│
└─ Relationship data → service.relationships.get_related_uids()
   └─ Use: Cross-domain context, graph traversal
   └─ Example: Task dependencies, goal knowledge gaps
```

**Deleted Paths (ADR-029):**
- ❌ `GraphNativeMixin.get_next_logical_steps()` - 78 lines, NEVER used
- ❌ `GraphNativeMixin.get_ready_to_learn()` - Duplicated context method
- ❌ `GraphNativeMixin.get_goal_aligned_knowledge()` - 90 lines, NEVER used
- ❌ `GraphNativeMixin.get_knowledge_gaps()` - 70 lines, NEVER used

**Result:** Two clear paths remain:
1. **Context methods** - Simple, cached, 8-line implementations used everywhere
2. **Service methods** - Fresh Cypher queries when real-time data needed

**Philosophy:**
- UserContext provides **cached snapshot** for intelligence analysis
- Services provide **fresh queries** for real-time API responses
- No intermediate layers creating alternative paths

**See:** [ADR-029](../decisions/ADR-029-graphnative-service-removal.md) for complete removal rationale.

## 🏗️ Architecture Layers

### Layer 1: UnifiedUserContext - The Rich Domain Model

**Location:** `/core/services/user/unified_user_context.py`

**Purpose:** Complete domain awareness with UIDs, relationships, and intelligence methods.

```python
@dataclass
class UnifiedUserContext:
    """
    The master context providing complete awareness of user state.
    This is THE integration point for understanding users.
    """
    # Core Identity
    user_uid: str
    username: str
    email: str

    # Task Awareness (UIDs + relationships)
    active_task_uids: list[str]
    overdue_task_uids: list[str]
    tasks_by_goal: dict[str, list[str]]
    task_priorities: dict[str, float]

    # Habit Awareness
    habit_streaks: dict[str, int]
    habit_completion_rates: dict[str, float]
    at_risk_habits: list[str]

    # Goal Awareness
    active_goal_uids: list[str]
    goal_progress: dict[str, float]
    completed_goal_uids: set[str]

    # Knowledge/Learning Awareness
    knowledge_mastery: dict[str, float]
    mastered_knowledge_uids: set[str]
    enrolled_path_uids: list[str]

    # ... complete domain awareness

    # Intelligence Methods
    def get_tasks_for_goal(self, goal_uid: str) -> list[str]: ...
    def get_ready_to_learn(self) -> list[str]: ...
    def calculate_life_alignment(self) -> float: ...
    def calculate_current_workload(self) -> float: ...
```

**Key Features:**
- ✅ Contains actual UIDs (not just counts)
- ✅ Tracks relationships (tasks_by_goal, habits_by_goal)
- ✅ Rich intelligence methods
- ✅ Supports cascade updates
- ✅ Mutable (can be updated as user works)

### Layer 2: ProfileHubData - The Computed Statistical View

**Location:** `/core/services/user_stats_types.py`

**Purpose:** Frozen, serializable view with computed statistics for API responses.

```python
@dataclass(frozen=True)
class ProfileHubData:
    """
    Complete profile hub data with type safety.

    Pattern 3C + UnifiedUserContext Integration:
    - Built FROM UnifiedUserContext (single source of truth)
    - ProfileHubData is a computed, serializable view
    - Includes full context for rich domain awareness
    """
    user: Any
    context: UnifiedUserContext  # ← THE source of truth
    domain_stats: DomainStatsAggregate  # ← Computed from context
    overall_metrics: OverallMetrics  # ← Computed from context
    recent_activities: list[dict[str, Any]]
    recommendations: list[dict[str, str]]
    aggregated_at: str

    @staticmethod
    def from_context(
        user: Any,
        context: UnifiedUserContext,
        recent_activities: list[dict],
        recommendations: list[dict]
    ) -> 'ProfileHubData':
        """Build ProfileHubData FROM UnifiedUserContext."""
        # Compute stats from context UIDs
        domain_stats = _compute_domain_stats_from_context(context)
        overall_metrics = _compute_overall_metrics_from_context(context)

        return ProfileHubData(
            user=user,
            context=context,  # Include full context
            domain_stats=domain_stats,
            overall_metrics=overall_metrics,
            recent_activities=recent_activities,
            recommendations=recommendations,
            aggregated_at=datetime.now(UTC).isoformat()
        )
```

**Key Features:**
- ✅ Frozen dataclass (immutable, Pattern 3C)
- ✅ Stats computed from context (no duplicate queries)
- ✅ Includes full context for rich access
- ✅ Serializable for API responses
- ✅ Type-safe all the way through

### Layer 3: Domain Stats - Statistical Aggregates

**Location:** `/core/services/user_stats_types.py`

**Purpose:** Strongly-typed statistical views computed from context.

```python
@dataclass(frozen=True)
class TasksStats:
    """Task statistics computed from UnifiedUserContext."""
    total_active: int  # = len(context.active_task_uids)
    completed_today: int  # = count(context.today_task_uids & completed)
    overdue: int  # = len(context.overdue_task_uids)
    completion_rate: float  # = calculated from context

@dataclass(frozen=True)
class DomainStatsAggregate:
    """All domain statistics aggregated."""
    tasks: TasksStats
    habits: HabitsStats
    goals: GoalsStats
    learning: LearningStats
    # ... all domains
```

**Computation Pattern:**
```python
def _compute_domain_stats_from_context(
    context: UnifiedUserContext
) -> DomainStatsAggregate:
    """
    Compute all statistics from UnifiedUserContext.
    Single source of truth - no duplicate queries.
    """
    tasks_stats = TasksStats(
        total_active=len(context.active_task_uids),
        completed_today=sum(1 for uid in context.today_task_uids
                           if uid in context.completed_task_uids),
        overdue=len(context.overdue_task_uids),
        completion_rate=_calculate_completion_rate(context)
    )
    # ... compute all stats from context

    return DomainStatsAggregate(tasks=tasks_stats, ...)
```

## 🔄 Data Flow - The Complete Picture

### Building the Profile Hub

**Location:** `/core/services/user_service.py`
**Method:** `get_profile_hub_data()`

```python
async def get_profile_hub_data(self, user_uid: str) -> Result[ProfileHubData]:
    """
    Pattern 3C + UnifiedUserContext Integration.

    Flow:
    1. Build UnifiedUserContext (THE source of truth)
    2. Compute ProfileHubData FROM context
    3. Return strongly-typed, frozen result
    """
    # 1. Build UnifiedUserContext from domain queries
    context = await self._build_user_context(user_uid, user)

    # 2. Get additional data not yet in context
    recent_activities = await self._get_recent_activities(user_uid)

    # 3. Generate UID-aware recommendations FROM context
    recommendations = self._generate_recommendations_from_context(context)

    # 4. Build ProfileHubData FROM context (stats auto-computed)
    hub_data = ProfileHubData.from_context(
        user=user,
        context=context,  # ← Full rich context included
        recent_activities=recent_activities,
        recommendations=recommendations
    )

    return Result.ok(hub_data)
```

### Building UnifiedUserContext

**Architecture (January 2026):** Context building decomposed into 4 focused modules for Standard vs Rich context.

#### 4-Module Decomposition

```
core/services/user/
├── user_context_builder.py      (~331 lines) - Orchestration (build() vs build_rich())
├── user_context_queries.py      (~1,000 lines) - MEGA-QUERY for rich context
├── user_context_extractor.py    (~351 lines) - Result parsing + relationship extraction
└── user_context_populator.py    (~235 lines) - Context field population
```

#### Context Depth: Standard vs Rich

| Depth | Method | Query | Fields | Use Case |
|-------|--------|-------|--------|----------|
| **Standard** | `build()` | Lightweight queries | UIDs only (~150) | API responses, ownership checks |
| **Rich** | `build_rich()` | MEGA-QUERY | UIDs + entities + graph (~240) | Intelligence operations |

**Standard Context:**
- Contains entity UIDs only (e.g., `active_task_uids: list[str]`)
- Fast to build (~50-100ms)
- Sufficient for: API responses, simple queries, ownership verification
- NOT sufficient for: Intelligence operations, recommendations, planning

**Rich Context:**
- Contains UIDs + full entities + graph neighborhoods
- Slower to build (~200-500ms) due to MEGA-QUERY
- Includes: Full Task/Goal/Habit entities, prerequisites, dependencies, substance scores
- Required for: All intelligence operations, UserContextIntelligence flagship methods

**Runtime Validation:**
```python
# File: /core/services/user/unified_user_context.py

class UserContext:
    def require_rich_context(self, operation: str) -> None:
        """
        Validate that context has rich data for intelligence operations.

        Raises:
            ValueError: If context is standard (UIDs only)
        """
        if not self.tasks:  # Rich context has full Task entities
            raise ValueError(
                f"Operation '{operation}' requires rich context. "
                f"Use UserContextBuilder.build_rich() instead of build()."
            )

# Used by intelligence services:
async def get_ready_to_work_on_today(self) -> Result[DailyWorkPlan]:
    """THE FLAGSHIP - requires rich context."""
    self.context.require_rich_context("get_ready_to_work_on_today")
    # Proceed with full entities available
```

#### UserContextBuilder Orchestration

**UserContextBuilder** orchestrates the flow:

```python
class UserContextBuilder:
    """Orchestrate context building from queries → extraction → population."""

    def __init__(self, driver: Any, user_service: "UserService | None" = None):
        self._query_executor = UserContextQueryExecutor(driver)
        self._extractor = UserContextExtractor()
        self._populator = UserContextPopulator()

    # Primary API (preferred - builder owns user resolution)
    async def build(self, user_uid: str) -> Result[UserContext]: ...
    async def build_rich(self, user_uid: str) -> Result[UserContext]: ...

    # Full API (backward compatibility)
    async def build_user_context(self, user_uid: str, user: User) -> Result[UserContext]: ...
    async def build_rich_user_context(self, user_uid: str, user: User) -> Result[UserContext]: ...
```

### Context Depth: Standard vs Rich

SKUEL builds two context depths for different use cases:

| Depth | Methods | What's Populated | Use Cases |
|-------|---------|------------------|-----------|
| **Standard** | `build()`, `build_user_context()` | UIDs only (~150 fields) | API responses, lightweight checks |
| **Rich** | `build_rich()`, `build_rich_user_context()` | UIDs + full entities + graph neighborhoods (~240 fields) | Intelligence, planning, dashboards |

**Rich Context Marker:**

UserContext has an `is_rich_context: bool` field that indicates which path was used:

```python
# Standard context - is_rich_context = False (default)
context = await builder.build(user_uid)
assert context.is_rich_context is False  # Only UIDs populated

# Rich context - is_rich_context = True
context = await builder.build_rich(user_uid)
assert context.is_rich_context is True  # Full entities + graph data
```

**Fail-Fast Validation for Rich-Required Operations:**

Methods requiring rich context should validate early:

```python
def get_advancing_goals_for_user(self, context: UserContext) -> Result[...]:
    context.require_rich_context("get_advancing_goals_for_user")
    # Now safe to access context.active_goals_rich
```

**Query Execution** (`user_context_queries.py`):

```python
class UserContextQueryExecutor:
    """Execute MEGA-QUERY and CONSOLIDATED-QUERY."""

    async def execute_mega_query(self, user_uid: str, min_confidence: float) -> Result[dict]:
        """Single query fetches UIDs AND rich data with graph neighborhoods."""

    async def execute_consolidated_query(self, user_uid: str) -> Result[dict]:
        """Optimized query for standard context (UIDs only)."""
```

**Data Extraction** (`user_context_extractor.py`):

```python
@dataclass
class GraphSourcedData:
    """Complete relationship data extracted from MEGA-QUERY."""
    tasks: TaskRelationshipData      # dependencies, blockers, knowledge_applied
    goals: GoalRelationshipData      # knowledge_required/mastered, supporting_tasks
    habits: HabitRelationshipData    # knowledge_applied, prerequisites
    knowledge: KnowledgeRelationshipData  # prerequisite_counts, ready_to_learn

class UserContextExtractor:
    """Extract relationship data from MEGA-QUERY rich results."""
    def extract_graph_sourced_data(self, mega_data: dict, mastered_uids: set) -> GraphSourcedData: ...
```

**Context Population** (`user_context_populator.py`):

```python
class UserContextPopulator:
    """Populate UserContext fields from query results."""
    # Core population methods
    def populate_standard_fields(self, context: UserContext, uids_data: dict) -> None: ...
    def populate_rich_fields(self, context: UserContext, rich_data: dict) -> None: ...
    def populate_graph_sourced_fields(self, context: UserContext, graph_data: GraphSourcedData) -> None: ...

    # Extended population methods (January 2026)
    def populate_user_properties(self, context: UserContext, user_props: dict) -> None: ...
    def populate_life_path(self, context: UserContext, life_path_data: dict) -> None: ...
    def populate_moc_fields(self, context: UserContext, uids_data: dict) -> None: ...
    def populate_progress_metrics(self, context: UserContext, progress_counts: dict) -> None: ...
    def populate_derived_fields(self, context: UserContext, tasks_rich: list, habits_rich: list) -> None: ...
    def populate_principle_choice_integration(self, context: UserContext, principles_rich: list, choices_rich: list) -> None: ...
```

## 💡 Key Design Benefits

### 1. Single Source of Truth

**Before (Disconnected):**
```python
# Separate queries for stats
tasks_stats = await query_tasks_stats(user_uid)  # Count query
habits_stats = await query_habits_stats(user_uid)  # Count query

# Separate queries for UIDs
context.active_task_uids = await query_task_uids(user_uid)  # UID query
context.habit_streaks = await query_habit_streaks(user_uid)  # UID query

# Duplication: Two queries for same data!
```

**After (Unified):**
```python
# One query for UIDs
context = await build_user_context(user_uid)

# Stats computed from UIDs
domain_stats = _compute_domain_stats_from_context(context)
# domain_stats.tasks.total_active = len(context.active_task_uids)

# No duplication!
```

### 2. Rich + Statistical Access

**API consumers get BOTH:**
```python
hub_data = await get_profile_hub_data(user_uid)

# Statistical view
total_active = hub_data.domain_stats.tasks.total_active  # 5

# Rich UID access
task_uids = hub_data.context.active_task_uids  # ['task_1', 'task_2', ...]

# Relationship awareness
goal_tasks = hub_data.context.tasks_by_goal['goal_1']  # ['task_1', 'task_3']

# Intelligence methods
ready_to_learn = hub_data.context.get_ready_to_learn()  # ['ku_5', 'ku_7']
```

### 3. UID-Aware Recommendations

**Before (Count-based):**
```python
if domain_stats.tasks.overdue > 3:
    return "You have 3 overdue tasks"  # Not actionable
```

**After (UID-aware):**
```python
if len(context.overdue_task_uids) > 3:
    # Can provide actual links and priorities
    return [
        {
            'type': 'tasks',
            'uids': context.overdue_task_uids[:3],  # Actual UIDs!
            'message': 'Focus on task_abc (blocks goal_xyz), task_def (urgent)'
        }
    ]
```

### 4. Type Safety All The Way

**Pattern 3C Achievement:**
```python
# Public API return type
async def get_profile_hub_data() -> Result[ProfileHubData]:  # ← Frozen dataclass

# ProfileHubData contains
class ProfileHubData:
    context: UnifiedUserContext  # ← Dataclass with methods
    domain_stats: DomainStatsAggregate  # ← Frozen dataclass
    overall_metrics: OverallMetrics  # ← Frozen dataclass

# All strongly typed, no dict[str, Any] anywhere!
```

## 🎯 Usage Patterns

### For API Responses (Statistical View)

```python
@rt('/api/user/profile')
@boundary_handler()
async def get_profile(user_uid: str):
    result = await user_service.get_profile_hub_data(user_uid)
    hub_data = result.value

    # Return serializable stats
    return {
        'stats': {
            'tasks': {
                'total_active': hub_data.domain_stats.tasks.total_active,
                'overdue': hub_data.domain_stats.tasks.overdue,
            },
            'habits': {
                'current_streak': hub_data.domain_stats.habits.current_streak,
            }
        },
        'overall': {
            'activity_score': hub_data.overall_metrics.activity_score,
        }
    }
```

### For AI Intelligence (Rich Context)

```python
async def get_ai_recommendations(user_uid: str):
    result = await user_service.get_profile_hub_data(user_uid)
    hub_data = result.value
    context = hub_data.context  # Full rich context

    # AI can use rich context for deep analysis
    recommendations = []

    # Check if user is blocked
    if context.is_blocked:
        blocked_tasks = context.get_blocked_tasks()  # Actual UIDs
        recommendations.append({
            'priority': 'high',
            'action': 'unblock',
            'task_uids': blocked_tasks,
            'reason': 'Complete prerequisites first'
        })

    # Check life path alignment
    alignment = context.calculate_life_alignment(life_path_knowledge_uids)
    if alignment < 0.7:
        gaps = context.get_life_path_gaps()  # KU UIDs needing practice
        recommendations.append({
            'priority': 'medium',
            'action': 'practice',
            'ku_uids': gaps,
            'reason': f'Life path alignment is {alignment:.0%} - focus on application'
        })

    return recommendations
```

### For Dashboard (Both Views)

```python
async def build_dashboard(user_uid: str):
    result = await user_service.get_profile_hub_data(user_uid)
    hub_data = result.value

    return {
        # Statistical widgets
        'overview': {
            'total_active_items': hub_data.overall_metrics.total_active_items,
            'activity_score': hub_data.overall_metrics.activity_score,
        },

        # Rich UID-based widgets
        'today_focus': {
            'task_uids': hub_data.context.get_tasks_for_today(),  # Clickable links
            'at_risk_habits': hub_data.context.get_habits_needing_reinforcement(),
        },

        # Intelligent recommendations
        'next_action': hub_data.context.get_recommended_next_action(),
    }
```

## 🧘‍♂️ Philosophical Alignment

This architecture embodies core SKUEL principles:

### "Deal with fundamentals"
- UnifiedUserContext is the fundamental truth
- ProfileHubData is a derived view
- No workarounds or hidden conversions

### "Everything flows toward the life path"
- `context.calculate_life_alignment()` measures lifestyle integration
- `context.get_life_path_gaps()` identifies areas needing practice
- Life path UID tracking enables deep analysis

### "Pydantic at edges, pure Python at core"
- UnifiedUserContext: Pure Python dataclass (core)
- ProfileHubData: Frozen dataclass (edge, serializable)
- Clean boundary separation

### "Type safety all the way"
- No `dict[str, Any]` in public APIs
- Frozen dataclasses everywhere
- Compile-time guarantees

## 📊 Performance Characteristics

### Query Efficiency

**Before (Disconnected):**
- 9 domain stat queries (one per domain)
- Separate UID queries if needed
- **Total: ~18 queries for full profile**

**After (Unified):**
- 5 enrichment queries (tasks, habits, goals, learning, events)
- Stats computed in-memory from UIDs
- **Total: 5 queries for full profile**
- **60% reduction in database queries**

### Caching Strategy

```python
class UserContextCache:
    """Cache for UnifiedUserContext (5-minute TTL)"""

    def get(self, user_uid: str) -> UnifiedUserContext | None:
        context = self._cache.get(user_uid)
        if context and context.is_cached_valid():
            return context
        return None
```

**Cache Hit Flow:**
```
Request → Cache → UnifiedUserContext (cached)
                → ProfileHubData.from_context() (in-memory compute)
                → Response
```

**Performance:**
- Cache hit: ~2ms (in-memory computation only)
- Cache miss: ~50ms (5 DB queries + computation)
- Cache TTL: 5 minutes (configurable)

## ✅ Implementation Checklist

- ✅ **UnifiedUserContext** defined with all domain awareness
- ✅ **ProfileHubData** with `context` field and `from_context()` factory
- ✅ **Computation functions** in `user_stats_types.py`
- ✅ **UserService** refactored to build context first
- ✅ **Tests** updated for context + stats verification
- ✅ **Type safety** enforced (no dict[str, Any])
- ✅ **Documentation** created (this file)

## 🔥 MEGA-QUERY: Rich Context with Graph Neighborhoods
*Added: December 2025 | Updated: January 2026*

### The Rich Query Pattern

The MEGA-QUERY in `user_context_queries.py` fetches **BOTH UIDs and full entity data + graph neighborhoods** in a single database round-trip (~1,000 lines).

**Location:** `/core/services/user/user_context_queries.py` (MEGA_QUERY constant)

**Two-Tier Data Return:**
```python
{
    # Tier 1: UIDs (for standard context)
    uids: {
        active_task_uids: ["task_1", "task_2"],
        active_goal_uids: ["goal_1", "goal_2"],
        habit_streaks: {"habit_1": 7},
        # ... all ~150 UID fields
    },

    # Tier 2: Rich entities with graph (for rich context)
    rich: {
        active_tasks_rich: [{
            task: properties(task),      # Full Task entity
            graph_context: {              # Graph neighborhoods
                related_goals: [{uid, title, status}],
                applied_knowledge: [{uid, title}],
                prerequisites: [...],
                blockers: [...]
            }
        }],
        # ... all rich entity fields with graph context
    },

    # Additional sections
    user_properties: {...},
    life_path: {...},
    progress_counts: {...}
}
```

### Rich Query Status (All Complete as of December 2025)

| Domain | UID Collection | Rich Query | Graph Neighborhoods |
|--------|----------------|------------|---------------------|
| Tasks | ✅ | ✅ | subtasks, dependencies, knowledge, goals |
| Goals | ✅ | ✅ | tasks, subgoals, knowledge, milestones |
| Habits | ✅ | ✅ | goals, knowledge, prerequisites |
| Knowledge | ✅ | ✅ | prerequisites, dependents |
| Learning Paths | ✅ | ✅ | steps, knowledge, goals, principles |
| Learning Steps | ✅ | ✅ | prereqs, habits, tasks, knowledge |
| **Events** | ✅ | ✅ | knowledge, goals, habits, conflicts |
| **Principles** | ✅ | ✅ | knowledge, goals, choices, habits, tasks |
| **Choices** | ✅ | ✅ | knowledge, principles, goals, paths, tasks |

### Design Decisions

1. **LIMIT clauses** - Relationship results limited to 10 per type for performance
2. **Choices filtered by status** - Only 'pending' or 'active' choices (not completed/archived)
3. **Single round-trip** - All data fetched in ONE Cypher query (MEGA_QUERY in user_context_queries.py)

### Performance

```
Single MEGA-QUERY: 150-200ms (1K nodes)
vs
Multiple queries: 450-750ms (15-18 queries)
= 60% latency reduction
```

### Rich Fields in UserContext

```python
# Full entity + graph neighborhoods
context.active_tasks_rich       # [{task: {...}, graph_context: {...}}, ...]
context.active_goals_rich       # [{goal: {...}, graph_context: {...}}, ...]
context.active_habits_rich      # [{habit: {...}, graph_context: {...}}, ...]
context.active_events_rich      # [{event: {...}, graph_context: {...}}, ...]
context.core_principles_rich    # [{principle: {...}, graph_context: {...}}, ...]
context.recent_choices_rich     # [{choice: {...}, graph_context: {...}}, ...]
context.knowledge_units_rich    # {uid: {ku: {...}, graph_context: {...}}}
context.enrolled_paths_rich     # [{path: {...}, graph_context: {...}}, ...]
context.active_learning_steps_rich  # [{step: {...}, graph_context: {...}}, ...]
```

### MEGA_QUERY ↔ UserContext Field Mapping (January 2026)

The MEGA_QUERY returns 5 top-level sections that map to UserContext fields:

| MEGA_QUERY Section | UserContext Fields | Populate Method |
|-------------------|-------------------|-----------------|
| `uids` | `active_task_uids`, `active_goal_uids`, `habit_streaks`, etc. | `populate_standard_fields()` |
| `rich` | `active_tasks_rich`, `active_goals_rich`, etc. | `populate_rich_fields()` |
| `user_properties` | `learning_level`, `preferred_time`, `energy_level`, `preferred_personality`, `preferred_tone`, `preferred_guidance`, `available_minutes_daily` | `populate_user_properties()` |
| `life_path` | `life_path_uid`, `life_path_alignment_score` | `populate_life_path()` |
| `progress_counts` | `overall_progress` | `populate_progress_metrics()` |

**Derived fields (computed from rich data, not direct MEGA_QUERY sections):**

| Derived Field | Source Data | Populate Method |
|--------------|-------------|-----------------|
| `tasks_by_goal` | `tasks_rich[].graph_context.goal_context` | `populate_derived_fields()` |
| `habits_by_goal` | `habits_rich[].graph_context.linked_goals` | `populate_derived_fields()` |
| `at_risk_habits` | `habit_streaks`, `habit_completion_rates` | `populate_derived_fields()` |
| `blocked_task_uids` | `task_blockers` (from graph-sourced) | `populate_derived_fields()` |
| `principle_guided_choice_counts` | `principles_rich[].graph_context.guided_choices` | `populate_principle_choice_integration()` |
| `principle_integration_score` | Computed: aligned_choices / total_choices | `populate_principle_choice_integration()` |
| `recent_principle_aligned_choices` | `principles_rich[].graph_context.guided_choices` | `populate_principle_choice_integration()` |

**MOC fields (from `uids` section):**

| MEGA_QUERY Field | UserContext Field | Populate Method |
|-----------------|-------------------|-----------------|
| `active_moc_uids` | `active_moc_uids` | `populate_moc_fields()` |
| `moc_metadata` | `moc_view_counts`, `recently_viewed_moc_uids` | `populate_moc_fields()` |

## 🎯 Profile Intelligence Integration
*Last updated: January 2026*

### Architecture

The Profile page (`/profile`) integrates UserContextIntelligence following SKUEL's fail-fast philosophy:

```
Profile Hub Route
    ↓
_get_user_context(user_uid) → UserContext (~240 fields)
    ↓
_get_intelligence_data(context) → Result[dict] with 4 intelligence outputs
    ↓
OverviewView(context, daily_plan, alignment, synergies, learning_steps)
    ↓
UI Components (all required parameters, no None handling)
```

### Fail-Fast Principles

| Layer | Pattern | Handling |
|-------|---------|----------|
| **Bootstrap** | Factory exists | Fail-fast at startup if missing |
| **Runtime** | Methods return `Result[T]` | Propagate to HTTP boundary (500) |
| **UI** | Components expect data | No None handling, no fallbacks |

### Intelligence Data Flow

```python
async def _get_intelligence_data(context: UserContext) -> Result[dict[str, Any]]:
    # Factory is REQUIRED (bootstrap dependency)
    intelligence = services.context_intelligence.create(context)

    # Methods return Result[T] - propagate errors
    plan_result = await intelligence.get_ready_to_work_on_today()
    if plan_result.is_error:
        return plan_result.expect_error()

    alignment_result = await intelligence.calculate_life_path_alignment()
    synergies_result = await intelligence.get_cross_domain_synergies()
    steps_result = await intelligence.get_optimal_next_learning_steps()

    # ... error handling for each

    return Result.ok({
        "daily_plan": plan_result.value,
        "alignment": alignment_result.value,
        "synergies": synergies_result.value,
        "learning_steps": steps_result.value,
    })
```

### UI Component Pattern

**All 4 intelligence cards require their data:**

```python
def OverviewView(
    context: UserContext,
    daily_plan: "DailyWorkPlan",              # Required
    alignment: "LifePathAlignment",            # Required
    synergies: "list[CrossDomainSynergy]",     # Required (may be empty)
    learning_steps: "list[LearningStep]",      # Required (may be empty)
) -> Div:
```

**Key Distinction:** Empty list `[]` is valid data. The pattern removes `| None`, NOT empty checks.

### Files

| File | Purpose |
|------|---------|
| `/adapters/inbound/user_profile_ui.py` | Routes with fail-fast error handling |
| `/ui/profile/domain_views.py` | UI components with required parameters |
| `/ui/profile/layout.py` | Profile Hub layout with sidebar |

**See:**
- `/docs/patterns/ERROR_HANDLING.md` § "Fail-Fast Philosophy for Required Dependencies"
- `/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md` § "Profile Hub Integration"

---

## 🚀 Future Enhancements

### 1. Event-Driven Invalidation
**Next:** Publish events when entities change, invalidate context cache.

### 2. Selective Context Building
**Next:** Build partial contexts for specific use cases (reduce query load).

### 3. GraphQL Integration
**Next:** Expose `ProfileHubData.context` through GraphQL for rich queries.

---

## See Also

### Architecture Documentation

| Document | Purpose |
|----------|---------|
| [FOURTEEN_DOMAIN_ARCHITECTURE.md](FOURTEEN_DOMAIN_ARCHITECTURE.md) | 14-domain + 5 systems architecture overview |
| [NEO4J_DATABASE_ARCHITECTURE.md](NEO4J_DATABASE_ARCHITECTURE.md) | Database schema, MEGA-QUERY implementation |
| [RELATIONSHIPS_ARCHITECTURE.md](RELATIONSHIPS_ARCHITECTURE.md) | Cross-domain relationships |
| [SEARCH_ARCHITECTURE.md](SEARCH_ARCHITECTURE.md) | Graph-aware search using UserContext |

### Related Patterns

- [query_architecture.md](../patterns/query_architecture.md) - Query builders and MEGA-QUERY pattern
- [protocol_architecture.md](../patterns/protocol_architecture.md) - Protocol-based services

### Key ADRs

- [ADR-016-context-builder-decomposition](../decisions/ADR-016-context-builder-decomposition.md) - Context builder decomposition
- [ADR-015-mega-query-rich-queries-completion](../decisions/ADR-015-mega-query-rich-queries-completion.md) - MEGA-QUERY architecture

---

**Status:** ✅ Architecture complete - Context builder decomposed + Profile Hub Intelligence Integration + MEGA_QUERY Field Mapping
**Last Updated:** January 20, 2026
**Migration Guide:** See `/docs/guides/PATTERN_3C_MIGRATION.md`
**Related ADR:** ADR-016-context-builder-decomposition
