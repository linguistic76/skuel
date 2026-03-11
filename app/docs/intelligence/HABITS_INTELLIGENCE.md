# HabitsIntelligenceService - Streak Pattern Analysis & Habit Formation

## Overview

**Architecture:** Extends `BaseAnalyticsService[HabitsOperations, Habit]`
**Location:** `/core/services/habits/habits_intelligence_service.py`
**Service Name:** `habits.intelligence`
**Lines:** ~1,311

---

## Purpose

HabitsIntelligenceService transforms habit execution data into behavioral insights and learning reinforcement analytics. It analyzes streak patterns, calculates consistency scores, tracks knowledge reinforcement through practice, evaluates goal support contributions, and provides habit formation recommendations.

---

## Core Methods

### Method 1: get_habit_with_context()

**Purpose:** Get habit with full graph context using pure Cypher graph intelligence. Automatically selects optimal query type based on habit's suggested intent.

**Signature:**
```python
async def get_habit_with_context(
    self,
    uid: str,
    depth: int = 2
) -> Result[tuple[Habit, GraphContext]]:
```

**Parameters:**
- `uid` (str) - Habit UID
- `depth` (int, default=2) - Graph traversal depth

**Returns:**
```python
(habit, graph_context)  # Tuple
```

**Query Selection:**
- **PRACTICE** → Knowledge reinforcement tracking
- **HIERARCHICAL** → Goal support analysis
- **RELATIONSHIP** → Habit ecosystem connections
- **Default** → Knowledge practice context

**Example:**
```python
result = await habits_service.intelligence.get_habit_with_context(
    uid="habit_001",
    depth=2
)

if result.is_ok:
    habit, graph_context = result.value
    print(f"Habit: {habit.name}")

    # Extract cross-domain insights
    knowledge = graph_context.get_nodes_by_domain(Domain.KNOWLEDGE)
    goals = graph_context.get_nodes_by_domain(Domain.GOALS)
    tasks = graph_context.get_nodes_by_domain(Domain.TASKS)

    print(f"Reinforces {len(knowledge)} knowledge areas")
    print(f"Supports {len(goals)} goals")
```

**Dependencies:**
- GraphIntelligenceService (REQUIRED - uses `@requires_graph_intelligence` decorator)
- Uses GraphContextOrchestrator pattern (Phase 2 consolidation)

**Performance:**
- Old approach: ~250ms (3-5 separate queries)
- New approach: ~30ms (single APOC query)
- 8-10x faster with single database round trip

---

### Method 2: analyze_habit_performance()

**Purpose:** Analyze habit with knowledge reinforcement and goal support using comprehensive performance analysis. Provides insights into streak score, consistency metrics, reinforcement effectiveness, and actionable recommendations.

**Signature:**
```python
async def analyze_habit_performance(
    self,
    uid: str,
    min_confidence: float = 0.7
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `uid` (str) - Habit UID
- `min_confidence` (float, default=0.7) - Minimum confidence for graph relationships

**Returns:**
```python
{
    "habit": Habit(...),
    "performance": {
        "knowledge_reinforced": [{"uid": "ku.python-basics"}, ...],
        "supporting_goals": [{"uid": "goal_001"}, ...],
        "streak_score": 0.85,
        "reinforcement_effectiveness": 6.8,
        "consistency_score": 0.85,
        "total_knowledge_areas": 4,
        "total_goals_supported": 2
    },
    "insights": {
        "high_reinforcement": True,
        "goal_aligned": True,
        "knowledge_builder": True
    },
    "recommendations": {
        "maintain_consistency": False,
        "expand_knowledge_links": False,
        "align_with_more_goals": False
    },
    "metrics": {
        "knowledge_reinforcement_count": 4,
        "goal_support_count": 2,
        "has_goal_connection": True,
        "is_knowledge_builder": True,
        "integration_score": 0.67
    }
}
```

**Example:**
```python
result = await habits_service.intelligence.analyze_habit_performance("habit_001")

if result.is_ok:
    analysis = result.value
    perf = analysis["performance"]

    print(f"Streak: {perf['streak_score']:.0%}")
    print(f"Reinforces {perf['total_knowledge_areas']} knowledge areas")
    print(f"Supports {perf['total_goals_supported']} goals")
    print(f"Consistency: {perf['consistency_score']:.0%}")

    if analysis["insights"]["high_reinforcement"]:
        print("This is a highly effective learning habit!")
```

**Dependencies:**
- HabitsOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED - `_require_relationships = True`)
- Uses CrossDomainContextService for typed context retrieval (Phase 3)
- Uses `calculate_habit_metrics()` for standard metrics

**Performance Metrics Calculation:**
- `streak_score` = current_streak / best_streak (0.0-1.0)
- `consistency_score` = habit.calculate_consistency_score()
- `reinforcement_effectiveness` = knowledge_count × consistency_score
- `high_reinforcement` = reinforcement_effectiveness > 5.0

---

### Method 3: get_habit_knowledge_reinforcement()

**Purpose:** Analyze how this habit reinforces knowledge through practice. Tracks practice frequency, calculates effectiveness scores, analyzes mastery progression, and identifies learning opportunities.

**Signature:**
```python
async def get_habit_knowledge_reinforcement(
    self,
    uid: str,
    depth: int = 2,
    min_confidence: float = 0.7
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `uid` (str) - Habit UID
- `depth` (int, default=2) - Graph traversal depth
- `min_confidence` (float, default=0.7) - Minimum confidence for relationships

**Returns:**
```python
{
    "habit": Habit(...),
    "knowledge_reinforcement": {
        "reinforced_knowledge": [{"uid": "ku.python-basics"}, ...],
        "practice_frequency": "daily",
        "practice_effectiveness_score": 7.5,
        "mastery_progression": [
            {
                "knowledge_uid": "ku.python-basics",
                "title": "Python Basics",
                "practice_count": 42,
                "estimated_mastery": 0.75
            }
        ],
        "knowledge_coverage": 0.4
    },
    "learning_analysis": {
        "primary_knowledge_areas": ["ku.python-basics", "ku.fasthtml-intro"],
        "skill_development_rate": 0.75,
        "learning_consistency": 0.85
    },
    "metrics": {
        "knowledge_reinforcement_count": 4,
        "is_knowledge_builder": True,
        "integration_score": 0.67
    }
}
```

**Example:**
```python
result = await habits_service.intelligence.get_habit_knowledge_reinforcement("habit_001")

if result.is_ok:
    analysis = result.value
    kr = analysis["knowledge_reinforcement"]

    print(f"Reinforces {len(kr['reinforced_knowledge'])} areas")
    print(f"Practice frequency: {kr['practice_frequency']}")
    print(f"Effectiveness: {kr['practice_effectiveness_score']:.1f}/10")
    print(f"Knowledge coverage: {kr['knowledge_coverage']:.0%}")

    print("\nMastery Progression:")
    for progress in kr["mastery_progression"]:
        print(f"  {progress['knowledge_uid']}: {progress['estimated_mastery']:.0%}")
```

**Dependencies:**
- HabitsOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED)
- Uses CrossDomainContextService (Phase 3)

**Practice Effectiveness Calculation:**
```
base_score = consistency × 5.0
knowledge_bonus = min(3.0, knowledge_count × 0.5)
streak_bonus = min(2.0, (streak / 30.0) × 2.0)
practice_effectiveness = base_score + knowledge_bonus + streak_bonus
```

**Mastery Progression:**
- `practice_count` = current_streak (number of consecutive completions)
- `estimated_mastery` = min(1.0, practice_effectiveness × 0.1)

---

### Method 4: get_habit_goal_support()

**Purpose:** Analyze how this habit supports user's goals. Evaluates contribution strength to each goal, calculates goal alignment score, assesses progress impact, and provides optimization recommendations.

**Signature:**
```python
async def get_habit_goal_support(
    self,
    uid: str,
    depth: int = 2,
    min_confidence: float = 0.7
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `uid` (str) - Habit UID
- `depth` (int, default=2) - Graph traversal depth
- `min_confidence` (float, default=0.7) - Minimum confidence for relationships

**Returns:**
```python
{
    "habit": Habit(...),
    "goal_support": {
        "supported_goals": [{"uid": "goal_001"}, {"uid": "goal_002"}],
        "goal_contributions": [
            {
                "goal_uid": "goal_001",
                "goal_title": "goal_001",
                "contribution_strength": 1.7,
                "estimated_impact": "high"
            }
        ],
        "alignment_score": 6.8,
        "total_goals_supported": 2,
        "primary_goal": {"uid": "goal_001"}
    },
    "impact_analysis": {
        "high_impact": False,
        "goal_aligned": True,
        "consistency_matters": True
    },
    "recommendations": {
        "increase_frequency": False,
        "link_more_goals": False,
        "maintain_consistency": True
    },
    "metrics": {
        "goal_support_count": 2,
        "has_goal_connection": True,
        "integration_score": 0.67
    }
}
```

**Example:**
```python
result = await habits_service.intelligence.get_habit_goal_support("habit_001")

if result.is_ok:
    analysis = result.value
    gs = analysis["goal_support"]

    print(f"Supports {gs['total_goals_supported']} goals")
    print(f"Alignment: {gs['alignment_score']:.1f}/10")

    for contrib in gs["goal_contributions"]:
        print(f"\nGoal: {contrib['goal_uid']}")
        print(f"  Contribution strength: {contrib['contribution_strength']:.2f}")
        print(f"  Impact: {contrib['estimated_impact']}")

    if analysis["impact_analysis"]["consistency_matters"]:
        print("\nConsistency is critical for this habit!")
```

**Dependencies:**
- HabitsOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED)
- Uses CrossDomainContextService (Phase 3)

**Goal Contribution Calculation:**
```
contribution_strength = consistency_score × 2.0  # 0-2 scale
estimated_impact = "high"   if consistency > 0.7
                 | "medium" if consistency > 0.4
                 | "low"    otherwise
```

**Alignment Score Calculation:**
```
alignment_score = min(10.0, goal_count × 2.0 × consistency_score)
```

**Impact Analysis:**
- `high_impact` = alignment_score > 7.0
- `goal_aligned` = has_goal_connection (from metrics)
- `consistency_matters` = consistency_score > 0.7

---

### Method 5: assess_consistency_dual_track() (ADR-030)

**Purpose:** Compare user's self-assessed habit consistency with system-measured consistency metrics, generating perception gap analysis and personalized insights.

**Signature:**
```python
async def assess_consistency_dual_track(
    self,
    user_uid: str,
    user_consistency_level: ConsistencyLevel,
    user_evidence: str,
    user_reflection: str | None = None,
    period_days: int = 30,
) -> Result[DualTrackResult[ConsistencyLevel]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `user_consistency_level` (ConsistencyLevel) - User's self-assessed consistency level
- `user_evidence` (str) - User's evidence for their assessment
- `user_reflection` (str, optional) - User's optional reflection
- `period_days` (int, default=30) - Period to analyze for system calculation

**Returns:**
```python
DualTrackResult[ConsistencyLevel](
    entity_uid="user.mike",
    entity_type="consistency_assessment",

    # USER-DECLARED (Vision)
    user_level=ConsistencyLevel.VERY_CONSISTENT,
    user_score=0.875,
    user_evidence="I maintain my habits every day",
    user_reflection="I'm very disciplined with my routines",

    # SYSTEM-CALCULATED (Action)
    system_level=ConsistencyLevel.MOSTLY_CONSISTENT,
    system_score=0.68,
    system_evidence=(
        "Average completion rate: 68%",
        "Streak health: 72%",
        "Average streak length: 8.5 days",
        "Active habit ratio: 80%",
    ),

    # GAP ANALYSIS
    perception_gap=0.195,
    gap_direction="user_higher",

    # INSIGHTS
    insights=("Self-assessment exceeds measured consistency by ~20%",),
    recommendations=("Focus on maintaining streaks", "Review habits at risk"),
)
```

**ConsistencyLevel Enum:**
```python
class ConsistencyLevel(str, Enum):
    VERY_CONSISTENT = "very_consistent"     # 0.85+
    MOSTLY_CONSISTENT = "mostly_consistent"  # 0.70-0.85
    SOMEWHAT_CONSISTENT = "somewhat_consistent"  # 0.50-0.70
    INCONSISTENT = "inconsistent"           # 0.30-0.50
    VERY_INCONSISTENT = "very_inconsistent"  # <0.30

    def to_score(self) -> float: ...
    @classmethod
    def from_score(cls, score: float) -> "ConsistencyLevel": ...
```

**System Metrics Used:**
- Average completion rate across all habits
- Streak health (current streaks vs best streaks)
- Average streak length in days
- Active habit ratio (active habits / total habits)

**Example:**
```python
result = await habits_service.intelligence.assess_consistency_dual_track(
    user_uid="user.mike",
    user_consistency_level=ConsistencyLevel.VERY_CONSISTENT,
    user_evidence="I maintain my habits every day",
    user_reflection="I'm very disciplined with my routines",
    period_days=30,
)

if result.is_ok:
    assessment = result.value
    print(f"User perception: {assessment.user_level.value}")
    print(f"System measurement: {assessment.system_level.value}")

    if assessment.is_self_aware():
        print("Accurate self-assessment!")
    else:
        print(f"Perception gap: {assessment.perception_gap:.0%}")
```

**Dependencies:**
- HabitsOperations backend (REQUIRED)
- Uses `BaseAnalyticsService._dual_track_assessment()` template

**API Endpoint:**
```
POST /api/habits/assess-consistency
```

**See:** [ADR-030: Dual-Track Assessment Pattern](../decisions/ADR-030-dual-track-assessment-pattern.md)

---

## BaseAnalyticsService Features

### Inherited Infrastructure

**Fail-Fast Validation:**
- `_require_graph_intelligence()` - Ensures graph_intel available
- `_require_relationship_service()` - Ensures relationships available (REQUIRED)

**Standard Attributes:**
- `self.backend` - HabitsOperations (REQUIRED)
- `self.graph_intel` - GraphIntelligenceService (REQUIRED for graph methods)
- `self.relationships` - UnifiedRelationshipService (REQUIRED - `_require_relationships = True`)
- `self.embeddings` - OpenAIEmbeddingsService (not currently used)
- `self.llm` - LLMService (not currently used)

**Domain-Specific Attributes:**
- `self.context_service` - CrossDomainContextService for typed context retrieval (Phase 3)
- `self.orchestrator` - GraphContextOrchestrator for get_with_context pattern (Phase 2)

**Logging:**
```python
self.logger.info("Message")  # Logs to: skuel.intelligence.habits.intelligence
```

---

## Integration with HabitsService

### Facade Access

```python
# HabitsService creates intelligence internally
habits_service = HabitsService(
    backend=habits_backend,
    graph_intelligence_service=graph_intelligence,
    embeddings_service=embeddings_service,
    llm_service=llm_service,
    event_bus=event_bus,
    user_service=user_service,
)

# Access via .intelligence attribute
result = await habits_service.intelligence.analyze_habit_performance(
    uid="habit_001"
)
```

---

## Domain-Specific Features

### Streak Pattern Analysis

HabitsIntelligenceService excels at **analyzing consistency patterns** through:

**Streak Metrics:**
- `current_streak` - Consecutive successful completions
- `best_streak` - All-time highest streak
- `streak_score` - Current vs best (0.0-1.0)

**Consistency Calculation:**
```python
consistency_score = habit.calculate_consistency_score()
# Considers:
# - Recurrence pattern (daily, weekly, etc.)
# - Completion rate over time
# - Streak momentum
```

**Pattern Detection:**
- Identifies "at risk" streaks (missed recent completions)
- Detects "broken" streaks requiring restart
- Tracks "building momentum" patterns (improving consistency)

### Knowledge Reinforcement Through Practice

Unique capability: **Quantifying learning impact of habit practice**

**Reinforcement Tracking:**
```
REINFORCES_KNOWLEDGE relationships → Knowledge areas being practiced
practice_frequency → How often habit executed
practice_effectiveness → Quality of reinforcement (0-10 scale)
mastery_progression → Estimated skill development over time
```

**Effectiveness Formula:**
```
base_score = consistency × 5.0                 # 0-5 from consistency
knowledge_bonus = min(3.0, knowledge_count × 0.5)  # 0-3 from breadth
streak_bonus = min(2.0, (streak / 30.0) × 2.0)    # 0-2 from persistence
total_effectiveness = base_score + knowledge_bonus + streak_bonus  # 0-10
```

**Mastery Estimation:**
- `practice_count` = current_streak (repetitions)
- `estimated_mastery` = min(1.0, effectiveness × 0.1)
- Caps at 100% to prevent unrealistic projections

### Goal Support Contribution Analysis

**Contribution Metrics:**
```
contribution_strength = consistency × 2.0  # 0-2 scale per goal
alignment_score = goal_count × 2.0 × consistency  # 0-10 overall
```

**Criticality Classification:**
- `high_impact` - alignment_score > 7.0 (critical to goal success)
- `goal_aligned` - has_goal_connection (supports at least one goal)
- `consistency_matters` - consistency > 0.7 (high consistency required)

**Recommendations:**
```
increase_frequency: consistency < 0.5
link_more_goals: goal_count < 2
maintain_consistency: consistency >= 0.7
```

### Cross-Domain Context Integration (Phase 3)

Uses `HabitCrossContext` for type-safe relationship access:

```python
@dataclass
class HabitCrossContext:
    knowledge_reinforcement_uids: list[str]
    linked_goal_uids: list[str]
    related_task_uids: list[str]
    related_event_uids: list[str]
    # ... additional fields
```

**Standard Metrics (calculate_habit_metrics):**
- `knowledge_reinforcement_count` - Number of KUs reinforced
- `goal_support_count` - Number of goals supported
- `has_goal_connection` - Boolean flag
- `is_knowledge_builder` - Boolean flag (reinforces knowledge)
- `integration_score` - Overall integration level (0.0-1.0)

---

## Testing

### Unit Tests
```bash
uv run python -m pytest tests/unit/services/test_habits_intelligence_service.py -v
```

### Integration Tests
```bash
# Test with real backend
uv run python -m pytest tests/integration/intelligence/test_habits_intelligence.py -v

# Test specific method
uv run python -m pytest tests/integration/intelligence/ -k "test_analyze_habit_performance" -v
```

### Example Test
```python
from unittest.mock import Mock
from core.services.habits.habits_intelligence_service import HabitsIntelligenceService

# Create mock services
backend = Mock()
graph_intel = Mock()
relationships = Mock()

# Instantiate service
service = HabitsIntelligenceService(
    backend=backend,
    graph_intelligence_service=graph_intel,
    relationship_service=relationships
)

# Verify initialization
assert service._service_name == "habits.intelligence"
assert service._require_relationships is True
assert service.backend == backend
assert service.graph_intel == graph_intel
assert service.relationships == relationships
```

---

---

## get_zpd_knowledge_signals() (ZPD Bridge — March 2026)

**Purpose:** Extract knowledge reinforcement signals for ZPDService consumption. Queries `REINFORCES_KNOWLEDGE` edges on the user's active habits and computes per-KU reinforcement strength.

**Signature:**
```python
async def get_zpd_knowledge_signals(
    self, user_uid: str
) -> Result[dict[str, Any]]:
```

**Returns:**
```python
{
    "reinforced_ku_uids": list[str],            # KUs reinforced by active habits
    "reinforcement_strength": dict[str, float], # ku_uid → 0.0-1.0 (streak + success rate blend)
    "at_risk_ku_uids": list[str],               # KUs whose reinforcing habit has broken streak
                                                # or success_rate < 0.5
}
```

**Strength formula:** `(min(streak/30, 1.0) × 0.5) + (success_rate × 0.5)`

**Consumed by:** `ZPDService.assess_zone()` — reinforced KUs count toward current_zone scoring.

**See:** `core/services/zpd/zpd_service.py` (Phase 3, pending implementation)

---

## See Also

- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` - Master index
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - BaseAnalyticsService pattern
- `/core/services/base_intelligence_service.py` - Base implementation
- `/core/services/habits/habits_service.py` - HabitsService facade
- `/core/services/habits/habits_planning_service.py` - Context-aware planning (January 2026)
- `/core/services/habits/habits_scheduling_service.py` - Smart scheduling (January 2026)
- `/core/services/intelligence/cross_domain_context_service.py` - Phase 3 context retrieval
- `/core/models/habit/habit.py` - Habit domain model
- `/docs/domains/habits.md` - Habits domain documentation
