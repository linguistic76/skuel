---
name: user-context-intelligence
description: Expert guide for SKUEL's central cross-domain intelligence hub. Use when implementing daily planning, life path alignment, learning recommendations, schedule-aware recommendations, or when working with UserContextIntelligence, UserContextIntelligenceFactory, or the 8 flagship methods.
allowed-tools: Read, Grep, Glob
---

# UserContextIntelligence: Central Cross-Domain Intelligence Hub

> "THE CORE VALUE PROPOSITION: What should I work on next?"

SKUEL's `UserContextIntelligence` is the central intelligence hub that synthesizes user state (`UserContext` ~240 fields) with all 13 domain services to answer the fundamental question: **"What should I work on today?"**

## Quick Start

### What is UserContextIntelligence?

`UserContextIntelligence` is NOT a `BaseIntelligenceService` subclass. It uses a **modular mixin architecture** (ADR-021) that composes functionality from 5 specialized mixins:

```python
class UserContextIntelligence(
    LearningIntelligenceMixin,      # Methods 1-4: Learning steps, critical path
    LifePathIntelligenceMixin,      # Method 7: Life path alignment
    SynergyIntelligenceMixin,       # Method 6: Cross-domain synergies
    ScheduleIntelligenceMixin,      # Method 8: Schedule-aware recommendations
    TemporalMomentumMixin,          # Momentum signals (entities_rich analysis)
    DailyPlanningMixin,             # Method 5: THE FLAGSHIP - Daily work plan
):
    """Learning journey intelligence = Context + 13 Domain Services."""
```

### Core Architecture

```
UserContextIntelligence = UserContext + 13 Domain Services
                        = User State + Complete Graph Intelligence
```

**UserContext (~240 fields)** provides:
- Current mastery levels, prerequisites, learning goals
- Active tasks, habits, goals, events
- Workload capacity, available time, energy levels
- Life path alignment, recommended next steps

**13 Domain Services** provide:
- Fresh graph queries for real-time data
- Cross-domain relationship traversal
- Actionable recommendations

---

## The 8 Core Methods

| # | Method | Mixin | Purpose |
|---|--------|-------|---------|
| 1 | `get_optimal_next_learning_steps()` | Learning | What should I learn next? |
| 2 | `get_learning_path_critical_path()` | Learning | Fastest route to life path? |
| 3 | `get_knowledge_application_opportunities()` | Learning | Where can I apply this? |
| 4 | `get_unblocking_priority_order()` | Learning | What unlocks the most? |
| 5 | **`get_ready_to_work_on_today()`** | Daily | **THE FLAGSHIP** - What's optimal for TODAY? |
| 6 | `get_cross_domain_synergies()` | Synergy | Cross-domain synergy detection |
| 7 | `calculate_life_path_alignment()` | LifePath | Life path alignment scoring |
| 8 | `get_schedule_aware_recommendations()` | Schedule | Schedule-aware recommendations |

---

## The 13 Required Domain Services

`UserContextIntelligence` requires ALL 13 domain services at construction:

### Activity Domains (6)

All use `UnifiedRelationshipService` with domain configs:

| Service | Attribute | Purpose |
|---------|-----------|---------|
| Tasks | `self.tasks` | Actionable tasks, overdue items |
| Goals | `self.goals` | Active goals, advancement opportunities |
| Habits | `self.habits` | At-risk habits, streak maintenance |
| Events | `self.events` | Upcoming events, scheduling |
| Choices | `self.choices` | Pending decisions |
| Principles | `self.principles` | Value alignment |

### Curriculum Domains (3)

| Service | Attribute | Purpose |
|---------|-----------|---------|
| KU | `self.ku` | Knowledge readiness (KuGraphService) |
| LS | `self.ls` | Learning step sequencing (UnifiedRelationshipService) |
| LP | `self.lp` | Life path analysis (UnifiedRelationshipService) |

### Processing Domains (3)

| Service | Attribute | Purpose |
|---------|-----------|---------|
| Submissions | `self.submissions` | Student work relationship graph — FOLLOWS, RELATED_TO, SUPPORTS_GOAL (`SubmissionsRelationshipService`) |
| Feedback | `self.feedback` | Feedback loop graph queries — pending submissions, completion rate (`FeedbackRelationshipService`) |
| Analytics | `self.analytics` | Cross-domain analytics (`AnalyticsRelationshipService`) |

> **Wired, Not Yet Called**
> These 2 services are required at construction and stored on `self`, but no mixin currently invokes them. The intelligence methods for the processing domain are architecturally reserved — the slots exist, the calling code has not been written yet:
>
> | Service | Will power | Status |
> |---------|-----------|--------|
> | `self.submissions` | Cross-domain submission state (planned) | Wired, not called |
> | `self.analytics` | Cross-domain pattern queries in synergy detection | Wired, not called |
>
> `self.feedback` is now active — `DailyPlanningMixin` calls `get_unsubmitted_exercises()` at Priority 2.5.

### Temporal Domain (1)

| Service | Attribute | Purpose |
|---------|-----------|---------|
| Calendar | `self.calendar` | Schedule-aware intelligence |

### Optional Services (FULL tier only)

| Service | Attribute | Purpose |
|---------|-----------|---------|
| ZPDService | `self.zpd_service` | Curriculum-graph-aware ZPD ranking for `get_optimal_next_learning_steps()` |
| Neo4jVectorSearchService | `self.vector_search` | Semantic search enhancements |

Both are `None` in CORE tier — all methods gracefully degrade when absent.

**ZPD (Zone of Proximal Development):**

When `zpd_service` is set, `get_optimal_next_learning_steps()` uses a two-hop curriculum graph traversal to rank KUs by readiness:

```python
priority_score = readiness_score × (0.7 + 0.3 × behavioral_readiness)
```

`behavioral_readiness` aggregates choices (65%) + habits (35%) signals via `ChoicesIntelligenceService` and `HabitsIntelligenceService`. When ZPD assessment is empty (no engagement relationships yet in graph), the method falls through to the activity-based ranking algorithm.

**Wiring ZPD in bootstrap:**

```python
from core.services.zpd import ZPDService

zpd_service: ZPDOperations | None = None
if tier.ai_enabled:  # FULL tier
    zpd_service = ZPDService(
        driver=driver,
        choices_intelligence=activity_services["choices"].intelligence,
        habits_intelligence=activity_services["habits"].intelligence,
    )
    services.zpd_service = zpd_service

factory = UserContextIntelligenceFactory(
    ...,  # 13 required services
    zpd_service=zpd_service,
)
```

---

## The 5 Structured Return Types

| Type | Purpose | Key Fields |
|------|---------|------------|
| `LearningStep` | Learning recommendation | `ku_uid`, `priority_score`, `aligns_with_goals` |
| `DailyWorkPlan` | Daily work plan | `tasks`, `habits`, `learning`, `rationale` |
| `LifePathAlignment` | Life path analysis | `overall_score`, `dimension_scores`, `gaps` |
| `CrossDomainSynergy` | Synergy detection | `source_uid`, `target_uids`, `synergy_score` |
| `ScheduleAwareRecommendation` | Schedule-aware rec | `suggested_time_slot`, `schedule_fit_score` |

### DailyWorkPlan (The Flagship Return Type)

```python
@dataclass
class DailyWorkPlan:
    # Domain-specific UIDs
    learning: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    habits: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    principles: list[str] = field(default_factory=list)

    # Contextual items (enriched)
    contextual_tasks: list[ContextualTask] = field(default_factory=list)
    contextual_habits: list[ContextualHabit] = field(default_factory=list)
    contextual_goals: list[ContextualGoal] = field(default_factory=list)
    contextual_knowledge: list[ContextualKnowledge] = field(default_factory=list)

    # Plan metadata
    estimated_time_minutes: int = 0
    fits_capacity: bool = True
    workload_utilization: float = 0.0  # 0.0-1.0
    rationale: str = ""
    priorities: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

---

## Build Paths: MEGA_QUERY vs CONSOLIDATED_QUERY

`UserContextIntelligence` always requires **rich context** from `build_rich()`. The two build paths produce structurally similar `UserContext` objects but with different data density:

| Query | Method | Speed | ActivityReport fields | Intelligence-ready? |
|-------|--------|-------|-----------------------|---------------------|
| `MEGA_QUERY` (~875 lines) | `build_rich()` | ~150-200ms | ✅ populated | **Yes** — full entities + graph |
| `CONSOLIDATED_QUERY` (lightweight) | `build()` | ~50-100ms | ✅ populated | No — UIDs only |

**What both paths share (March 2026):** `latest_activity_report_*` fields (`uid`, `period`, `period_end`, `content`, `user_annotation`) are now populated by both queries. CONSOLIDATED_QUERY fetches the latest ActivityReport via the same OPTIONAL MATCH + ORDER BY + collect-first-one pattern as MEGA_QUERY, and shapes the result with identical key names so `populate_activity_report()` works unchanged on both paths.

**What only MEGA_QUERY provides:** Full entity objects (`entities_rich["tasks"]`, `entities_rich["goals"]`, etc.), graph neighborhoods, `cross_domain_insights` (active_insights_raw). These are absent in standard context.

**`build_rich()` optional `window` parameter:** Passing `window="7d"` (or `"14d"`,
`"30d"`, `"90d"`) includes completed entities touched within the window in `context.entities_rich`
alongside active entities. Used by **both** intelligence methods and feedback services
(`ProgressFeedbackGenerator`, `ActivityReportService`). Default `window="30d"` always
provides the standard 30-day window.

**The rule:** Always pass `build_rich()` context to intelligence. `require_rich_context()` will catch mistakes:

```python
# ❌ WRONG — build() context will fail at require_rich_context()
context = await builder.build(user_uid)
intelligence = factory.create(context)
plan = await intelligence.get_ready_to_work_on_today()  # Raises ValueError

# ✅ CORRECT — build_rich() for intelligence (no time_period needed)
context = await builder.build_rich(user_uid)
intelligence = factory.create(context)
plan = await intelligence.get_ready_to_work_on_today()

# ✅ For feedback generation (ProgressFeedbackGenerator, ActivityReportService)
context = await builder.build_rich(user_uid, time_period="7d")
# context.activity_rich populated; active_*_rich unchanged
```

**When standard context is enough:** API ownership checks, ActivityReport display, lightweight profile data — `build()` is sufficient and ~3× faster.

---

## Two-Level Architecture

SKUEL's intelligence services are designed so the app runs at full capability without any LLM dependency.

### Level 1 — Graph Analytics (Always Runs)

`UserContextIntelligence` and its 5 mixins are **pure graph analytics** — Cypher queries, relationship traversals, scoring. No LLM, no embeddings.

```
UserContextIntelligence (Level 1)
├── DailyPlanningMixin            → Pure Cypher: tasks, habits, goals, events, ku
├── LearningIntelligenceMixin     → Pure Cypher: ku graph traversal, prerequisite chains
├── LifePathIntelligenceMixin     → Pure Cypher: SERVES_LIFE_PATH relationships
├── SynergyIntelligenceMixin      → Pure Cypher: cross-domain relationship patterns
└── ScheduleIntelligenceMixin     → Pure Cypher: calendar + capacity scoring
```

All 13 required services are Level 1. `SubmissionsRelationshipService`, `FeedbackRelationshipService`, and `AnalyticsRelationshipService` are pure Cypher — no LLM required.

### Level 2 — AI Enhancement (Optional)

AI features live in separate `*_ai_service.py` files, one per domain. These extend `BaseAIService` and depend on LLM/embeddings:

```
tasks_intelligence_service.py  ← Level 1: BaseAnalyticsService (always available)
tasks_ai_service.py            ← Level 2: BaseAIService (optional, requires LLM)
```

13 such pairs exist in the codebase. `UserContextIntelligence` is Level 1. The optional `vector_search=` parameter is the only Level 2 hook in the constructor.

### Why the Processing Domains Are Wired But Not Called

`self.submissions`, `self.feedback`, and `self.analytics` are Level 1 services stored on the instance. The mixin methods that CALL them have not been written yet — the architecture is established, the implementation is next.

This is by design. The slot reservation ensures future implementation is a fill-in, not a redesign.

---

## Factory Pattern

### Why a Factory?

- `UserContextIntelligence` requires a `UserContext` at construction
- Context is user-specific and built on-demand
- The 13 domain services are singletons (created once at bootstrap)
- Factory pattern separates **service wiring** from **context binding**

### UserContextIntelligenceFactory

```python
from core.services.user.intelligence import UserContextIntelligenceFactory

# At bootstrap (services_bootstrap.py)
factory = UserContextIntelligenceFactory(
    # Activity Domains (6)
    tasks=tasks_service.relationships,
    goals=goals_service.relationships,
    habits=habits_service.relationships,
    events=events_service.relationships,
    choices=choices_service.relationships,
    principles=principles_service.relationships,
    # Curriculum Domains (3)
    ku=ku_service.graph,
    ls=ls_service.relationships,
    lp=lp_service.relationships,
    # Processing Domains (3)
    submissions=submissions_relationship_service,
    feedback=feedback_relationship_service,
    analytics=analytics_relationship_service,
    # Temporal Domain (1)
    calendar=calendar_service,
)
services.context_intelligence = factory
```

### Creating Intelligence Instances

```python
# At runtime (in UserService or route handler)
context = await user_service.get_user_context(user_uid)
intelligence = factory.create(context)

# Use flagship method
plan = await intelligence.get_ready_to_work_on_today()
```

Note: `factory.create()` also accepts an optional `vector_search=` service for semantic search enhancements.

---

## The Flagship Method: get_ready_to_work_on_today()

This is THE core value proposition of SKUEL. It currently synthesizes 10 domains and has slot reservations for 2 more:

### Method Signature

```python
async def get_ready_to_work_on_today(
    self,
    prioritize_life_path: bool = True,
    respect_capacity: bool = True,
) -> Result[DailyWorkPlan]:
    """
    THE FLAGSHIP METHOD - What should I focus on TODAY?

    Currently synthesizes 10 of 13 wired domains:
    - Activity Domains (6): tasks, habits, goals, events, choices, principles
    - Curriculum Domains (3): ku, ls, lp
    - Submissions Domain (1): self.feedback — Priority 2.5: unsubmitted exercises

    Processing Domains (2): wired, not yet called
    - self.submissions: cross-domain submission state (planned)
    - self.analytics: cross-domain pattern scoring (planned)

    Respects:
    - context.available_minutes_daily (capacity)
    - context.current_energy_level (cognitive load)
    - context.current_workload_score (not overload)
    """
```

### Priority & Confidence in get_ready_to_work_on_today()

`get_ready_to_work_on_today()` applies a **CRITICAL priority override** before returning its
ranked plan. Any entity with `priority = "critical"` from `context.entities_rich` (all 6 Activity
Domains) is moved to the front of its uid list, capped at **3 items total** across all domains.

**Guard:** Only fires when `context.is_rich_context` is `True`
(i.e., `build_rich()` was called, not `build()`).

**File:** `core/services/user/intelligence/daily_planning.py` — "CRITICAL PRIORITY OVERRIDE" block

**See:** `/docs/architecture/PRIORITY_CONFIDENCE_ARCHITECTURE.md`

---

### Priority Order

The method prioritizes work in this order:

1. **At-risk habits** (maintain streaks - highest priority)
2. **Today's events** (can't reschedule)
2.5. **Unsubmitted exercises** (teacher assignments — external accountability)
3. **Overdue and actionable tasks**
4. **Daily habits** (consistency)
5. **Learning** (if capacity allows)
6. **Advancing goals**
7. **Pending decisions** (high priority only)
8. **Aligned principles** (for focus)

### Usage Example

```python
intelligence = factory.create(context)

result = await intelligence.get_ready_to_work_on_today(
    prioritize_life_path=True,
    respect_capacity=True
)

if result.is_ok:
    plan = result.value

    # Display priorities
    for priority in plan.priorities:
        print(f"- {priority}")

    # Check capacity
    print(f"Utilization: {plan.workload_utilization:.0%}")
    print(f"Fits capacity: {plan.fits_capacity}")

    # Show warnings
    for warning in plan.warnings:
        print(f"Warning: {warning}")
```

---

## Mixin Architecture

### 5 Specialized Mixins

| Mixin | Methods | Lines | Focus |
|-------|---------|-------|-------|
| `LearningIntelligenceMixin` | 1-4 | ~470 | Learning steps, critical path, application |
| `LifePathIntelligenceMixin` | 7 | ~150 | Life path alignment scoring |
| `SynergyIntelligenceMixin` | 6 | ~200 | Cross-domain synergy detection |
| `ScheduleIntelligenceMixin` | 8 | ~180 | Schedule-aware recommendations |
| `DailyPlanningMixin` | 5 | ~255 | THE FLAGSHIP daily planning |

### Mixin Composition Pattern

```python
class UserContextIntelligence(
    LearningIntelligenceMixin,
    LifePathIntelligenceMixin,
    SynergyIntelligenceMixin,
    ScheduleIntelligenceMixin,
    DailyPlanningMixin,
):
    def __init__(self, context: UserContext, ...):
        # Store context and all 13 services
        self.context = context
        self.tasks = tasks
        # ... 12 more services
```

### Mixin Requirements

Each mixin expects these attributes on `self`:

```python
class DailyPlanningMixin:
    context: UserContext           # User state
    tasks: Any                     # UnifiedRelationshipService
    habits: Any                    # UnifiedRelationshipService
    goals: Any                     # UnifiedRelationshipService
    events: Any                    # UnifiedRelationshipService
    choices: Any                   # UnifiedRelationshipService
    principles: Any                # UnifiedRelationshipService
    ku: Any                        # KuGraphService
```

**Domain-specific planning methods** (`get_at_risk_habits_for_user`, `get_actionable_tasks_for_user`, `get_upcoming_events_for_user`, `get_advancing_goals_for_user`, `get_pending_decisions_for_user`, `get_aligned_principles_for_user`) are provided by `_domain_planning_mixin.py` in the URS package via MRO — `DailyPlanningMixin` calls them on `self.tasks`, `self.habits`, etc.

---

## UserContext Integration

### Key Context Fields Used

| Field | Type | Used By |
|-------|------|---------|
| `available_minutes_daily` | `int` | Capacity planning |
| `current_energy_level` | `float` | Cognitive load |
| `current_workload_score` | `float` | Overload prevention |
| `life_path_uid` | `str \| None` | Life path alignment |
| `daily_habits` | `list[str]` | Daily planning |
| `active_habit_uids` | `list[str]` | Habit tracking |
| `upcoming_event_uids` | `list[str]` | Event scheduling |
| `prerequisites_completed` | `set[str]` | Learning readiness |
| `prerequisites_needed` | `dict[str, list[str]]` | Prerequisite chains |
| `mastered_knowledge_uids` | `set[str]` | Mastery tracking |
| `estimated_time_to_mastery` | `dict[str, int]` | Time estimates |
| `learning_goals` | `list[str]` | Learning alignment |
| `primary_goal_focus` | `str \| None` | Goal prioritization |

### Context Methods Used

```python
# Get ready-to-learn knowledge units
ready_uids = context.get_ready_to_learn()

# Check if knowledge is mastered
is_mastered = ku_uid in context.mastered_knowledge_uids

# Get prerequisites for an item
prereqs = context.prerequisites_needed.get(item_uid, [])
```

---

## Usage Examples

### Example 1: Daily Planning

```python
from core.services.user.intelligence import UserContextIntelligenceFactory

# Create factory at bootstrap
factory = UserContextIntelligenceFactory(
    tasks=tasks_relationships,
    goals=goals_relationships,
    habits=habits_relationships,
    # ... other services
)

# At runtime
context = await user_service.get_user_context("user.mike")
intelligence = factory.create(context)

# Get daily plan
plan_result = await intelligence.get_ready_to_work_on_today()

if plan_result.is_ok:
    plan = plan_result.value
    print(f"Today's plan ({plan.estimated_time_minutes} minutes):")
    print(f"Rationale: {plan.rationale}")
```

### Example 2: Learning Recommendations

```python
# Get optimal next learning steps
steps_result = await intelligence.get_optimal_next_learning_steps(
    max_steps=5,
    consider_goals=True,
    consider_capacity=True
)

if steps_result.is_ok:
    for step in steps_result.value:
        print(f"Learn: {step.title}")
        print(f"  Priority: {step.priority_score:.1%}")
        print(f"  Rationale: {step.rationale}")
        print(f"  Unlocks: {step.unlocks_count} items")
```

### Example 3: Life Path Alignment

```python
# Calculate alignment with life path
alignment_result = await intelligence.calculate_life_path_alignment()

if alignment_result.is_ok:
    alignment = alignment_result.value
    print(f"Alignment: {alignment.overall_score:.1%} ({alignment.alignment_level})")
    print(f"Knowledge: {alignment.knowledge_score:.1%}")
    print(f"Activity: {alignment.activity_score:.1%}")
    print(f"Momentum: {alignment.momentum_score:.1%}")

    if alignment.gaps:
        print("Gaps:", ", ".join(alignment.gaps))
```

### Example 4: Cross-Domain Synergies

```python
# Detect synergies across domains
synergies_result = await intelligence.get_cross_domain_synergies()

if synergies_result.is_ok:
    for synergy in synergies_result.value:
        print(f"{synergy.source_domain} → {synergy.target_domain}")
        print(f"  Type: {synergy.synergy_type}")
        print(f"  Score: {synergy.synergy_score:.1%}")
        print(f"  Targets: {len(synergy.target_uids)} items")
```

---

## Anti-Patterns

### Don't Create Without Factory

```python
# WRONG - direct instantiation misses service wiring
intelligence = UserContextIntelligence(
    context=context,
    tasks=tasks,  # Where do these come from?
    # ...
)

# CORRECT - use factory pattern
factory = services.context_intelligence  # Wired at bootstrap
intelligence = factory.create(context)
```

### Don't Cache Intelligence Instances

```python
# WRONG - context becomes stale
cached_intelligence = factory.create(context)
# ... time passes ...
plan = await cached_intelligence.get_ready_to_work_on_today()  # Stale!

# CORRECT - create fresh for each request
context = await user_service.get_user_context(user_uid)
intelligence = factory.create(context)  # Fresh context
plan = await intelligence.get_ready_to_work_on_today()
```

### Don't Ignore Result Errors

```python
# WRONG - crashes on error
result = await intelligence.get_ready_to_work_on_today()
plan = result.value  # Raises if error!

# CORRECT - check result
result = await intelligence.get_ready_to_work_on_today()
if result.is_ok:
    plan = result.value
else:
    error = result.expect_error()
    logger.error(f"Daily planning failed: {error.message}")
```

### Don't Mix with BaseIntelligenceService

```python
# WRONG - UserContextIntelligence is NOT a BaseIntelligenceService
class MyService(BaseIntelligenceService):
    def __init__(self, intelligence: UserContextIntelligence):
        super().__init__(intelligence)  # Wrong pattern!

# CORRECT - UserContextIntelligence is used via factory
factory = services.context_intelligence
intelligence = factory.create(context)
```

---

## Key Source Files

| File | Purpose |
|------|---------|
| `/core/services/user/intelligence/__init__.py` | Package exports |
| `/core/services/user/intelligence/core.py` | Main class |
| `/core/services/user/intelligence/factory.py` | Factory pattern |
| `/core/models/context_types.py` | Return types (LearningStep, DailyWorkPlan, etc.) |
| `/core/services/user/intelligence/daily_planning.py` | Flagship method |
| `/core/services/user/intelligence/learning_intelligence.py` | Methods 1-4 |
| `/core/services/user/intelligence/life_path_intelligence.py` | Method 7 |
| `/core/services/user/intelligence/synergy_intelligence.py` | Method 6 |
| `/core/services/user/intelligence/schedule_intelligence.py` | Method 8 |
| `/core/services/submissions/submissions_relationship_service.py` | Level 1 — submission graph queries |
| `/core/services/feedback/feedback_relationship_service.py` | Level 1 — feedback loop graph queries |
| `/core/services/analytics_relationship_service.py` | Level 1 — cross-domain analytics queries |
| `/core/services/relationships/_domain_planning_mixin.py` | 6 domain-specific planning methods called by DailyPlanningMixin on URS instances |
| `/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md` | Documentation |

## Deep Dive Resources

**Architecture:**
- [UNIFIED_USER_ARCHITECTURE.md](/docs/architecture/UNIFIED_USER_ARCHITECTURE.md) - Complete UserContext architecture
- [ADR-030](/docs/decisions/ADR-030-usercontext-file-consolidation.md) - UserContext consolidation decision
- [ADR-021](/docs/decisions/ADR-021-user-context-intelligence-modularization.md) - Intelligence modularization

**Implementation:**
- [USER_CONTEXT_INTELLIGENCE.md](/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md) - Detailed implementation guide

**Patterns:**
- [SERVICE_CONSOLIDATION_PATTERNS.md](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md) - Service patterns

---

## Related Skills

- **[base-analytics-service](../base-analytics-service/SKILL.md)** - Level 1 domain analytics (BaseAnalyticsService, no AI) — same tier as UserContextIntelligence
- **[learning-loop](../learning-loop/SKILL.md)** - The four-phased loop (Ku → Exercise → Submission → Feedback) — context for why submissions/feedback slots exist
- **[result-pattern](../result-pattern/SKILL.md)** - Result[T] error handling

## See Also

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - 13 services, 8 methods, 5 return types
- [MIXIN_ARCHITECTURE.md](MIXIN_ARCHITECTURE.md) - 5 mixins and responsibilities
- [FACTORY_PATTERN.md](FACTORY_PATTERN.md) - UserContextIntelligenceFactory usage
