# TasksIntelligenceService - Knowledge Generation & Learning Discovery

## Overview

**Architecture:** Extends `BaseAnalyticsService[TasksOperations, Task]` (NO AI dependencies)
**Location:** `/core/services/tasks/tasks_intelligence_service.py`
**Service Name:** `tasks.intelligence`
**Lines:** ~1459

---

## Purpose

TasksIntelligenceService transforms task patterns into actionable knowledge and learning opportunities. It analyzes completed tasks to extract best practices, identify skill gaps, discover behavioral patterns, and generate performance insights.

---

## Core Methods

### Method 1: get_knowledge_suggestions()

**Purpose:** Generate knowledge suggestions from task patterns by analyzing frequent task types, problem-solving approaches, and skills used.

**Signature:**
```python
async def get_knowledge_suggestions(
    self,
    user_uid: str,
    entity_uid: str | None = None
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `entity_uid` (str, optional) - Specific task UID to analyze (if None, analyzes all completed tasks)

**Returns:**
```python
{
    "task_patterns": [
        {
            "pattern": "debugging",
            "knowledge_suggestion": "Create knowledge unit for debugging",
            "confidence": 0.85,
            "frequency": 12
        }
    ],
    "learning_opportunities": [
        "Error handling patterns from repeated bug fixes",
        "API integration best practices"
    ],
    "knowledge_gaps": [
        "Testing strategies",
        "Performance optimization",
        "Security best practices"
    ],
    "metadata": {
        "generated_at": "2026-01-08T10:00:00",
        "user_uid": "user.mike",
        "tasks_analyzed": 45,
        "scope": "all_user_tasks"
    }
}
```

**Example:**
```python
# Analyze all completed tasks
result = await tasks_service.intelligence.get_knowledge_suggestions(user_uid)
if result.is_ok:
    data = result.value
    for pattern in data["task_patterns"]:
        print(f"Pattern: {pattern['pattern']} (confidence: {pattern['confidence']})")

# Analyze specific task
result = await tasks_service.intelligence.get_knowledge_suggestions(
    user_uid="user.mike",
    entity_uid="task_001"
)
```

**Dependencies:** TasksOperations backend (REQUIRED)

---

### Method 2: generate_knowledge_from_entities()

**Purpose:** Generate proposed knowledge units from completed tasks over a specified time period, extracting best practices and documentation suggestions.

**Signature:**
```python
async def generate_knowledge_from_entities(
    self,
    user_uid: str,
    period_days: int = 30
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `period_days` (int, default=30) - Period to analyze in days

**Returns:**
```python
{
    "knowledge_units": [
        {
            "title": "API Integration Best Practices",
            "content": "Knowledge extracted from 8 api integration tasks",
            "source_tasks": ["task_001", "task_002", "task_003"],
            "confidence": 0.8,
            "type": "best_practice"
        }
    ],
    "patterns_discovered": ["api", "debugging", "testing"],
    "documentation_suggestions": [
        "Document api workflow and best practices",
        "Document debugging workflow and best practices"
    ],
    "metadata": {
        "generated_at": "2026-01-08T10:00:00",
        "user_uid": "user.mike",
        "period_days": 30,
        "tasks_analyzed": 23
    }
}
```

**Example:**
```python
# Generate knowledge from last 90 days
result = await tasks_service.intelligence.generate_knowledge_from_entities(
    user_uid="user.mike",
    period_days=90
)

if result.is_ok:
    data = result.value
    for ku in data["knowledge_units"]:
        print(f"Suggested KU: {ku['title']}")
        print(f"  Based on {len(ku['source_tasks'])} tasks")
        print(f"  Confidence: {ku['confidence']}")
```

**Dependencies:** TasksOperations backend (REQUIRED)

---

### Method 3: get_knowledge_prerequisites()

**Purpose:** Analyze knowledge prerequisites for a task using graph intelligence to identify required knowledge units.

**Signature:**
```python
async def get_knowledge_prerequisites(
    self,
    entity_uid: str
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `entity_uid` (str) - Task UID

**Returns:**
```python
{
    "prerequisites": [
        {
            "uid": "ku.python-basics",
            "title": "Python Basics",
            "relationship": "REQUIRES_KNOWLEDGE"
        }
    ],
    "learning_path": ["ku.python-basics", "ku.fasthtml-intro"]
}
```

**Example:**
```python
result = await tasks_service.intelligence.get_knowledge_prerequisites("task_001")
if result.is_ok:
    prereqs = result.value["prerequisites"]
    for prereq in prereqs:
        print(f"Required knowledge: {prereq['title']}")
```

**Dependencies:**
- GraphIntelligenceService (REQUIRED - uses `_require_graph_intelligence()`)
- Uses shared utility: `core.utils.intelligence_queries.get_knowledge_prerequisites()`

---

### Method 4: get_learning_opportunities()

**Purpose:** Discover learning opportunities by analyzing failed tasks, tasks taking longer than expected, tasks blocked by knowledge gaps, and successfully used skills.

**Signature:**
```python
async def get_learning_opportunities(
    self,
    user_uid: str
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `user_uid` (str) - User identifier

**Returns:**
```python
{
    "opportunities": [
        {
            "type": "knowledge_gap",
            "title": "Learn concepts for: Implement authentication",
            "task_uid": "task_001",
            "required_knowledge": ["Security Basics", "OAuth 2.0"],
            "priority": "high"
        },
        {
            "skill": "python",
            "suggestion": "Consider deepening knowledge in python",
            "source": "task_analysis"
        }
    ],
    "recommended_focus": [
        "Focus on knowledge gap (5 opportunities)",
        "Focus on skill development (3 opportunities)"
    ],
    "estimated_impact": {
        "potential_time_savings": "10 hours per week",
        "quality_improvement": "Estimated 20-40% improvement",
        "confidence_boost": "High"
    },
    "metadata": {
        "generated_at": "2026-01-08T10:00:00",
        "user_uid": "user.mike",
        "opportunities_found": 8
    }
}
```

**Example:**
```python
result = await tasks_service.intelligence.get_learning_opportunities("user.mike")
if result.is_ok:
    data = result.value
    for opp in data["opportunities"]:
        print(f"{opp['type']}: {opp.get('title', opp.get('suggestion'))}")

    print("\nRecommended focus:")
    for focus in data["recommended_focus"]:
        print(f"  - {focus}")
```

**Dependencies:**
- TasksOperations backend (REQUIRED)
- GraphIntelligenceService (optional - enhanced analysis if available)

---

### Method 5: get_behavioral_insights()

**Purpose:** Analyze behavioral patterns from task completion data, including time-of-day patterns, procrastination indicators, and context productivity.

**Signature:**
```python
async def get_behavioral_insights(
    self,
    user_uid: str,
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

### Method 6: get_performance_analytics()

**Purpose:** Analyze task performance metrics including completion rate trends, average completion time, priority distribution, and efficiency patterns.

**Signature:**
```python
async def get_performance_analytics(
    self,
    user_uid: str,
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

### Method 7: categorize_cross_domain_context()

**Purpose:** Categorize raw graph context into task-specific relationship groups (prerequisites, dependents, required knowledge, applied knowledge, contributing goals).

**Signature:**
```python
async def categorize_cross_domain_context(
    self,
    task_uid: str,
    raw_context: list[dict[str, Any]]
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `task_uid` (str) - Task UID
- `raw_context` (list[dict]) - Raw graph context from backend (list of entities with metadata)

**Returns:**
```python
{
    "task_uid": "task_001",
    "prerequisites": [
        {
            "uid": "task_000",
            "title": "Setup development environment",
            "distance": 1,
            "path_strength": 0.8,
            "via_relationships": ["->DEPENDS_ON"]
        }
    ],
    "dependents": [
        {
            "uid": "task_002",
            "title": "Deploy to production",
            "distance": 1,
            "path_strength": 0.9,
            "via_relationships": ["<-DEPENDS_ON"]
        }
    ],
    "required_knowledge": [
        {
            "uid": "ku.python-basics",
            "title": "Python Basics",
            "distance": 1,
            "path_strength": 0.7,
            "via_relationships": ["REQUIRES_KNOWLEDGE"]
        }
    ],
    "applied_knowledge": [
        {
            "uid": "ku.fasthtml-intro",
            "title": "FastHTML Introduction",
            "distance": 1,
            "path_strength": 0.85,
            "via_relationships": ["APPLIES_KNOWLEDGE"]
        }
    ],
    "contributing_goals": [
        {
            "uid": "goal_001",
            "title": "Launch MVP",
            "distance": 1,
            "path_strength": 0.9,
            "via_relationships": ["FULFILLS_GOAL"]
        }
    ]
}
```

**Example:**
```python
# Backend provides raw context
raw_context = await backend.get_domain_context_raw("task_001")

# Intelligence service categorizes it
result = await tasks_service.intelligence.categorize_cross_domain_context(
    task_uid="task_001",
    raw_context=raw_context
)

if result.is_ok:
    context = result.value
    print(f"Prerequisites: {len(context['prerequisites'])}")
    print(f"Required Knowledge: {len(context['required_knowledge'])}")
    print(f"Contributing Goals: {len(context['contributing_goals'])}")
```

**Dependencies:** None (pure categorization logic)

**Architecture Note (Phase 2B):**
- Backend provides raw graph data via `get_domain_context_raw()`
- Intelligence service performs domain-specific categorization
- Achieves true separation: Backend = primitives, Intelligence = domain logic

---

### Method 8: assess_productivity_dual_track() (ADR-030)

**Purpose:** Compare user's self-assessed productivity level with system-measured productivity metrics, generating perception gap analysis and personalized insights.

**Signature:**
```python
async def assess_productivity_dual_track(
    self,
    user_uid: str,
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
- `_require_graph_intelligence()` - Ensures graph_intel available
- `_require_relationship_service()` - Ensures relationships available

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
    graph_intelligence_service=graph_intelligence,
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

### Knowledge Generation

TasksIntelligenceService excels at **extracting knowledge from action**. By analyzing task patterns, it identifies:
- Recurring problem-solving approaches → best practice KUs
- Frequent task types → workflow documentation
- Repeated debugging sessions → troubleshooting guides

### Learning Opportunity Discovery

The service discovers learning opportunities by correlating:
- Failed tasks → knowledge gaps
- Slow task completion → skill development areas
- Successful patterns → skills worth deepening
- Graph relationships → prerequisite knowledge needs

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
    graph_intelligence_service=graph_intel
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
