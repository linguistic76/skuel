---
title: Analytics Architecture - Statistical Aggregation Meta-Service
updated: 2026-03-03
status: current
category: architecture
tags: [architecture, analytics]
related: []
---

# Analytics Architecture - Statistical Aggregation Meta-Service

## Executive Summary

**Analytics is NOT a domain** — it's a **meta-layer statistical aggregation service** that reads from multiple domains to generate quantitative assessments.

**Key Distinction:** Unlike all other SKUEL domains (tasks, goals, habits, etc.), Analytics:
- Does NOT store entities in the graph
- Does NOT create relationships
- Does NOT have a relationship service
- Is purely READ-ONLY (aggregates existing data)
- Spans all domains

---

## The Unique Nature of Analytics

### What Analytics IS

**Analytics is a statistical compiler** — it queries multiple domain services, aggregates their data, and generates quantitative metrics.

```
User Activity Across Domains
    ↓
Analytics Service (Facade Pattern)
    ├── AnalyticsMetricsService → Query domain services
    ├── AnalyticsAggregationService → Synthesize cross-domain data
    └── AnalyticsLifePathService → Track life path alignment
    ↓
Statistical Metrics (NOT graph entities)
```

**Philosophy:** "Listen and respond" — SKUEL provides data when asked, never pushes advice.

### What Analytics is NOT

❌ **Not a Domain** — Not in `EntityType` or `NonKuDomain` enum
❌ **Not a Graph Entity** — No `Analytics` nodes stored in Neo4j
❌ **Not Relational** — No analytics relationship service
❌ **Not Write-Heavy** — Only generates and optionally stores markdown files
❌ **Not Prescriptive** — Contains ONLY metrics, no AI recommendations

---

## Architecture: 4-Service Facade Pattern

### AnalyticsService (Facade)

**Location:** `/core/services/analytics_service.py`

**Responsibilities:**
1. Orchestrate analytics generation across all domains
2. Delegate to specialized sub-services
3. Handle markdown rendering and file storage
4. Handle event-driven analytics generation
5. Maintain the single external entry point

**Key Dependencies:** Takes all domain services as constructor parameters
```python
def __init__(
    self,
    tasks_service=None,
    habits_service=None,
    goals_service=None,
    events_service=None,
    finance_service=None,
    choices_service=None,
    principle_service=None,
    content_enrichment=None,
    user_service=None,
    ku_service=None,
    lp_service=None,
    report_dir: Path | None = None,
    event_bus=None,
)
```

### AnalyticsMetricsService

**Location:** `/core/services/analytics/analytics_metrics_service.py`

**Responsibilities:**
- Generate domain-specific statistical metrics
- Query individual services for raw data
- Calculate completion rates, totals, averages

**Metrics by Domain:**
- **Tasks:** completion_rate, overdue_count, priority_distribution, avg_completion_time_days
- **Habits:** current_streaks, consistency_score, completion_rate
- **Goals:** on_track_count, at_risk_count, progress_percentage, completion_rate
- **Events:** total_count, completion_rate, time_distribution, total_hours_scheduled
- **Finance:** total_expenses, category_breakdown, budget_variance, avg_daily_expense
- **Choices:** total_count, domain_distribution, decision_quality_avg
- **Principles:** total_principles, active_principles, avg_strength, alignment_score
- **Knowledge:** substance_scores, mastery_levels, decay_warnings
- **Submissions:** reflection_frequency, theme_analysis, metacognition_score

### AnalyticsAggregationService

**Location:** `/core/services/analytics/analytics_aggregation_service.py`

**Responsibilities:**
- Cross-domain synthesis (Life Analytics)
- Detect patterns across multiple domains
- Generate weekly/monthly/quarterly/yearly summaries

**Methods:**
- `aggregate_weekly_life_summary()`
- `aggregate_monthly_life_review()`
- `aggregate_quarterly_progress()`
- `aggregate_yearly_review()`
- `detect_cross_domain_patterns()`

### AnalyticsLifePathService

**Location:** `/core/services/analytics/analytics_life_path_service.py`

**Responsibilities:**
- Calculate life path alignment
- Track alignment trends over time
- Identify knowledge gaps
- Analyze domain contributions

**Methods:**
- `calculate_life_path_alignment()`
- `track_alignment_trends()`
- `identify_knowledge_gaps()`
- `analyze_domain_contributions()`

---

## Analytics Domains Covered

**From `AnalyticsDomain` enum (`core/models/enums/entity_enums.py`):**

| AnalyticsDomain | Domain Queried | Key Metrics |
|-----------------|----------------|-------------|
| `TASKS` | Tasks | completion_rate, overdue_count, priority_distribution |
| `HABITS` | Habits | current_streaks, consistency_score, completion_rate |
| `GOALS` | Goals | on_track_count, at_risk_count, progress_percentage |
| `EVENTS` | Events | total_count, completion_rate, time_distribution |
| `FINANCE` | Finance | total_expenses, category_breakdown, budget_variance |
| `CHOICES` | Choices | total_count, domain_distribution, outcome_analysis |

**Note:** No `ANALYTICS` or `SUBMISSIONS` enum values. Submissions are used IN analytics (via `AnalyticsMetricsService`) but don't generate standalone analytics. Principles are tracked via life path alignment rather than as a separate analytics domain.

---

## Data Flow: Read-Only Aggregation

```
Domain Services (Source of Truth)
    ↓ read
AnalyticsMetricsService
    ↓ queries
TasksService.list_tasks(user_uid, status="completed")
HabitsService.get_user_habits(user_uid)
GoalsService.get_user_goals(user_uid)
EventsService.get_user_events(user_uid, period)
FinanceService.get_expenses(user_uid, period)
ChoicesService.get_user_choices(user_uid, period)
    ↓ aggregate
Statistical Metrics Dict
    ↓ format
AnalyticsSummary (frozen domain model)
    ↓ render (optional)
Markdown File (stored in /data/analytics/)
```

**Critical:** Analytics NEVER writes to domain services — strictly read-only.

---

## Why Analytics Has No Relationship Service

**Reason:** Analytics doesn't create relationships. It consumes them.

**Contrast with other domains:**
- **Tasks** → Has relationship methods on `TasksBackend` — creates DEPENDS_ON, CONTRIBUTES_TO_GOAL edges
- **Goals** → Has relationship methods on `GoalsBackend` — creates SUPPORTS, REQUIRES edges
- **Analytics** → NO relationship service — only reads existing edges for statistics

**Example:**
```python
# TasksBackend (writes relationships)
await tasks_backend.link_task_to_goal(task_uid, goal_uid, contribution=0.3)

# AnalyticsMetricsService (reads relationships for metrics)
tasks_for_goal = await tasks_service.get_tasks_for_goal(goal_uid)
completion_rate = calculate_completion(tasks_for_goal)
```

---

## Analytics and the Graph

Analytics interacts with the graph in a unique way:

### What Analytics Queries

Analytics queries graph relationships to calculate metrics:
- Task completion rates (via CONTRIBUTES_TO_GOAL edges)
- Goal dependencies (via DEPENDS_ON edges)
- Knowledge application (via APPLIES_KNOWLEDGE edges)
- Life path alignment (via cross-domain edge traversal)

### What Analytics Stores

**Option 1:** Nothing (ephemeral)
- Analytics generated on-demand
- Returned to client
- No persistence

**Option 2:** Markdown files (optional)
- Stored in `/data/analytics/`
- File-based, NOT in Neo4j
- Used for historical reference

**Analytics are NEVER stored as nodes in Neo4j.**

---

## Architectural Patterns

### 1. Meta-Service (Not a Domain)

Analytics sits ABOVE the domain layer, reading across all of them:

```
Activity Domains (tasks, habits, goals, events, finance, choices, principles)
Curriculum Domains (ku, ls, lp)
Submissions + Feedback

                    ↓ reads from all ↓

            AnalyticsService (Meta-Layer)
```

### 2. Facade Pattern (3 Sub-Services)

```
AnalyticsService (Facade)
├── AnalyticsMetricsService (domain-specific metrics)
├── AnalyticsAggregationService (cross-domain synthesis)
└── AnalyticsLifePathService (life path alignment)
```

### 3. Read-Only Aggregation

Analytics ONLY reads, NEVER writes:
- ✅ Query domain services
- ✅ Aggregate data
- ✅ Calculate metrics
- ❌ Create entities
- ❌ Modify data
- ❌ Create relationships

### 4. Stateless Generation

Analytics are generated on-demand:
- No cached state
- Fresh data each time
- No stale metrics

---

## Model Layer

### AnalyticsSummary (Domain Model)

**Location:** `/core/models/analytics/analytics.py`

```python
@dataclass(frozen=True)
class AnalyticsSummary:
    uid: str
    user_uid: str
    analytics_domain: AnalyticsDomain
    period_start: date
    period_end: date
    metrics: dict[str, Any]
    generated_at: datetime
    title: str
    markdown_content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_metric(self, key: str, default: Any = None) -> Any: ...
    def get_period_days(self) -> int: ...
    def is_current_period(self) -> bool: ...
    def format_period(self) -> str: ...
```

### AnalyticsSummaryDTO (Transfer Layer)

Mutable version for construction and persistence.

### No Pydantic Models

Analytics doesn't have external API validation models — generated internally only.

---

## Key Design Decisions

### 1. Why NOT Store Analytics in Neo4j?

**Rationale:**
- Analytics are derived data (not source of truth)
- Storing would create duplication
- Graph queries would be slower than recomputing
- No relationships to other entities (no graph value)

**Alternative:** File-based storage for historical reference

### 2. Why NO Analytics Relationship Service?

**Rationale:**
- Analytics doesn't create relationships
- Analytics consumes relationships for metrics
- No cross-domain edges involving analytics
- Analytics are ephemeral statistical views

### 3. Why NO `EntityType.ANALYTICS` or `NonKuDomain.ANALYTICS`?

**Rationale:**
- Analytics is not a domain — it's a meta-service
- Domain enums are for entity types (tasks, habits, goals)
- Analytics doesn't have entities
- Including would confuse domain-based routing

---

## Integration Points

### Services That PROVIDE Data to Analytics

| Service | Data Provided | Query Method |
|---------|---------------|--------------|
| TasksService | Task completions, statuses | `get_user_items_in_range(user_uid, dates)` |
| HabitsService | Habit streaks, completions | `get_user_items_in_range(user_uid, dates)` |
| GoalsService | Goal progress, milestones | `get_user_items_in_range(user_uid, dates)` |
| EventsService | Event completions, schedules | `get_user_items_in_range(user_uid, dates)` |
| FinanceService | Expenses, budgets | `get_user_items_in_range(user_uid, dates)` |
| ChoicesService | Decisions, outcomes | `get_user_items_in_range(user_uid, dates)` |
| PrincipleService | Principle strength, alignment | `get_user_items_in_range(user_uid, dates)` |
| ContentEnrichment | Submission reflection patterns | Direct submission node query |
| KuService | Knowledge mastery | `list_by_user(user_uid, limit)` |
| LpService | Learning path progress | `list_by_user(user_uid, limit)` |

### Services That COULD Consume Analytics (Future)

| Service | Use Case | Integration Method |
|---------|----------|-------------------|
| CalendarService | Scheduled generation | Trigger on calendar event |
| UserService | Dashboard widgets | Include recent analytics in context |

---

## Distinction from Activity Feedback (`ActivityReport`)

Analytics and `ActivityReport` are often confused — both aggregate activity data — but they serve different purposes:

| | `AnalyticsService` | `ActivityReport` |
|---|---|---|
| **Output** | Ephemeral metrics dict / markdown file | `ACTIVITY_REPORT` entity stored in Neo4j |
| **Trigger** | On-demand query | Scheduled or user-initiated |
| **Scope** | Statistical aggregation (counts, rates) | Qualitative synthesis (LLM or human) |
| **Storage** | Optional file, never Neo4j | Always Neo4j |
| **Feedback loop** | None | Yes — user annotation feeds next LLM prompt |

**See:** [FEEDBACK_ARCHITECTURE.md](FEEDBACK_ARCHITECTURE.md) for the `ActivityReport` pattern.

---

## See Also

- [FEEDBACK_ARCHITECTURE.md](FEEDBACK_ARCHITECTURE.md) — `ActivityReport` and `SubmissionFeedback` patterns
- [FEEDBACK_ARCHITECTURE.md](FEEDBACK_ARCHITECTURE.md) — Submission pipeline, Exercise, visibility model
- [INTELLIGENCE_SERVICES_INDEX.md](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md) — Domain intelligence services (extend `BaseAnalyticsService`)
- [Entity Type Architecture](ENTITY_TYPE_ARCHITECTURE.md)
