# EventsIntelligenceService - Cross-Domain Impact Analysis & Schedule Optimization

## Overview

**Architecture:** Extends `BaseAnalyticsService[EventsOperations, Event]`
**Location:** `/core/services/events/events_intelligence_service.py`
**Service Name:** `events.intelligence`
**Lines:** ~830

**Related Services (January 2026):**
- `EventsProgressService` - Progress tracking, completion, attendance metrics
- `EventsSchedulingService` - Smart scheduling, conflict detection, calendar density

---

## Purpose

EventsIntelligenceService analyzes events through cross-domain impact tracking, learning practice verification, and schedule optimization. It evaluates how events support goals, reinforce habits, practice knowledge, and contribute to overall life path alignment through comprehensive graph-based analysis.

**Version:** 1.1.0 (Pure Cypher - NO APOC, January 2026)

---

## Core Methods

### Method 1: get_event_with_context()

**Purpose:** Get event with full graph context using pure Cypher graph intelligence. Single query retrieves event entity plus supporting goals, reinforcing habits, related knowledge units, learning path connections, and semantic relationships.

**Signature:**
```python
async def get_event_with_context(
    self,
    uid: str,
    depth: int = 2
) -> Result[tuple[Event, GraphContext]]:
```

**Parameters:**
- `uid` (str) - Event UID
- `depth` (int, default=2) - Graph traversal depth

**Returns:**
```python
(event, graph_context)  # Tuple[Event, GraphContext]
```

**Performance:**
- 8-10x faster than sequential queries
- Single query retrieves all relationships
- Handles nested graph context at any depth

**Example:**
```python
result = await events_service.intelligence.get_event_with_context(
    uid="event_001",
    depth=2
)

if result.is_ok:
    event, graph_context = result.value
    print(f"Event: {event.title}")
    print(f"Relationships: {len(graph_context.relationships)}")
    print(f"Connected nodes: {len(graph_context.nodes)}")
```

**Dependencies:**
- GraphIntelligenceService (REQUIRED - fails with system error if not available)
- Uses `graph_intel.get_entity_context()` for pure Cypher traversal

---

### Method 2: get_performance_analytics() (IntelligenceOperations Protocol)

**Purpose:** Get event performance analytics for a user within a specified time period.

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
- `period_days` (int, default=30) - Number of days to analyze

**Returns:**
```python
{
    "user_uid": "user.mike",
    "period_days": 30,
    "start_date": "2025-12-20",
    "end_date": "2026-01-19",
    "total_events": 25,
    "completed_events": 18,
    "upcoming_events": 5,
    "completion_rate": 0.72,
    "analytics": {
        "total": 25,
        "completed": 18,
        "upcoming": 5,
        "completion_rate_percentage": 72.0
    }
}
```

**Note:** As of January 19, 2026, `period_days` is fully implemented (no longer a placeholder).

**Example:**
```python
result = await events_service.intelligence.get_performance_analytics(
    user_uid="user.mike",
    period_days=30
)

if result.is_ok:
    analytics = result.value
    print(f"Completion rate: {analytics['completion_rate']:.0%}")
    print(f"Events in period: {analytics['total_events']}")
```

---

### Method 3: analyze_event_performance()

**Purpose:** Analyze event with goal support, habit reinforcement, and knowledge practice metrics. Returns comprehensive performance analysis including impact scores and cross-domain contribution weights.

**Signature:**
```python
async def analyze_event_performance(
    self,
    uid: str
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `uid` (str) - Event UID

**Returns:**
```python
{
    "event_uid": "event_001",
    "event_title": "Morning workout",
    "status": "completed",
    "goal_support": {
        "supports_goals": True,
        "goal_uid": "goal_001",
        "contribution_weight": 1.0,
        "status": "completed",
        "completed": True
    },
    "habit_reinforcement": {
        "reinforces_habit": True,
        "habit_uid": "habit_001",
        "quality_score": 4,
        "status": "completed",
        "completed": True
    },
    "knowledge_reinforcement": {
        "reinforces_knowledge": True,
        "knowledge_units": ["ku.exercise-technique", "ku.nutrition-basics"],
        "knowledge_count": 2,
        "study_time_minutes": 30,
        "status": "completed"
    },
    "overall_impact_score": 3.5,
    "graph_context_depth": 8
}
```

**Example:**
```python
result = await events_service.intelligence.analyze_event_performance("event_001")

if result.is_ok:
    analysis = result.value
    print(f"Event: {analysis['event_title']}")
    print(f"Overall impact: {analysis['overall_impact_score']:.2f}")

    if analysis["goal_support"]["supports_goals"]:
        print(f"Supports goal: {analysis['goal_support']['goal_uid']}")

    if analysis["knowledge_reinforcement"]["reinforces_knowledge"]:
        print(f"Practices {analysis['knowledge_reinforcement']['knowledge_count']} KUs")
```

**Dependencies:**
- GraphIntelligenceService (REQUIRED)
- UnifiedRelationshipService (optional - enhanced analysis)
- Uses `GraphDepth.NEIGHBORHOOD` constant for context depth

---

### Method 4: get_event_goal_support()

**Purpose:** Get event's goal contribution analysis, identifying which goals are supported by the event and the contribution weight of the relationship.

**Signature:**
```python
async def get_event_goal_support(
    self,
    uid: str,
    depth: int = 2
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `uid` (str) - Event UID
- `depth` (int, default=2) - Graph traversal depth

**Returns:**
```python
{
    "event_uid": "event_001",
    "supports_goal_uids": ["goal_001", "goal_002"],
    "goal_contribution_weight": 1.0,
    "analysis": {
        "supports_goals": True,
        "goal_uid": "goal_001",
        "contribution_weight": 1.0,
        "status": "completed",
        "completed": True
    },
    "retrieved_via": "pure Cypher graph intelligence"
}
```

**Example:**
```python
result = await events_service.intelligence.get_event_goal_support("event_001")

if result.is_ok:
    support = result.value
    print(f"Supports {len(support['supports_goal_uids'])} goals")
    print(f"Contribution weight: {support['goal_contribution_weight']}")

    analysis = support["analysis"]
    if analysis["supports_goals"]:
        print(f"Primary goal: {analysis['goal_uid']}")
```

**Dependencies:**
- GraphIntelligenceService (REQUIRED)
- UnifiedRelationshipService (REQUIRED - uses `_require_relationship_service()`)

**Graph Pattern:**
```cypher
(event)-[:SUPPORTS_GOAL {contribution_weight}]->(goal)
```

---

### Method 5: get_event_knowledge_reinforcement()

**Purpose:** Get event's knowledge practice tracking, showing which knowledge units are practiced through the event and the learning time invested.

**Signature:**
```python
async def get_event_knowledge_reinforcement(
    self,
    uid: str,
    depth: int = 2
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `uid` (str) - Event UID
- `depth` (int, default=2) - Graph traversal depth

**Returns:**
```python
{
    "event_uid": "event_001",
    "practices_knowledge_uids": ["ku.exercise-technique", "ku.nutrition-basics"],
    "analysis": {
        "reinforces_knowledge": True,
        "knowledge_units": ["ku.exercise-technique", "ku.nutrition-basics"],
        "knowledge_count": 2,
        "study_time_minutes": 30,
        "status": "completed"
    },
    "retrieved_via": "pure Cypher graph intelligence with EventRelationships"
}
```

**Example:**
```python
result = await events_service.intelligence.get_event_knowledge_reinforcement("event_001")

if result.is_ok:
    reinforcement = result.value
    ku_count = len(reinforcement["practices_knowledge_uids"])
    print(f"Practices {ku_count} knowledge units")

    analysis = reinforcement["analysis"]
    if analysis.get("study_time_minutes"):
        print(f"Study time: {analysis['study_time_minutes']} minutes")
```

**Dependencies:**
- GraphIntelligenceService (REQUIRED)
- UnifiedRelationshipService (REQUIRED)
- Uses `EventRelationships.fetch()` for typed relationship access

**Graph Pattern:**
```cypher
(event)-[:PRACTICES_KNOWLEDGE]->(ku)
```

---

### Method 6: analyze_upcoming_events()

**Purpose:** Batch analysis of all upcoming events for impact optimization opportunities. Identifies high-impact events (worth prioritizing) and low-impact events (worth linking to goals/habits).

**Signature:**
```python
async def analyze_upcoming_events(
    self,
    user_uid: str,
    days_ahead: int = 7
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `days_ahead` (int, default=7) - Number of days to analyze forward

**Returns:**
```python
{
    "total_upcoming_events": 12,
    "high_impact_events": [
        {
            "uid": "event_001",
            "title": "Morning workout",
            "event_date": "2026-01-09",
            "impact_score": 3.5
        }
    ],
    "low_impact_events": [
        {
            "uid": "event_005",
            "title": "Random meeting",
            "event_date": "2026-01-10",
            "impact_score": 0.0
        }
    ],
    "total_goal_supporting_events": 8,
    "total_habit_reinforcing_events": 6,
    "days_analyzed": 7,
    "recommendations": [
        "Consider linking 3 low-impact events to goals or habits",
        "Schedule more events to maintain consistent progress"
    ]
}
```

**Example:**
```python
# Analyze next week
result = await events_service.intelligence.analyze_upcoming_events(
    user_uid="user.mike",
    days_ahead=7
)

if result.is_ok:
    analysis = result.value
    print(f"Total upcoming events: {analysis['total_upcoming_events']}")
    print(f"High-impact: {len(analysis['high_impact_events'])}")
    print(f"Low-impact: {len(analysis['low_impact_events'])}")

    print("\nScheduling Recommendations:")
    for rec in analysis["recommendations"]:
        print(f"  - {rec}")
```

**Dependencies:**
- EventsOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED)

**Impact Scoring:**
```
impact_score = (goal_support ? 1 : 0)
             + (habit_reinforcement ? 1 : 0)
             + (knowledge_count × 0.5)

High impact: ≥2.0
Low impact: <1.0
```

---

### Method 7: assess_engagement_dual_track() (ADR-030)

**Purpose:** Compare user's self-assessed event engagement with system-measured engagement metrics, generating perception gap analysis and personalized insights.

**Signature:**
```python
async def assess_engagement_dual_track(
    self,
    user_uid: str,
    user_engagement_level: EngagementLevel,
    user_evidence: str,
    user_reflection: str | None = None,
    period_days: int = 30,
) -> Result[DualTrackResult[EngagementLevel]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `user_engagement_level` (EngagementLevel) - User's self-assessed engagement level
- `user_evidence` (str) - User's evidence for their assessment
- `user_reflection` (str, optional) - User's optional reflection
- `period_days` (int, default=30) - Period to analyze for system calculation

**Returns:**
```python
DualTrackResult[EngagementLevel](
    entity_uid="user.mike",
    entity_type="engagement_assessment",

    # USER-DECLARED (Vision)
    user_level=EngagementLevel.HIGHLY_ENGAGED,
    user_score=0.90,
    user_evidence="I attend all my scheduled events",
    user_reflection="I'm very active in my commitments",

    # SYSTEM-CALCULATED (Action)
    system_level=EngagementLevel.ENGAGED,
    system_score=0.72,
    system_evidence=(
        "Attendance rate: 75%",
        "Goal-supporting events: 68%",
        "Habit reinforcement: 70%",
        "Recent activity: 78%",
    ),

    # GAP ANALYSIS
    perception_gap=0.18,
    gap_direction="user_higher",

    # INSIGHTS
    insights=("Self-assessment exceeds measured engagement by ~18%",),
    recommendations=("Improve event attendance rate", "Link more events to goals"),
)
```

**EngagementLevel Enum:**
```python
class EngagementLevel(str, Enum):
    HIGHLY_ENGAGED = "highly_engaged"      # 0.85+
    ENGAGED = "engaged"                     # 0.70-0.85
    MODERATELY_ENGAGED = "moderately_engaged"  # 0.50-0.70
    DISENGAGED = "disengaged"              # 0.30-0.50
    VERY_DISENGAGED = "very_disengaged"    # <0.30

    def to_score(self) -> float: ...
    @classmethod
    def from_score(cls, score: float) -> "EngagementLevel": ...
```

**System Metrics Used:**
- Attendance rate (completed events / total events)
- Goal-supporting events (events with goal connections / total)
- Habit reinforcement (events reinforcing habits / total)
- Recency score (recent events weighted higher)

**Example:**
```python
result = await events_service.intelligence.assess_engagement_dual_track(
    user_uid="user.mike",
    user_engagement_level=EngagementLevel.HIGHLY_ENGAGED,
    user_evidence="I attend all my scheduled events",
    user_reflection="I'm very active in my commitments",
    period_days=30,
)

if result.is_ok:
    assessment = result.value
    print(f"Perception gap: {assessment.perception_gap:.0%}")
    print(f"Direction: {assessment.gap_direction}")

    for evidence in assessment.system_evidence:
        print(f"  - {evidence}")
```

**Dependencies:**
- EventsOperations backend (REQUIRED)
- Uses `BaseAnalyticsService._dual_track_assessment()` template

**API Endpoint:**
```
POST /api/events/assess-engagement
```

**See:** [ADR-030: Dual-Track Assessment Pattern](../decisions/ADR-030-dual-track-assessment-pattern.md)

---

## BaseAnalyticsService Features

### Inherited Infrastructure

**Fail-Fast Validation:**
- `_require_graph_intelligence()` - Ensures graph_intel available
- `_require_relationship_service()` - Ensures relationships available

**Standard Attributes:**
- `self.backend` - EventsOperations (REQUIRED)
- `self.graph_intel` - GraphIntelligenceService (REQUIRED for graph methods)
- `self.relationships` - UnifiedRelationshipService (optional - enhanced analysis)

**NOTE:** Analytics services do NOT have `embeddings` or `llm` attributes - they work without AI dependencies (ADR-030).

**Domain-Specific Attributes:**
- `self.context_service` - CrossDomainContextService for typed context retrieval (Phase 3)

**Logging:**
```python
self.logger.info("Message")  # Logs to: skuel.intelligence.events.intelligence
```

---

## Integration with EventsService

### Facade Access

```python
# EventsService creates intelligence internally
events_service = EventsService(
    backend=events_backend,
    graph_intelligence_service=graph_intelligence,
    embeddings_service=embeddings_service,
    llm_service=llm_service,
    event_bus=event_bus,
    user_service=user_service,
)

# Access via .intelligence attribute
result = await events_service.intelligence.analyze_upcoming_events(
    user_uid="user.mike",
    days_ahead=14
)
```

---

## Domain-Specific Features

### Cross-Domain Impact Analysis

EventsIntelligenceService excels at **tracking how events contribute across domains**:
- **Goal support** - How events drive goal completion
- **Habit reinforcement** - How events strengthen habit systems
- **Knowledge practice** - How events apply learning in real-world contexts
- **Life path alignment** - Overall contribution to ultimate life goal

### Learning Practice Tracking

Events serve as **practice opportunities** for knowledge application:
- Links events to knowledge units via `PRACTICES_KNOWLEDGE` relationships
- Tracks `study_time_minutes` or `duration_minutes` for learning investment
- Identifies which knowledge is being actively practiced vs. passively known
- Supports knowledge substance philosophy (applied knowledge, not pure theory)

### Schedule Optimization

Unique among intelligence services, EventsIntelligenceService provides **actionable scheduling insights**:
- **High-impact events** → Worth prioritizing, should not be rescheduled
- **Low-impact events** → Candidates for goal/habit linking or cancellation
- **Goal-supporting events** → Directly contribute to goal achievement
- **Habit-reinforcing events** → Strengthen habit consistency

The batch analysis methods generate **scheduling recommendations**:
- Too many low-impact events? → Link to goals/habits
- Too few high-impact events? → Schedule more goal-supporting activities
- Too few total events? → Maintain consistent progress
- Too many total events? → Avoid overcommitment

### Graph-Native Relationships

Uses `EventRelationships.fetch()` for typed relationship access:
- `practices_knowledge_uids` - Knowledge units practiced via `PRACTICES_KNOWLEDGE`
- `executes_task_uids` - Tasks executed via event
- `conflicts_with_uids` - Conflicting events
- `attendee_uids` - Event attendees
- `supports_goal_uids` - Goals supported via `CONTRIBUTES_TO_GOAL` ✅ (January 2026)

**Helper Methods:**
- `has_knowledge_practice()` - Check if event practices any knowledge
- `has_task_execution()` - Check if event executes any tasks
- `has_conflicts()` - Check if event has conflicts
- `has_attendees()` - Check if event has attendees
- `has_goal_support()` - Check if event supports any goals ✅ (January 2026)
- `total_relationships()` - Count all relationships (includes goals)

**Implementation Note (January 2026):** Goal support was added to `EventRelationships` via `supports_goal_uids` field and `("supports_goal_uids", "goals")` in `EVENT_QUERY_SPECS`. The `get_event_goal_support()` method now uses `EventRelationships.fetch()` for efficient parallel relationship retrieval.

### Recurrence Pattern Analysis

Events support recurring patterns for sustained practice:
- Daily learning sessions
- Weekly review meetings
- Monthly goal check-ins
- Annual planning retreats

**TODO:** Implement `analyze_recurrence_patterns()` to identify optimal recurring event frequencies based on goal velocity and habit consistency.

---

## Testing

### Unit Tests
```bash
poetry run python -m pytest tests/unit/services/test_events_intelligence_service.py -v
```

### Integration Tests
```bash
# Test with real backend
poetry run python -m pytest tests/integration/intelligence/test_events_intelligence.py -v

# Test specific method
poetry run python -m pytest tests/integration/intelligence/ -k "test_analyze_upcoming_events" -v
```

### Example Test
```python
from unittest.mock import Mock
from core.services.events.events_intelligence_service import EventsIntelligenceService

# Create mock services
backend = Mock()
graph_intel = Mock()
relationships = Mock()

# Instantiate service
service = EventsIntelligenceService(
    backend=backend,
    graph_intelligence_service=graph_intel,
    relationship_service=relationships
)

# Verify initialization
assert service._service_name == "events.intelligence"
assert service.backend == backend
assert service.graph_intel == graph_intel
assert service.relationships == relationships
```

---

## See Also

- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` - Master index
- `/docs/intelligence/TASKS_INTELLIGENCE.md` - Task knowledge generation patterns
- `/docs/intelligence/GOALS_INTELLIGENCE.md` - Goal forecasting patterns
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - BaseAnalyticsService pattern
- `/core/services/base_intelligence_service.py` - Base implementation
- `/core/services/events/events_service.py` - EventsService facade
- `/core/services/events/event_relationships.py` - EventRelationships typed access
- `/docs/architecture/knowledge_substance_philosophy.md` - Applied knowledge measurement
