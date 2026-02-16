---
title: Analytics Architecture - Statistical Aggregation Meta-Service
updated: 2026-02-06
status: current
category: architecture
tags: [architecture, analytics]
related: []
---

# Analytics Architecture - Statistical Aggregation Meta-Service
**Date:** January 20, 2026
**Type:** Architectural Documentation
**Status:** ✅ ACTIVE

## Executive Summary

**Analytics is NOT a domain** - it's a **meta-layer statistical aggregation service** that reads from multiple domains to generate quantitative assessments.

**Key Distinction:** Unlike all other SKUEL domains (tasks, goals, habits, etc.), Analytics:
- Does NOT store entities in the graph
- Does NOT create relationships
- Does NOT have a relationship service
- Is purely READ-ONLY (aggregates existing data)
- Spans ALL layers (0, 1, 2, 3) and ALL domains

---

## The Unique Nature of Analytics

### What Analytics IS

**Analytics is a statistical compiler** - it queries multiple domain services, aggregates their data, and generates quantitative metrics.

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

**Philosophy:** "Listen and respond" - SKUEL provides data when asked, never pushes advice.

### What Analytics is NOT

❌ **Not a Domain** - Not in `Domain` enum (no `Domain.ANALYTICS`)
❌ **Not a Graph Entity** - No `Analytics` nodes stored in Neo4j
❌ **Not Relational** - No `analytics_relationship_service.py`
❌ **Not Write-Heavy** - Only generates and optionally stores markdown files
❌ **Not Prescriptive** - Contains ONLY metrics, no AI recommendations

---

## Architecture: 4-Service Facade Pattern

### AnalyticsService (Facade)

**Location:** `/core/services/analytics_service.py` (~683 lines)

**Responsibilities:**
1. Orchestrate analytics generation across all domains
2. Delegate to specialized sub-services
3. Handle markdown rendering and file storage
4. Handle event-driven analytics generation (Phase 4)
5. Maintain backward compatibility

**Key Dependencies:** Takes ALL domain services as constructor parameters
```python
def __init__(
    self,
    tasks_service=None,        # Layer 1
    habits_service=None,       # Layer 1
    goals_service=None,        # Layer 1
    events_service=None,       # Layer 1
    finance_service=None,      # Layer 1
    choices_service=None,      # Layer 1
    principle_service=None,    # Layer 1
    content_enrichment=None, # Layer 2 (ContentEnrichmentService)
    user_service=None,         # Layer 3
    ku_service=None,           # Layer 0
    lp_service=None,           # Layer 0
    analytics_dir: Path | None = None,
    event_bus=None,            # Event-driven analytics generation
)
```

### AnalyticsMetricsService

**Location:** `/core/services/analytics/analytics_metrics_service.py` (~1168 lines)

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
- **Knowledge (Layer 0):** substance_scores, mastery_levels, decay_warnings
- **Journals (Layer 2):** reflection_frequency, theme_analysis, metacognition_score

### AnalyticsAggregationService

**Location:** `/core/services/analytics/analytics_aggregation_service.py` (~570 lines)

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

**Location:** `/core/services/analytics/analytics_life_path_service.py` (~500 lines)

**Responsibilities:**
- Calculate life path alignment (Layer 3 metric)
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

**From `AnalyticsDomain` enum (`core/models/enums/`):**

| AnalyticsDomain | Domain Queried | Key Metrics |
|-----------------|----------------|-------------|
| `TASKS` | Tasks | completion_rate, overdue_count, priority_distribution |
| `HABITS` | Habits | current_streaks, consistency_score, completion_rate |
| `GOALS` | Goals | on_track_count, at_risk_count, progress_percentage |
| `EVENTS` | Events | total_count, completion_rate, time_distribution |
| `FINANCE` | Finance | total_expenses, category_breakdown, budget_variance |
| `CHOICES` | Choices | total_count, domain_distribution, outcome_analysis |
| `PRINCIPLES` | Principles | total_principles, avg_strength, alignment_score |

**Note:** No `ANALYTICS` or `JOURNALS` analytics domain types (yet). Journals are used IN analytics (via AnalyticsMetricsService) but don't generate standalone analytics.

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
AnalyticsPure (frozen domain model)
    ↓ render (optional)
Markdown File (stored in /data/analytics/)
```

**Critical:** Analytics NEVER writes to domain services - strictly read-only.

---

## Why Analytics Has No Relationship Service

**Reason:** Analytics doesn't create relationships. It consumes them.

**Contrast with other domains:**
- **Tasks** → Has `tasks_relationship_service.py` - creates DEPENDS_ON, CONTRIBUTES_TO_GOAL edges
- **Goals** → Has `goals_relationship_service.py` - creates SUPPORTS, REQUIRES edges
- **Analytics** → NO relationship service - only reads existing edges for statistics

**Example:**
```python
# TasksRelationshipService (writes relationships)
await tasks_rel.link_task_to_goal(task_uid, goal_uid, contribution=0.3)

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

## Calendar Integration Opportunity

### Current State: NO Integration

Calendar service does NOT reference Analytics service.

### Opportunity: Scheduled Analytics Generation

**Use Case:** User wants weekly habit analytics every Monday 9am

**Implementation Pattern:**
```python
# EventsService creates scheduled event
event = Event(
    uid="event.analytics_habits_weekly",
    title="Generate Weekly Habit Analytics",
    event_type=EventType.ANALYTICS_GENERATION,
    recurrence_pattern=RecurrencePattern.WEEKLY,
    time_of_day=TimeOfDay.MORNING,
    metadata={
        "analytics_domain": "HABITS",
        "period": "weekly",
        "user_uid": user_uid
    }
)

# CalendarService triggers on event completion
if event.event_type == EventType.ANALYTICS_GENERATION:
    await analytics_service.generate_analytics(
        user_uid=event.metadata["user_uid"],
        analytics_domain=event.metadata["analytics_domain"],
        period_start=week_start,
        period_end=week_end
    )
```

**Benefits:**
1. Scheduled analytics generation (weekly, monthly, quarterly)
2. User-configured analytics times (morning review, evening reflection)
3. Analytics history via calendar events
4. Cross-domain integration (calendar triggers analytics)

**Note:** This integration does NOT exist yet - it's a design opportunity.

---

## Architectural Patterns

### 1. Meta-Service (Not a Domain)

Analytics sits ABOVE the domain layer:

```
Layer 3: Life Path (user_service)
Layer 2: Pipeline (journals_service)
Layer 1: Activity (tasks, habits, goals, events, finance, choices, principles)
Layer 0: Curriculum (ku_service, lp_service, ls_service)

                    ↓ reads from all layers ↓

            AnalyticsService (Meta-Layer)
```

### 2. Facade Pattern (4 Sub-Services)

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

### AnalyticsPure (Domain Model)

**Location:** `/core/models/analytics/analytics.py`

```python
@dataclass(frozen=True)
class AnalyticsPure:
    uid: str
    user_uid: str
    analytics_domain: AnalyticsDomain
    period_start: date
    period_end: date
    metrics: dict[str, Any]  # Quantitative data ONLY
    generated_at: datetime
    title: str
    markdown_content: str
    metadata: dict[str, Any]
```

**Key Methods:**
- `get_metric(key, default)` - Safe metric retrieval
- `get_period_days()` - Calculate analytics period length
- `is_current_period()` - Check if analytics covers today
- `format_period()` - Human-readable period string

### AnalyticsDTO (Transfer Layer)

Mutable version for construction and persistence.

### No Pydantic Models

Analytics doesn't have external API validation models - generated internally only.

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

### 3. Why NO Domain.ANALYTICS Enum Value?

**Rationale:**
- Analytics is not a domain - it's a meta-service
- Domain enum is for entity types (tasks, habits, goals)
- Analytics doesn't have entities
- Including would confuse domain-based routing

---

## Future Enhancements

### 1. Calendar Integration (High Priority)

**Feature:** Scheduled analytics generation via calendar events

**Benefits:**
- Automated weekly/monthly analytics
- User-configured delivery times
- Analytics history via calendar

**Effort:** Medium (4-6 hours)

### 2. Analytics Subscriptions

**Feature:** User-configured automatic analytics delivery

**Implementation:**
```python
class AnalyticsSubscription:
    user_uid: str
    analytics_domain: AnalyticsDomain
    frequency: RecurrencePattern  # DAILY, WEEKLY, MONTHLY
    delivery_time: TimeOfDay
    delivery_method: str  # "email", "calendar", "dashboard"
```

**Effort:** Medium-High (8-12 hours)

### 3. Historical Analytics Comparison

**Feature:** Compare current metrics to historical analytics

**Benefits:**
- Trend analysis
- Progress visualization
- Pattern detection

**Effort:** Medium (6-8 hours)

### 4. Analytics Caching (Low Priority)

**Feature:** Cache frequently-requested analytics

**Consideration:** May violate "fresh data" principle

**Effort:** Low (2-4 hours)

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
| ContentEnrichment | Reflection patterns | Direct Journal node query |
| KuService | Knowledge mastery | `list_by_user(user_uid, limit)` |
| LpService | Learning path progress | `list_by_user(user_uid, limit)` |

### Services That COULD Consume Analytics (Future)

| Service | Use Case | Integration Method |
|---------|----------|-------------------|
| CalendarService | Scheduled generation | Trigger on calendar event |
| UserService | Dashboard widgets | Include recent analytics in context |
| EmailService | Automated delivery | Send analytics markdown via email |

---

## Testing Strategy

### Unit Tests

Test each sub-service independently:
- `test_analytics_metrics_service.py` - Domain metric calculations
- `test_analytics_aggregation_service.py` - Cross-domain synthesis
- `test_analytics_life_path_service.py` - Alignment tracking

### Integration Tests

Test full analytics generation:
- Mock domain services with known data
- Verify calculated metrics
- Check markdown rendering

### Performance Tests

Analytics queries many services:
- Measure total generation time
- Identify slow domain queries
- Optimize aggregation logic

---

## Migration Notes

**No migration needed** - Analytics service is already well-architected as a meta-service.

**Recommended enhancements:**
1. Add Calendar integration
2. Document unique distinction (this file)
3. Add analytics subscription system

---

## Conclusion

Analytics is SKUEL's **statistical compiler** - a meta-layer service that aggregates data from all domains to provide quantitative assessments. Its unique characteristics:

- ✅ Reads from ALL domains
- ✅ Generates ephemeral metrics
- ✅ Spans ALL layers (0-3)
- ❌ NOT a domain
- ❌ NO graph storage
- ❌ NO relationship service
- ❌ NO write operations

**Philosophy:** "Listen and respond" - provide data when asked, never push advice.

---

**Documented By:** Claude Code
**Date:** January 20, 2026
**Version:** 1.1.0
**Next Review:** When Calendar integration is implemented
