---
title: Reports Architecture - Statistical Aggregation Meta-Service
updated: 2026-01-20
status: current
category: architecture
tags: [architecture, reports]
related: []
---

# Reports Architecture - Statistical Aggregation Meta-Service
**Date:** January 20, 2026
**Type:** Architectural Documentation
**Status:** ✅ ACTIVE

## Executive Summary

**Reports is NOT a domain** - it's a **meta-layer statistical aggregation service** that reads from multiple domains to generate quantitative assessments.

**Key Distinction:** Unlike all other SKUEL domains (tasks, goals, habits, etc.), Reports:
- Does NOT store entities in the graph
- Does NOT create relationships
- Does NOT have a relationship service
- Is purely READ-ONLY (aggregates existing data)
- Spans ALL layers (0, 1, 2, 3) and ALL domains

---

## The Unique Nature of Reports

### What Reports IS

**Reports is a statistical compiler** - it queries multiple domain services, aggregates their data, and generates quantitative metrics.

```
User Activity Across Domains
    ↓
Reports Service (Facade Pattern)
    ├── ReportMetricsService → Query domain services
    ├── ReportAggregationService → Synthesize cross-domain data
    └── ReportLifePathService → Track life path alignment
    ↓
Statistical Metrics (NOT graph entities)
```

**Philosophy:** "Listen and respond" - SKUEL provides data when asked, never pushes advice.

### What Reports is NOT

❌ **Not a Domain** - Not in `Domain` enum (no `Domain.REPORTS`)
❌ **Not a Graph Entity** - No `Report` nodes stored in Neo4j
❌ **Not Relational** - No `report_relationship_service.py`
❌ **Not Write-Heavy** - Only generates and optionally stores markdown files
❌ **Not Prescriptive** - Contains ONLY metrics, no AI recommendations

---

## Architecture: 4-Service Facade Pattern

### ReportService (Facade)

**Location:** `/core/services/report_service.py` (~683 lines)

**Responsibilities:**
1. Orchestrate report generation across all domains
2. Delegate to specialized sub-services
3. Handle markdown rendering and file storage
4. Handle event-driven report generation (Phase 4)
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
    transcript_processor=None, # Layer 2 (TranscriptProcessorService)
    user_service=None,         # Layer 3
    ku_service=None,           # Layer 0
    lp_service=None,           # Layer 0
    report_dir: Path | None = None,
    event_bus=None,            # Event-driven report generation
)
```

### ReportMetricsService

**Location:** `/core/services/reports/report_metrics_service.py` (~1168 lines)

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

### ReportAggregationService

**Location:** `/core/services/reports/report_aggregation_service.py` (~570 lines)

**Responsibilities:**
- Cross-domain synthesis (Life Reports)
- Detect patterns across multiple domains
- Generate weekly/monthly/quarterly/yearly summaries

**Methods:**
- `aggregate_weekly_life_summary()`
- `aggregate_monthly_life_review()`
- `aggregate_quarterly_progress()`
- `aggregate_yearly_review()`
- `detect_cross_domain_patterns()`

### ReportLifePathService

**Location:** `/core/services/reports/report_life_path_service.py` (~500 lines)

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

## Report Types and Domains Covered

**From `ReportType` enum (shared_enums.py):**

| ReportType | Domain Queried | Key Metrics |
|------------|----------------|-------------|
| `TASKS` | Tasks | completion_rate, overdue_count, priority_distribution |
| `HABITS` | Habits | current_streaks, consistency_score, completion_rate |
| `GOALS` | Goals | on_track_count, at_risk_count, progress_percentage |
| `EVENTS` | Events | total_count, completion_rate, time_distribution |
| `FINANCE` | Finance | total_expenses, category_breakdown, budget_variance |
| `CHOICES` | Choices | total_count, domain_distribution, outcome_analysis |
| `PRINCIPLES` | Principles | total_principles, avg_strength, alignment_score |

**Note:** No `REPORTS` or `JOURNALS` report types (yet). Journals are used IN reports (via ReportMetricsService) but don't generate standalone reports.

---

## Data Flow: Read-Only Aggregation

```
Domain Services (Source of Truth)
    ↓ read
ReportMetricsService
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
ReportPure (frozen domain model)
    ↓ render (optional)
Markdown File (stored in /data/reports/)
```

**Critical:** Reports NEVER write to domain services - strictly read-only.

---

## Why Reports Has No Relationship Service

**Reason:** Reports don't create relationships. They consume them.

**Contrast with other domains:**
- **Tasks** → Has `tasks_relationship_service.py` - creates DEPENDS_ON, CONTRIBUTES_TO_GOAL edges
- **Goals** → Has `goals_relationship_service.py` - creates SUPPORTS, REQUIRES edges
- **Reports** → NO relationship service - only reads existing edges for statistics

**Example:**
```python
# TasksRelationshipService (writes relationships)
await tasks_rel.link_task_to_goal(task_uid, goal_uid, contribution=0.3)

# ReportMetricsService (reads relationships for metrics)
tasks_for_goal = await tasks_service.get_tasks_for_goal(goal_uid)
completion_rate = calculate_completion(tasks_for_goal)
```

---

## Reports and the Graph

Reports interact with the graph in a unique way:

### What Reports Query

Reports query graph relationships to calculate metrics:
- Task completion rates (via CONTRIBUTES_TO_GOAL edges)
- Goal dependencies (via DEPENDS_ON edges)
- Knowledge application (via APPLIES_KNOWLEDGE edges)
- Life path alignment (via cross-domain edge traversal)

### What Reports Store

**Option 1:** Nothing (ephemeral)
- Report generated on-demand
- Returned to client
- No persistence

**Option 2:** Markdown files (optional)
- Stored in `/data/reports/`
- File-based, NOT in Neo4j
- Used for historical reference

**Reports are NEVER stored as nodes in Neo4j.**

---

## Calendar Integration Opportunity

### Current State: NO Integration

Calendar service does NOT reference Reports service.

### Opportunity: Scheduled Report Generation

**Use Case:** User wants weekly habit report every Monday 9am

**Implementation Pattern:**
```python
# EventsService creates scheduled event
event = Event(
    uid="event.report_habits_weekly",
    title="Generate Weekly Habit Report",
    event_type=EventType.REPORT_GENERATION,
    recurrence_pattern=RecurrencePattern.WEEKLY,
    time_of_day=TimeOfDay.MORNING,
    metadata={
        "report_type": "HABITS",
        "period": "weekly",
        "user_uid": user_uid
    }
)

# CalendarService triggers on event completion
if event.event_type == EventType.REPORT_GENERATION:
    await report_service.generate_report(
        user_uid=event.metadata["user_uid"],
        report_type=event.metadata["report_type"],
        period_start=week_start,
        period_end=week_end
    )
```

**Benefits:**
1. Scheduled report generation (weekly, monthly, quarterly)
2. User-configured report times (morning review, evening reflection)
3. Report history via calendar events
4. Cross-domain integration (calendar triggers reports)

**Note:** This integration does NOT exist yet - it's a design opportunity.

---

## Architectural Patterns

### 1. Meta-Service (Not a Domain)

Reports sits ABOVE the domain layer:

```
Layer 3: Life Path (user_service)
Layer 2: Pipeline (journals_service)
Layer 1: Activity (tasks, habits, goals, events, finance, choices, principles)
Layer 0: Curriculum (ku_service, lp_service, ls_service)

                    ↓ reads from all layers ↓

            ReportService (Meta-Layer)
```

### 2. Facade Pattern (4 Sub-Services)

```
ReportService (Facade)
├── ReportMetricsService (domain-specific metrics)
├── ReportAggregationService (cross-domain synthesis)
└── ReportLifePathService (life path alignment)
```

### 3. Read-Only Aggregation

Reports ONLY read, NEVER write:
- ✅ Query domain services
- ✅ Aggregate data
- ✅ Calculate metrics
- ❌ Create entities
- ❌ Modify data
- ❌ Create relationships

### 4. Stateless Generation

Reports are generated on-demand:
- No cached state
- Fresh data each time
- No stale metrics

---

## Model Layer

### ReportPure (Domain Model)

**Location:** `/core/models/report/report.py`

```python
@dataclass(frozen=True)
class ReportPure:
    uid: str
    user_uid: str
    report_type: ReportType
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
- `get_period_days()` - Calculate report period length
- `is_current_period()` - Check if report covers today
- `format_period()` - Human-readable period string

### ReportDTO (Transfer Layer)

Mutable version for construction and persistence.

### No Pydantic Models

Reports don't have external API validation models - generated internally only.

---

## Key Design Decisions

### 1. Why NOT Store Reports in Neo4j?

**Rationale:**
- Reports are derived data (not source of truth)
- Storing would create duplication
- Graph queries would be slower than recomputing
- No relationships to other entities (no graph value)

**Alternative:** File-based storage for historical reference

### 2. Why NO Report Relationship Service?

**Rationale:**
- Reports don't create relationships
- Reports consume relationships for metrics
- No cross-domain edges involving reports
- Reports are ephemeral statistical views

### 3. Why NO Domain.REPORTS Enum Value?

**Rationale:**
- Reports are not a domain - they're a meta-service
- Domain enum is for entity types (tasks, habits, goals)
- Reports don't have entities
- Including would confuse domain-based routing

---

## Future Enhancements

### 1. Calendar Integration (High Priority)

**Feature:** Scheduled report generation via calendar events

**Benefits:**
- Automated weekly/monthly reports
- User-configured delivery times
- Report history via calendar

**Effort:** Medium (4-6 hours)

### 2. Report Subscriptions

**Feature:** User-configured automatic report delivery

**Implementation:**
```python
class ReportSubscription:
    user_uid: str
    report_type: ReportType
    frequency: RecurrencePattern  # DAILY, WEEKLY, MONTHLY
    delivery_time: TimeOfDay
    delivery_method: str  # "email", "calendar", "dashboard"
```

**Effort:** Medium-High (8-12 hours)

### 3. Historical Report Comparison

**Feature:** Compare current metrics to historical reports

**Benefits:**
- Trend analysis
- Progress visualization
- Pattern detection

**Effort:** Medium (6-8 hours)

### 4. Report Caching (Low Priority)

**Feature:** Cache frequently-requested reports

**Consideration:** May violate "fresh data" principle

**Effort:** Low (2-4 hours)

---

## Integration Points

### Services That PROVIDE Data to Reports

| Service | Data Provided | Query Method |
|---------|---------------|--------------|
| TasksService | Task completions, statuses | `get_user_items_in_range(user_uid, dates)` |
| HabitsService | Habit streaks, completions | `get_user_items_in_range(user_uid, dates)` |
| GoalsService | Goal progress, milestones | `get_user_items_in_range(user_uid, dates)` |
| EventsService | Event completions, schedules | `get_user_items_in_range(user_uid, dates)` |
| FinanceService | Expenses, budgets | `get_user_items_in_range(user_uid, dates)` |
| ChoicesService | Decisions, outcomes | `get_user_items_in_range(user_uid, dates)` |
| PrincipleService | Principle strength, alignment | `get_user_items_in_range(user_uid, dates)` |
| TranscriptProcessor | Reflection patterns | Direct Journal node query |
| KuService | Knowledge mastery | `list_by_user(user_uid, limit)` |
| LpService | Learning path progress | `list_by_user(user_uid, limit)` |

### Services That COULD Consume Reports (Future)

| Service | Use Case | Integration Method |
|---------|----------|-------------------|
| CalendarService | Scheduled generation | Trigger on calendar event |
| UserService | Dashboard widgets | Include recent reports in context |
| EmailService | Automated delivery | Send report markdown via email |

---

## Testing Strategy

### Unit Tests

Test each sub-service independently:
- `test_report_metrics_service.py` - Domain metric calculations
- `test_report_aggregation_service.py` - Cross-domain synthesis
- `test_report_life_path_service.py` - Alignment tracking

### Integration Tests

Test full report generation:
- Mock domain services with known data
- Verify calculated metrics
- Check markdown rendering

### Performance Tests

Reports query many services:
- Measure total generation time
- Identify slow domain queries
- Optimize aggregation logic

---

## Migration Notes

**No migration needed** - Reports service is already well-architected as a meta-service.

**Recommended enhancements:**
1. Add Calendar integration
2. Document unique distinction (this file)
3. Add report subscription system

---

## Conclusion

Reports is SKUEL's **statistical compiler** - a meta-layer service that aggregates data from all domains to provide quantitative assessments. Its unique characteristics:

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
