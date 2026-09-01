---
updated: 2026-07-27
---

# TasksIntelligenceService - Behavioral & Performance Intelligence

## Overview

**Architecture:** Shell delegates to focused mixins (April–June 2026); graph context
retrieval (`get_with_context`, mechanism B) comes from the shared
`core/services/intelligence/_CoreIntelligenceMixin`:
- `_analytics_mixin.py` (~255 lines) — `get_behavioral_insights`, completion patterns, success factors
- `_productivity_mixin.py` (~187 lines) — `analyze_learning_patterns`, `calculate_knowledge_aware_priorities`, `generate_task_insights`, `track_knowledge_mastery_progression`; delegates to `TaskKnowledgeAnalyzer` (`/core/services/tasks/task_knowledge_analyzer.py`). Routes: `GET /api/tasks/knowledge-patterns`, `GET /api/tasks/knowledge-priorities` (live since #367)
- `_dual_track_mixin.py` — `assess_productivity_dual_track` (ADR-030 perception gap; the 6th dual-track engine, added #259)

```python
class TasksIntelligenceService(
    _CoreIntelligenceMixin,    # shared: get_with_context (mechanism B)
    _AnalyticsMixin,           # behavioral + performance analytics
    _ProductivityMixin,        # TaskKnowledgeAnalyzer delegation
    _DualTrackMixin,           # assess_productivity_dual_track (ADR-030)
    BaseAnalyticsService["TasksOperations", Task],
):
    """Shell: __init__ + get_performance_analytics + get_domain_insights only."""
```

**Location:** `/core/services/tasks/tasks_intelligence_service.py`
**Service Name:** `tasks.intelligence`
**Lines:** ~265 (shell) — see mixin files above for the bulk of logic

**Dual-track productivity assessment (ADR-030):** lives in `_dual_track_mixin.py`
(`assess_productivity_dual_track` + a real system calculator) — NOT a standalone service.
The former `TasksProductivityService` (`tasks_productivity_service.py`) was shelved 2026-03-28
and never existed as a live file; #259 wired the dual-track engine to `GET /self-checkin`.

**Related sub-services:**
- `ActivityKnowledgeIntelligenceService` (`/core/services/knowledge/`) — domain-agnostic knowledge intelligence (suggestions, prerequisites, learning opportunities) extracted from Tasks and wired into all 6 activity domain facades as `self.knowledge_intelligence`

**April 2026 — symmetry refactor:** `TasksLearningMetricsService` was retired. Its two methods (`analyze_task_learning_metrics`, `generate_task_knowledge_insights`) were folded back into `TasksIntelligenceService` via `_productivity_mixin`, where they belong as task-level analytics alongside `analyze_learning_patterns` and `track_knowledge_mastery_progression`. The old name created false parity with peer domains' `*LearningService` (which handle learning-path integration, a different concern) — retiring it restores the sub-service taxonomy to a single shared meaning across all 6 Activity Domains.

**Related:** `TaskEventHandlerService` (`/core/services/tasks/task_event_handler_service.py`) — fire-and-forget reactive handlers extracted from intelligence; persists `COMPLETION_PATTERN`, `IMBALANCE_DETECTED`, and `PRINCIPLE_ALIGNMENT` insights to InsightStore (March 2026).

---

## Purpose

TasksIntelligenceService provides task-specific behavioral insights, performance analytics, and cross-domain context categorization. Domain-agnostic knowledge intelligence (knowledge suggestions, prerequisites, learning opportunities) was extracted to `ActivityKnowledgeIntelligenceService` (March 2026) — those methods work for all 6 activity domains, not just Tasks.

---

## Core Methods

> **Extracted (March 2026):** `get_knowledge_suggestions()`, `generate_knowledge_from_entities()`, `get_knowledge_prerequisites()`, and `get_learning_opportunities()` were moved to `ActivityKnowledgeIntelligenceService` (`/core/services/knowledge/`) and wired into all 6 activity domain facades. Access via `facade.get_knowledge_suggestions(user_uid)` on any activity service.

### Method 1: get_behavioral_insights()

**Purpose:** Analyze behavioral patterns from task completion data, including time-of-day patterns, procrastination indicators, and context productivity.

**Signature:**
```python
async def get_behavioral_insights(
    self,
    user_uid: UserUID,
    period_days: int = 90
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `period_days` (int, default=90) - Period to analyze

**Returns:**
```python
{
    "behavior_patterns": [
        {
            "pattern": "peak_productivity",
            "description": "Most tasks completed around 9:00",
            "confidence": 0.7
        }
    ],
    "success_factors": [
        "High priority focus drives completion",
        "Detailed task descriptions improve completion"
    ],
    "recommendations": [
        "Schedule high-priority tasks during your peak hours: Most tasks completed around 9:00",
        "Continue adding detailed descriptions to tasks"
    ],
    "metadata": {
        "generated_at": "2026-01-08T10:00:00",
        "user_uid": "user.mike",
        "period_days": 90,
        "tasks_analyzed": 67
    }
}
```

**Example:**
```python
# Analyze last 90 days
result = await tasks_service.intelligence.get_behavioral_insights(
    user_uid="user.mike",
    period_days=90
)

if result.is_ok:
    data = result.value
    print("Behavioral Patterns:")
    for pattern in data["behavior_patterns"]:
        print(f"  - {pattern['description']}")

    print("\nRecommendations:")
    for rec in data["recommendations"]:
        print(f"  - {rec}")
```

**Dependencies:** TasksOperations backend (REQUIRED)

---

### Method 2: get_performance_analytics()

**Purpose:** Analyze task performance metrics including completion rate trends, average completion time, priority distribution, and efficiency patterns.

**Signature:**
```python
async def get_performance_analytics(
    self,
    user_uid: UserUID,
    period_days: int = 30
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `period_days` (int, default=30) - Period to analyze

**Returns:**
```python
{
    "metrics": {
        "total_tasks": 45,
        "completed_tasks": 38,
        "completion_rate": 84.4,
        "in_progress_tasks": 5,
        "overdue_tasks": 2
    },
    "trends": {
        "completion_trend": "excellent",
        "efficiency_trend": "stable",
        "quality_trend": "stable",
        "completion_rate": 84.4,
        "tasks_analyzed": 45
    },
    "optimization_opportunities": [
        {
            "area": "deadline_management",
            "suggestion": "Review and adjust deadlines based on actual completion times",
            "potential_impact": "Reduced stress and more realistic planning"
        }
    ],
    "metadata": {
        "generated_at": "2026-01-08T10:00:00",
        "user_uid": "user.mike",
        "period_days": 30
    }
}
```

**Example:**
```python
result = await tasks_service.intelligence.get_performance_analytics(
    user_uid="user.mike",
    period_days=30
)

if result.is_ok:
    data = result.value
    print(f"Completion Rate: {data['metrics']['completion_rate']}%")
    print(f"Trend: {data['trends']['completion_trend']}")

    print("\nOptimization Opportunities:")
    for opp in data["optimization_opportunities"]:
        print(f"  {opp['area']}: {opp['suggestion']}")
```

**Dependencies:** TasksOperations backend (REQUIRED)

---

### Method 3: cross-domain block in `get_domain_insights()`

**Purpose:** `get_domain_insights` (GET `/api/tasks/insights`) composes TWO sources — Task's
distinctive **readiness** lens (graph-intel `get_knowledge_prerequisites` →
`knowledge_prerequisites` / `has_prerequisites`, plus task-field `insights`) AND an additive
path-aware **cross-domain** block over the CANONICAL typed reader.

The cross-domain block is built by `_build_cross_domain_block`, which runs
`BaseAnalyticsService._analyze_entity_with_typed_context` over
`get_cross_domain_context_typed` → path-aware `TaskCrossContext`
(`core/models/graph/path_aware_types.py`). Scope is **cross-domain only**: required/applied
knowledge + contributing goals. Same-domain task→task dependencies (DEPENDS_ON) are owned by
the lateral-relationships system (BlockingChainView) and ZPD — they are NOT in this context.
The hand-rolled `categorize_cross_domain_context` (dead, zero callers) was deleted in the
typed-reader convergence.

**Additive shape (under the `cross_domain` key, every prior `/insights` key preserved):**
```python
{
    "available": True,            # False (empty block) on a real context-fetch error
    "context": {
        "total_connections": 4,
        "required_knowledge": ["ku.python-basics"],      # REQUIRES_KNOWLEDGE
        "applied_knowledge": ["ku.fasthtml-intro"],      # APPLIES_KNOWLEDGE
        "contributing_goals": ["goal_001"],              # CONTRIBUTES_TO_GOAL ∪ FULFILLS_GOAL
    },
    "metrics": {
        "required_knowledge_count": 1,
        "applied_knowledge_count": 1,
        "knowledge_coverage": 2,
        "goal_support_count": 1,
        "has_required_knowledge": True,
        "has_applied_knowledge": True,
        "has_goal_support": True,
        "cascade_impact": {...},          # PathAwareAnalyzer.calculate_cascade_impact
        "path_aware_context": {...},      # strong/direct counts, max depth, avg strength
    },
    "recommendations": [...],             # PathAwareAnalyzer.generate_recommendations
}
```

**Degrades gracefully:** an edge-less task yields an OK empty block (`available: True`, zeroed
counts) via the typed reader's ok-empty-context policy; a real fetch error logs and yields
`available: False` rather than failing the whole route (the readiness lens still answers).

**Additive `learning_requirements` block (#254 — shared mastery lens with Goals):**
`get_domain_insights` also returns a `learning_requirements` key built from the task's
`required_knowledge` via the shared `build_learning_requirements` helper — the same
`PrerequisiteChecker.check_prerequisites` split that drives readiness, so gaps never disagree.
When the call has a `user_context` the split is truthful; otherwise every requirement is an open
gap. Shape = the `LearningRequirements` TypedDict (`knowledge_requirements` / `learning_paths` /
`learning_analysis` blocks — see [PREREQUISITE_CHECKER_PATTERN.md](/docs/patterns/PREREQUISITE_CHECKER_PATTERN.md)).
Note: `ContextualTask` carries the same field, but the daily-plan UI renders it for **goals only**
(actionable tasks are pre-filtered to ready), so this block is for non-UI consumers + `to_dict`.

**Backing functions:** `calculate_task_cross_domain_metrics` + `task_recommendations`
(`core/services/intelligence/metrics_calculators.py`); `build_learning_requirements`
(`core/services/infrastructure/prerequisite_checker.py`).

---

### Method 4: assess_productivity_dual_track() (ADR-030)

> **Location:** `_dual_track_mixin.py` (`_DualTrackMixin`), mixed into `TasksIntelligenceService`.
> Access via `tasks_service.intelligence.assess_productivity_dual_track(...)`. Wired to
> `GET /self-checkin` in #259 (ADR-030 v1).

**Purpose:** Compare user's self-assessed productivity level with system-measured productivity metrics, generating perception gap analysis and personalized insights.

**Signature:**
```python
async def assess_productivity_dual_track(
    self,
    user_uid: UserUID,
    user_productivity_level: ProductivityLevel,
    user_evidence: str,
    user_reflection: str | None = None,
    period_days: int = 30,
) -> Result[DualTrackResult[ProductivityLevel]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `user_productivity_level` (ProductivityLevel) - User's self-assessed level
- `user_evidence` (str) - User's evidence for their assessment
- `user_reflection` (str, optional) - User's optional reflection
- `period_days` (int, default=30) - Period to analyze for system calculation

**Returns:**
```python
DualTrackResult[ProductivityLevel](
    entity_uid="user.mike",
    entity_type="productivity_assessment",

    # USER-DECLARED (Vision)
    user_level=ProductivityLevel.PRODUCTIVE,
    user_score=0.775,
    user_evidence="I complete most tasks on time",
    user_reflection="Feeling good about my productivity",

    # SYSTEM-CALCULATED (Action)
    system_level=ProductivityLevel.MODERATELY_PRODUCTIVE,
    system_score=0.58,
    system_evidence=(
        "Completion rate: 58%",
        "On-time rate: 62%",
        "Overdue ratio: 22%",
        "Knowledge linking: 35%",
    ),

    # GAP ANALYSIS
    perception_gap=0.195,
    gap_direction="user_higher",

    # INSIGHTS
    insights=("Self-assessment exceeds measured productivity by ~20%",),
    recommendations=("Focus on reducing overdue tasks", "Increase task completion rate"),
)
```

**ProductivityLevel Enum:**
```python
class ProductivityLevel(str, Enum):
    HIGHLY_PRODUCTIVE = "highly_productive"    # 0.85+
    PRODUCTIVE = "productive"                   # 0.70-0.85
    MODERATELY_PRODUCTIVE = "moderately_productive"  # 0.50-0.70
    STRUGGLING = "struggling"                   # 0.30-0.50
    UNPRODUCTIVE = "unproductive"              # <0.30

    def to_score(self) -> float: ...
    @classmethod
    def from_score(cls, score: float) -> "ProductivityLevel": ...
```

**System Metrics Used:**
- Completion rate (tasks completed / total tasks)
- On-time rate (tasks completed before due date / completed)
- Overdue ratio (overdue tasks / total tasks)
- Knowledge linking (tasks with knowledge / total tasks)

**Example:**
```python
result = await tasks_service.intelligence.assess_productivity_dual_track(
    user_uid="user.mike",
    user_productivity_level=ProductivityLevel.HIGHLY_PRODUCTIVE,
    user_evidence="I complete all my tasks on time",
    user_reflection="I feel very productive lately",
    period_days=30,
)

if result.is_ok:
    assessment = result.value
    print(f"User level: {assessment.user_level.value}")
    print(f"System level: {assessment.system_level.value}")
    print(f"Perception gap: {assessment.perception_gap:.0%}")
    print(f"Gap direction: {assessment.gap_direction}")

    if assessment.has_perception_gap():
        print("\nInsights:")
        for insight in assessment.insights:
            print(f"  - {insight}")

        print("\nRecommendations:")
        for rec in assessment.recommendations:
            print(f"  - {rec}")
```

**Dependencies:**
- TasksOperations backend (REQUIRED)
- Uses `BaseAnalyticsService._dual_track_assessment()` template

**API Endpoint:**
```
POST /api/tasks/assess-productivity
```

**See:** [ADR-030: Dual-Track Assessment Pattern](../decisions/ADR-030-dual-track-assessment-pattern.md)

---

## BaseAnalyticsService Features

### Inherited Infrastructure

**Fail-Fast Validation:**

**Standard Attributes:**
- `self.backend` - TasksOperations (REQUIRED)
- `self.graph_intel` - GraphIntelligenceService (optional, validated on use)
- `self.relationships` - UnifiedRelationshipService (optional)
- `self.event_bus` - EventBus (optional)

**NOTE:** Analytics services explicitly DO NOT have `embeddings` or `llm` attributes. This is intentional - they work without AI dependencies.

**Logging:**
```python
self.logger.info("Message")  # Logs to: skuel.analytics.tasks.analytics
```

---

## Integration with TasksService

### Facade Access

```python
# TasksService creates intelligence internally
tasks_service = TasksService(
    backend=tasks_backend,
    graph_intel=graph_intelligence,
    embeddings_service=embeddings_service,
    llm_service=llm_service,
    event_bus=event_bus,
    user_service=user_service,
)

# Access via .intelligence attribute
result = await tasks_service.intelligence.get_behavioral_insights(
    user_uid="user.mike",
    period_days=90
)
```

---

## Domain-Specific Features

### Cross-Domain Context Categorization

Unique among intelligence services, TasksIntelligenceService provides **semantic categorization** of graph relationships:
- Distinguishes `->DEPENDS_ON` (prerequisites) from `<-DEPENDS_ON` (dependents)
- Separates `REQUIRES_KNOWLEDGE` (learning needs) from `APPLIES_KNOWLEDGE` (knowledge application)
- Groups `FULFILLS_GOAL` and `CONTRIBUTES_TO_GOAL` as contributing goals

This categorization enables rich UI experiences without coupling backend logic to domain semantics.

---

## Testing

### Unit Tests
```bash
uv run python -m pytest tests/unit/services/test_tasks_intelligence_service.py -v
```

### Integration Tests
```bash
# Test with real backend
uv run python -m pytest tests/integration/intelligence/test_tasks_intelligence.py -v

# Test specific method
uv run python -m pytest tests/integration/intelligence/ -k "test_get_knowledge_suggestions" -v
```

### Example Test
```python
from unittest.mock import Mock
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService

# Create mock backend
backend = Mock()
graph_intel = Mock()

# Instantiate service
service = TasksIntelligenceService(
    backend=backend,
    graph_intel=graph_intel
)

# Verify initialization
assert service._service_name == "tasks.intelligence"
assert service.backend == backend
assert service.graph_intel == graph_intel
```

---

## See Also

- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` - Master index
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - Base service pattern (now BaseAnalyticsService)
- `/core/services/base_analytics_service.py` - Base implementation (NO AI deps)
- `/core/services/tasks/tasks_service.py` - TasksService facade
- `/core/utils/intelligence_queries.py` - Shared intelligence utilities (Phase 2)
