# GoalsIntelligenceService - Progress Forecasting & Predictive Analytics

## Overview

**Architecture:** Extends `BaseAnalyticsService[GoalsOperations, Goal]`
**Location:** `/core/services/goals/goals_intelligence_service.py`
**Service Name:** `goals.intelligence`
**Lines:** ~1,495

---

## Purpose

GoalsIntelligenceService provides comprehensive goal intelligence combining graph-based context analysis with predictive analytics. It forecasts goal completion, analyzes habit impact, generates progress dashboards, and identifies learning requirements through semantic graph traversal and statistical modeling.

**Version:** 3.0.0 (Analytics merge from GoalAnalyticsService, November 2025)

---

## Core Methods

### Method 1: get_goal_with_context()

**Purpose:** Get goal with full graph context using pure Cypher graph intelligence. Automatically selects optimal query type based on goal's suggested intent.

**Signature:**
```python
async def get_goal_with_context(
    self,
    uid: str,
    depth: int = 2
) -> Result[tuple[Goal, GraphContext]]:
```

**Parameters:**
- `uid` (str) - Goal UID
- `depth` (int, default=2) - Graph traversal depth

**Returns:**
```python
(goal, graph_context)  # Tuple
```

**Query Selection:**
- **HIERARCHICAL** → Supporting activities and milestones
- **PREREQUISITE** → Required knowledge and learning paths
- **AGGREGATION** → Progress tracking across all activities
- **Default** → Comprehensive goal ecosystem

**Example:**
```python
result = await goals_service.intelligence.get_goal_with_context(
    uid="goal_001",
    depth=2
)

if result.is_ok:
    goal, graph_context = result.value
    print(f"Goal: {goal.title}")
    print(f"Graph nodes: {len(graph_context.nodes)}")
    print(f"Graph relationships: {len(graph_context.relationships)}")
```

**Dependencies:**
- GraphIntelligenceService (REQUIRED - uses `@requires_graph_intelligence` decorator)
- Uses GraphContextOrchestrator pattern (Phase 2 consolidation)

---

### Method 2: get_goal_progress_dashboard()

**Purpose:** Generate comprehensive goal progress dashboard with supporting activities, habit metrics, learning paths, and actionable recommendations.

**Signature:**
```python
async def get_goal_progress_dashboard(
    self,
    uid: str,
    min_confidence: float = 0.7
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `uid` (str) - Goal UID
- `min_confidence` (float, default=0.7) - Minimum confidence for graph relationships

**Returns:**
```python
{
    "goal": Goal(...),
    "progress": {
        "percentage": 45.0,
        "status": "active",
        "is_on_track": True,
        "target_date": "2026-03-01",
        "days_remaining": 52
    },
    "supporting_activities": {
        "tasks": [{"uid": "task_001"}, ...],
        "habits": [{"uid": "habit_001"}, ...],
        "learning_paths": [{"uid": "lp.python-basics"}, ...],
        "total_tasks": 8,
        "completed_tasks": 3,
        "active_habits": 2
    },
    "contributions": {
        "task_contribution": 37.5,
        "habit_contribution": 80.0,
        "learning_contribution": 20.0
    },
    "insights": {
        "needs_more_tasks": False,
        "needs_habit_support": False,
        "has_learning_gaps": True,
        "on_track": True
    },
    "recommendations": [
        "Develop learning paths for required knowledge areas",
        "Focus on completing more supporting tasks to advance progress"
    ],
    "metrics": {
        "task_support_count": 8,
        "habit_support_count": 2,
        "support_coverage": 0.65,
        "has_habit_system": True,
        "has_curriculum_alignment": False,
        "knowledge_requirement_count": 3
    }
}
```

**Example:**
```python
result = await goals_service.intelligence.get_goal_progress_dashboard("goal_001")

if result.is_ok:
    dashboard = result.value
    progress = dashboard["progress"]
    print(f"Progress: {progress['percentage']}%")
    print(f"Days remaining: {progress['days_remaining']}")

    for rec in dashboard["recommendations"]:
        print(f"Recommendation: {rec}")
```

**Dependencies:**
- GoalsOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED - uses `_require_relationships = True`)
- Uses CrossDomainContextService for typed context retrieval (Phase 3)
- Uses `calculate_goal_metrics()` for standard metrics

---

### Method 3: get_goal_completion_forecast()

**Purpose:** Generate goal completion forecast based on progress rate, task velocity, habit consistency, and historical patterns.

**Signature:**
```python
async def get_goal_completion_forecast(
    self,
    uid: str,
    depth: int = 2,
    min_confidence: float = 0.7
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `uid` (str) - Goal UID
- `depth` (int, default=2) - Graph traversal depth
- `min_confidence` (float, default=0.7) - Minimum confidence for relationships

**Returns:**
```python
{
    "goal": Goal(...),
    "forecast": {
        "estimated_completion_date": "2026-02-15",
        "confidence_level": "high",
        "on_track": True,
        "days_ahead_or_behind": 5,
        "completion_probability": 0.85
    },
    "velocity_metrics": {
        "current_progress_rate": 2.5,
        "task_completion_velocity": 3.2,
        "habit_consistency_score": 0.78,
        "learning_progress_rate": 0.5
    },
    "timeline_analysis": {
        "target_date": "2026-03-01",
        "days_remaining": 52,
        "required_velocity": 1.8,
        "current_pace": "ahead"
    },
    "risk_factors": [
        "Low habit consistency threatening goal achievement"
    ],
    "acceleration_opportunities": [
        "Increase task completion rate by 25%",
        "Add 1 more supporting habit"
    ],
    "metrics": {
        "task_support_count": 8,
        "habit_support_count": 2,
        "support_coverage": 0.65
    },
    "graph_context": {
        "task_support_count": 8,
        "habit_support_count": 2,
        "support_coverage": 0.65
    }
}
```

**Example:**
```python
result = await goals_service.intelligence.get_goal_completion_forecast("goal_001")

if result.is_ok:
    forecast = result.value
    print(f"Estimated completion: {forecast['forecast']['estimated_completion_date']}")
    print(f"Confidence: {forecast['forecast']['confidence_level']}")
    print(f"Completion probability: {forecast['forecast']['completion_probability']:.0%}")

    print("\nRisk Factors:")
    for risk in forecast["risk_factors"]:
        print(f"  - {risk}")
```

**Dependencies:**
- GoalsOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED)
- GoalsProgressService - for velocity calculations (domain-specific)
- Uses CrossDomainContextService (Phase 3)

---

### Method 4: get_goal_learning_requirements()

**Purpose:** Analyze goal's learning requirements including required knowledge areas, current mastery status, available learning paths, and knowledge gaps.

**Signature:**
```python
async def get_goal_learning_requirements(
    self,
    uid: str,
    depth: int = 2,
    min_confidence: float = 0.7
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `uid` (str) - Goal UID
- `depth` (int, default=2) - Graph traversal depth
- `min_confidence` (float, default=0.7) - Minimum confidence for relationships

**Returns:**
```python
{
    "goal": Goal(...),
    "knowledge_requirements": {
        "required_knowledge": [{"uid": "ku.python-basics"}, ...],
        "mastered_knowledge": [],
        "knowledge_gaps": [{"uid": "ku.python-basics"}, ...],
        "total_required": 3,
        "total_mastered": 0,
        "mastery_percentage": 0.0
    },
    "learning_paths": {
        "available_paths": [{"uid": "lp.python-basics"}, ...],
        "recommended_path": {"uid": "lp.python-basics"},
        "estimated_learning_time": 6  # hours
    },
    "learning_analysis": {
        "ready_to_start": False,
        "has_prerequisites": True,
        "learning_in_progress": False,
        "knowledge_complete": False
    },
    "recommendations": [
        "Master 3 knowledge areas before starting this goal",
        "Create a learning path to systematically acquire required knowledge"
    ],
    "metrics": {
        "knowledge_requirement_count": 3,
        "learning_path_count": 1,
        "has_curriculum_alignment": True
    },
    "graph_context": {
        "knowledge_requirement_count": 3,
        "learning_path_count": 1,
        "has_curriculum_alignment": True
    }
}
```

**Example:**
```python
result = await goals_service.intelligence.get_goal_learning_requirements("goal_001")

if result.is_ok:
    learning = result.value
    req = learning["knowledge_requirements"]
    print(f"Required knowledge: {req['total_required']}")
    print(f"Mastery: {req['mastery_percentage']}%")

    paths = learning["learning_paths"]
    print(f"Available paths: {len(paths['available_paths'])}")
    print(f"Estimated time: {paths['estimated_learning_time']} hours")
```

**Dependencies:**
- GoalsOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED)
- Uses CrossDomainContextService (Phase 3)

---

### Method 5: predict_goal_success()

**Purpose:** Predict probability of successfully achieving a goal using multiple factors including progress, habit consistency, time remaining, and historical patterns.

**Signature:**
```python
async def predict_goal_success(
    self,
    goal_uid: str,
    lookback_days: int = 30,
    habits_service: "HabitsOperations | None" = None
) -> Result[GoalPrediction]:
```

**Parameters:**
- `goal_uid` (str) - Goal to analyze
- `lookback_days` (int, default=30) - Days of history to consider
- `habits_service` (HabitsOperations, optional) - Service for fetching habit data (required for full analysis)

**Returns:**
```python
GoalPrediction(
    goal_uid="goal_001",
    goal_title="Launch MVP",
    success_probability=0.75,
    predicted_completion_date=date(2026, 2, 28),
    confidence_level="high",
    risk_factors=[
        "⏰ Less than 30 days remaining - time pressure high"
    ],
    success_factors=[
        "✅ Ahead of schedule",
        "💪 Strong habit consistency",
        "📊 Over halfway to goal"
    ],
    recommended_actions=[
        "👍 Maintain current momentum",
        "⏱️ Consider optimizing long habit sessions"
    ],
    trend="improving"
)
```

**Example:**
```python
result = await goals_service.intelligence.predict_goal_success(
    goal_uid="goal_001",
    lookback_days=30,
    habits_service=habits_service
)

if result.is_ok:
    prediction = result.value
    print(f"Success probability: {prediction.success_probability:.0%}")
    print(f"Predicted completion: {prediction.predicted_completion_date}")
    print(f"Trend: {prediction.trend}")

    print("\nSuccess Factors:")
    for factor in prediction.success_factors:
        print(f"  {factor}")

    print("\nRecommendations:")
    for action in prediction.recommended_actions:
        print(f"  {action}")
```

**Dependencies:**
- GoalsOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED)
- HabitsOperations (optional - enhanced analysis if provided)

**Merged from GoalAnalyticsService (November 2025):**
This method combines four probability factors using weighted model:
- **Progress factor** (35%) - Current vs expected progress
- **Consistency factor** (35%) - Habit performance
- **Time factor** (15%) - Time pressure
- **Momentum factor** (15%) - Recent trends

---

### Method 6: analyze_habit_impact()

**Purpose:** Analyze the impact of each habit on goal success, identifying critical habits and consistency gaps.

**Signature:**
```python
async def analyze_habit_impact(
    self,
    goal_uid: str,
    habits_service: "HabitsOperations | None" = None
) -> Result[list[HabitImpactAnalysis]]:
```

**Parameters:**
- `goal_uid` (str) - Goal to analyze
- `habits_service` (HabitsOperations, required) - Service for fetching habit data

**Returns:**
```python
[
    HabitImpactAnalysis(
        habit_uid="habit_001",
        habit_title="Daily coding practice",
        impact_score=0.72,
        criticality="important",
        current_consistency=0.72,
        required_consistency=0.8,
        consistency_gap=0.08
    ),
    ...
]
```

**Example:**
```python
result = await goals_service.intelligence.analyze_habit_impact(
    goal_uid="goal_001",
    habits_service=habits_service
)

if result.is_ok:
    analyses = result.value
    for analysis in analyses:
        print(f"Habit: {analysis.habit_title}")
        print(f"  Impact score: {analysis.impact_score:.2f}")
        print(f"  Criticality: {analysis.criticality}")
        print(f"  Current consistency: {analysis.current_consistency:.0%}")
        print(f"  Consistency gap: {analysis.consistency_gap:.0%}")
```

**Dependencies:**
- GoalsOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED)
- HabitsOperations (REQUIRED - fails if not provided)

**Impact Calculation:**
```
impact_score = weight × consistency
criticality = "critical" (weight ≥ 1.5)
            | "important" (weight ≥ 1.0)
            | "supportive" (weight < 1.0)
```

---

### Method 7: run_scenario_analysis()

**Purpose:** Run what-if scenario with adjusted habit consistencies to explore optimization opportunities.

**Signature:**
```python
async def run_scenario_analysis(
    self,
    goal_uid: str,
    consistency_adjustments: dict[str, float],
    habits_service: "HabitsOperations | None" = None
) -> Result[GoalPrediction]:
```

**Parameters:**
- `goal_uid` (str) - Goal to analyze
- `consistency_adjustments` (dict[str, float]) - Dict of habit_uid → new_consistency (0.0-1.0)
- `habits_service` (HabitsOperations, required) - Service for fetching habit data

**Returns:**
```python
GoalPrediction(
    goal_uid="goal_001",
    goal_title="Launch MVP (Scenario)",
    success_probability=0.82,
    predicted_completion_date=date(2026, 2, 20),
    confidence_level="medium",
    risk_factors=[],
    success_factors=[],
    recommended_actions=["This is a what-if scenario"],
    trend="stable"
)
```

**Example:**
```python
# Test scenario: Improve habit consistency by 20%
adjustments = {
    "habit_001": 0.85,  # Increase from 0.65 to 0.85
    "habit_002": 0.90,  # Increase from 0.70 to 0.90
}

result = await goals_service.intelligence.run_scenario_analysis(
    goal_uid="goal_001",
    consistency_adjustments=adjustments,
    habits_service=habits_service
)

if result.is_ok:
    scenario = result.value
    print(f"Scenario success probability: {scenario.success_probability:.0%}")
    print(f"Original completion: 2026-02-28")
    print(f"Scenario completion: {scenario.predicted_completion_date}")
    print(f"Days saved: {(date(2026, 2, 28) - scenario.predicted_completion_date).days}")
```

**Dependencies:**
- GoalsOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED)
- HabitsOperations (REQUIRED - fails if not provided)

**Note:** Adjustments are in-memory only - does not modify actual habit data.

---

### Method 8: assess_progress_dual_track() (ADR-030)

**Purpose:** Compare user's self-assessed goal progress with system-measured progress metrics, generating perception gap analysis and personalized insights.

**Signature:**
```python
async def assess_progress_dual_track(
    self,
    user_uid: str,
    user_progress_level: ProgressLevel,
    user_evidence: str,
    user_reflection: str | None = None,
    period_days: int = 30,
) -> Result[DualTrackResult[ProgressLevel]]:
```

**Parameters:**
- `user_uid` (str) - User identifier
- `user_progress_level` (ProgressLevel) - User's self-assessed progress level
- `user_evidence` (str) - User's evidence for their assessment
- `user_reflection` (str, optional) - User's optional reflection
- `period_days` (int, default=30) - Period to analyze for system calculation

**Returns:**
```python
DualTrackResult[ProgressLevel](
    entity_uid="user.mike",
    entity_type="progress_assessment",

    # USER-DECLARED (Vision)
    user_level=ProgressLevel.ON_TRACK,
    user_score=0.70,
    user_evidence="I'm making steady progress on my goals",
    user_reflection="Feeling confident about reaching my targets",

    # SYSTEM-CALCULATED (Action)
    system_level=ProgressLevel.SLIGHTLY_BEHIND,
    system_score=0.55,
    system_evidence=(
        "Milestone completion: 45%",
        "Goals on track: 50%",
        "Habit support: 62%",
        "Consistency: 58%",
    ),

    # GAP ANALYSIS
    perception_gap=0.15,
    gap_direction="user_higher",

    # INSIGHTS
    insights=("Self-assessment is higher than measured progress",),
    recommendations=("Focus on milestone completion", "Strengthen habit support"),
)
```

**ProgressLevel Enum:**
```python
class ProgressLevel(str, Enum):
    AHEAD = "ahead"                      # 0.85+
    ON_TRACK = "on_track"                # 0.70-0.85
    SLIGHTLY_BEHIND = "slightly_behind"  # 0.50-0.70
    BEHIND = "behind"                    # 0.30-0.50
    AT_RISK = "at_risk"                  # <0.30

    def to_score(self) -> float: ...
    @classmethod
    def from_score(cls, score: float) -> "ProgressLevel": ...
```

**System Metrics Used:**
- Milestone completion percentage
- Goals on track percentage
- Habit support (average habit consistency for goal-supporting habits)
- Overall consistency score

**Example:**
```python
result = await goals_service.intelligence.assess_progress_dual_track(
    user_uid="user.mike",
    user_progress_level=ProgressLevel.ON_TRACK,
    user_evidence="I'm making steady progress on my goals",
    user_reflection="Feeling confident about reaching my targets",
    period_days=30,
)

if result.is_ok:
    assessment = result.value
    if assessment.has_perception_gap():
        print(f"Gap detected: {assessment.gap_direction}")
        print(f"  User thinks: {assessment.user_level.value}")
        print(f"  System shows: {assessment.system_level.value}")
```

**Dependencies:**
- GoalsOperations backend (REQUIRED)
- UnifiedRelationshipService (REQUIRED for habit support calculation)
- Uses `BaseAnalyticsService._dual_track_assessment()` template

**API Endpoint:**
```
POST /api/goals/assess-progress
```

**See:** [ADR-030: Dual-Track Assessment Pattern](../decisions/ADR-030-dual-track-assessment-pattern.md)

---

## BaseAnalyticsService Features

### Inherited Infrastructure

**Fail-Fast Validation:**
- `_require_graph_intelligence()` - Ensures graph_intel available
- `_require_relationship_service()` - Ensures relationships available (REQUIRED)

**Standard Attributes:**
- `self.backend` - GoalsOperations (REQUIRED)
- `self.graph_intel` - GraphIntelligenceService (REQUIRED for graph methods)
- `self.relationships` - UnifiedRelationshipService (REQUIRED - `_require_relationships = True`)
- `self.embeddings` - OpenAIEmbeddingsService (not currently used)
- `self.llm` - LLMService (not currently used)

**Domain-Specific Attributes:**
- `self.progress` - GoalsProgressService for velocity calculations
- `self.context_service` - CrossDomainContextService for typed context retrieval (Phase 3)
- `self.orchestrator` - GraphContextOrchestrator for get_with_context pattern (Phase 2)

**Logging:**
```python
self.logger.info("Message")  # Logs to: skuel.intelligence.goals.intelligence
```

---

## Integration with GoalsService

### Facade Access

```python
# GoalsService creates intelligence internally
goals_service = GoalsService(
    backend=goals_backend,
    graph_intelligence_service=graph_intelligence,
    embeddings_service=embeddings_service,
    llm_service=llm_service,
    progress_service=progress_service,
    event_bus=event_bus,
    user_service=user_service,
)

# Access via .intelligence attribute
result = await goals_service.intelligence.predict_goal_success(
    goal_uid="goal_001",
    habits_service=habits_service
)
```

---

## Domain-Specific Features

### Progress Forecasting

GoalsIntelligenceService excels at **predicting future outcomes** using:
- **Velocity tracking** - Daily progress rate, task completion velocity
- **Habit analysis** - Consistency trends, streak momentum
- **Timeline analysis** - Days remaining, required velocity
- **Statistical modeling** - Weighted factor combination with non-linear scaling

### Predictive Analytics (v3.0.0)

Merged from GoalAnalyticsService (November 2025), provides:

**Success Prediction:**
- Combines 4 factors: progress (35%), consistency (35%), time (15%), momentum (15%)
- Non-linear scaling prevents over-confident predictions
- Caps probability at 95% max, 5% min

**Habit Impact Analysis:**
- Calculates impact_score = weight × consistency
- Identifies critical habits (weight ≥ 1.5)
- Detects consistency gaps (required_consistency - current_consistency)

**Scenario Analysis:**
- What-if modeling with adjusted habit consistencies
- In-memory adjustments (doesn't modify actual data)
- Comparative predictions (original vs scenario)

### Graph-Native Relationships

Uses `GoalRelationships.fetch()` for typed relationship access:
- `supporting_task_uids` - Tasks fulfilling goal
- `supporting_habit_uids` - Habits supporting goal
- `required_knowledge_uids` - Knowledge needed for goal
- `learning_path_uids` - Learning paths aligned with goal

### CrossDomainContextService (Phase 3)

Uses typed context retrieval with:
- `GoalCrossContext` - Type-safe field access
- `calculate_goal_metrics()` - Standard metrics calculation
- Recommendation generation functions

---

## Testing

### Unit Tests
```bash
uv run python -m pytest tests/unit/services/test_goals_intelligence_service.py -v
```

### Integration Tests
```bash
# Test with real backend
uv run python -m pytest tests/integration/intelligence/test_goals_intelligence.py -v

# Test specific method
uv run python -m pytest tests/integration/intelligence/ -k "test_predict_goal_success" -v
```

### Example Test
```python
from unittest.mock import Mock
from core.services.goals.goals_intelligence_service import GoalsIntelligenceService

# Create mock services
backend = Mock()
graph_intel = Mock()
relationships = Mock()

# Instantiate service
service = GoalsIntelligenceService(
    backend=backend,
    graph_intelligence_service=graph_intel,
    relationship_service=relationships
)

# Verify initialization
assert service._service_name == "goals.intelligence"
assert service._require_relationships is True
assert service.backend == backend
assert service.graph_intel == graph_intel
assert service.relationships == relationships
```

---

## See Also

- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` - Master index
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - BaseAnalyticsService pattern
- `/core/services/base_intelligence_service.py` - Base implementation
- `/core/services/goals/goals_service.py` - GoalsService facade
- `/core/services/goals/goals_progress_service.py` - Velocity calculations
- `/core/services/intelligence/cross_domain_context_service.py` - Phase 3 context retrieval
